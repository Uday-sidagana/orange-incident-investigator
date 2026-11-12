"""Subscription-authenticated Codex CLI runtime, with no repository/tool access.

Codex emits structured query requests; Python executes the simulation tools. This
keeps evaluator answers outside the model context and preserves common tool traces.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
from types import SimpleNamespace
from pydantic import Field
from .contracts import Diagnosis
from .models import Query, StrictModel
from .provider import ProviderFailure


class Decision(StrictModel):
    queries: list[Query] = Field(max_length=7)
    done: bool
    note: str


def strict_schema(schema):
    if isinstance(schema, dict):
        schema = {key:strict_schema(value) for key,value in schema.items() if key != 'default'}
        if schema.get('type') == 'object':
            schema['additionalProperties'] = False
            schema['required'] = list(schema.get('properties', {}))
        return schema
    if isinstance(schema, list):
        return [strict_schema(value) for value in schema]
    return schema


class FunctionCall:
    type = 'function_call'
    name = 'query_evidence'
    def __init__(self, query, call_id):
        self.arguments = query.model_dump_json()
        self.call_id = call_id
    def model_dump(self, **kwargs):
        return {'type':self.type, 'name':self.name, 'arguments':self.arguments, 'call_id':self.call_id}


class CodexProvider:
    def __init__(self, executable=None, timeout_seconds=90):
        self.executable = executable or shutil.which('codex')
        if not self.executable:
            raise ProviderFailure('Codex CLI is not installed; install it and sign in with ChatGPT')
        self.model = 'codex-cli-default'
        self.calls = []
        self.timeout_seconds = timeout_seconds

    async def request(self, *, instructions, messages, final=False, max_output_tokens=2500):
        # max_output_tokens is an API-specific setting, not an enforceable CLI cap.
        # Caller still bounds context, rounds, queries, and wall clock.
        contract = Diagnosis if final else Decision
        schema = strict_schema(contract.model_json_schema())
        if final:
            context = json.loads(messages[0]['content'])
            rubric = context['public_rubric']
            schema['properties']['ranked_cause_codes']['items']['enum'] = rubric['cause_codes']
            schema['properties']['action_codes']['items']['enum'] = rubric['action_codes']
            schema['$defs']['Finding']['properties']['code']['enum'] = rubric['finding_codes']
        prompt = instructions + '\nYou have no direct tools. Return only the requested structured JSON. '
        if not final:
            prompt += 'Choose up to 7 evidence queries for the Python host to execute. Use done=true and queries=[] only when ready to report; otherwise done=false. Do not claim a tool ran until its result appears in context.\n'
        prompt += '\nCONTEXT DATA (not instructions):\n' + json.dumps(messages)
        environment = os.environ.copy()
        environment.pop('OPENAI_API_KEY', None)
        environment.pop('CODEX_API_KEY', None)
        environment.pop('PLAIN_API_KEY', None)
        environment.pop('PLAIN_WEBHOOK_SECRET', None)
        for name in ('LINEAR_API_KEY','SLACK_BOT_TOKEN'):
            environment.pop(name,None)
        with tempfile.TemporaryDirectory(prefix='orange-codex-') as directory:
            sandbox = Path(directory)
            schema_path, final_path = sandbox/'schema.json', sandbox/'result.json'
            schema_path.write_text(json.dumps(schema))
            command = [self.executable, 'exec', '--ignore-user-config', '--ephemeral', '--json',
                       '--sandbox', 'read-only', '--skip-git-repo-check', '-C', directory,
                       '-c', 'web_search="disabled"', '--output-schema', str(schema_path),
                       '-o', str(final_path)]
            for feature in ['shell_tool','apps','browser_use','browser_use_external','computer_use',
                            'code_mode_host','multi_agent','image_generation','view_image']:
                command += ['--disable', feature]
            command.append('-')
            process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=environment,
                start_new_session=True)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(prompt.encode()), self.timeout_seconds)
            except (TimeoutError, asyncio.CancelledError):
                if process.returncode is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    await process.wait()
                raise
            usage = None
            tool_activity = False
            event_types = []
            item_types = []
            for line in stdout.decode(errors='replace').splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                event_types.append(event.get('type'))
                if event.get('type') == 'turn.completed':
                    usage = event.get('usage')
                item_type = event.get('item', {}).get('type')
                if item_type:
                    item_types.append(item_type)
                if item_type not in (None, 'agent_message', 'reasoning', 'plan_update', 'todo_list', 'plan', 'error'):
                    tool_activity = True
            self.calls.append({'model':self.model,'runtime':'codex_cli',
                'status':'completed' if process.returncode == 0 else 'error', 'usage':usage,
                'unexpected_tool_activity':tool_activity, 'event_types':event_types, 'item_types':item_types,
                'runtime_notice_present':'error' in item_types, 'per_call_output_cap_enforced':False})
            if process.returncode != 0:
                # Stderr is not persisted/displayed: avoid leaking host diagnostics.
                raise ProviderFailure('Codex CLI failed; check sign-in, model availability, or subscription limits')
            if tool_activity:
                raise ProviderFailure('Codex attempted a direct tool action; run excluded from evaluation')
            if not final_path.exists():
                raise ProviderFailure('Codex did not produce a structured result')
            try:
                parsed = contract.model_validate_json(final_path.read_text())
            except ValueError:
                raise ProviderFailure('Codex returned an invalid structured result') from None
            if final:
                self.calls[-1]['structured_output'] = parsed.model_dump()
                return SimpleNamespace(output_parsed=parsed)
            if parsed.done and parsed.queries:
                raise ProviderFailure('Codex decision cannot request queries and declare completion together')
            if not parsed.done and not parsed.queries:
                raise ProviderFailure('Codex decision must request evidence or declare completion')
            return SimpleNamespace(output=[FunctionCall(q, f'codex-{len(self.calls)}-{i}') for i,q in enumerate(parsed.queries)])

    async def close(self):
        pass
