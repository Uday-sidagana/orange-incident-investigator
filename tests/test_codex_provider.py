import asyncio
import json
from pathlib import Path
import stat
import pytest
from orange_incident.codex_provider import CodexProvider, Decision, strict_schema
from orange_incident.provider import ProviderFailure


def executable(tmp_path, result, *, event=None, exit_code=0):
    path = tmp_path/'fake-codex'
    code = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
assert '--ignore-user-config' in args
assert '--ephemeral' in args
assert args[args.index('--sandbox')+1] == 'read-only'
assert 'OPENAI_API_KEY' not in os.environ
assert 'CODEX_API_KEY' not in os.environ
assert '--disable' in args
sys.stdin.read()
'''
    code += f"pathlib.Path(args[args.index('-o')+1]).write_text({json.dumps(json.dumps(result))})\n"
    code += f"print({json.dumps(json.dumps(event or {'type':'turn.completed','usage':{'input_tokens':40,'output_tokens':10}}))})\n"
    code += f'sys.exit({exit_code})\n'
    path.write_text(code)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_structured_queries_and_usage(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','must-not-reach-child')
    provider = CodexProvider(executable(tmp_path, {'queries':[{'tool':'logs'}],'done':False,'note':'Inspect errors'}))
    result = asyncio.run(provider.request(instructions='Investigate',messages=[]))
    assert result.output[0].name == 'query_evidence'
    assert json.loads(result.output[0].arguments)['tool'] == 'logs'
    assert provider.calls[0]['usage']['input_tokens'] == 40
    assert provider.calls[0]['per_call_output_cap_enforced'] is False


def test_finished_collection(tmp_path):
    provider = CodexProvider(executable(tmp_path, {'queries':[],'done':True,'note':'Ready'}))
    assert asyncio.run(provider.request(instructions='Investigate',messages=[])).output == []


def test_direct_tool_use_disqualifies_run(tmp_path):
    provider = CodexProvider(executable(tmp_path, {'queries':[],'done':True,'note':'Ready'},
        event={'type':'item.completed','item':{'type':'command_execution'}}))
    with pytest.raises(ProviderFailure, match='direct tool action'):
        asyncio.run(provider.request(instructions='Investigate',messages=[]))


def test_invalid_or_failed_cli_output(tmp_path):
    provider = CodexProvider(executable(tmp_path, {'queries':[],'done':False,'note':'Stuck'}))
    with pytest.raises(ProviderFailure, match='request evidence'):
        asyncio.run(provider.request(instructions='Investigate',messages=[]))
    provider = CodexProvider(executable(tmp_path, {}, exit_code=1))
    with pytest.raises(ProviderFailure, match='CLI failed'):
        asyncio.run(provider.request(instructions='Investigate',messages=[]))


def test_strict_nested_schema():
    schema = strict_schema(Decision.model_json_schema())
    query = schema['$defs']['Query']
    assert set(query['required']) == set(query['properties'])
    assert all('default' not in value for value in query['properties'].values())


def test_internal_todo_plan_is_not_evidence_access(tmp_path):
    provider = CodexProvider(executable(tmp_path, {'queries':[],'done':True,'note':'Ready'},
        event={'type':'item.completed','item':{'type':'todo_list'}}))
    assert asyncio.run(provider.request(instructions='Investigate',messages=[])).output == []
    assert provider.calls[0]['unexpected_tool_activity'] is False


def test_runtime_notice_is_not_a_direct_tool_action(tmp_path):
    provider = CodexProvider(executable(tmp_path, {'queries':[],'done':True,'note':'Ready'},
        event={'type':'item.completed','item':{'type':'error','message':'Non-fatal runtime notice'}}))
    assert asyncio.run(provider.request(instructions='Investigate',messages=[])).output == []
    assert provider.calls[0]['runtime_notice_present'] is True
    assert provider.calls[0]['unexpected_tool_activity'] is False
