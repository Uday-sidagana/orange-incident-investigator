import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from orange_incident.baseline import investigate
from orange_incident.contracts import Diagnosis
from orange_incident.models import InvestigationReport
from orange_incident.provider import GPTProvider, ProviderFailure, load_config, tool_definition
from orange_incident.tools import Simulation

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = json.loads((ROOT/'data/rubric.json').read_text())


class Call:
    type = 'function_call'
    name = 'query_evidence'
    call_id = 'call-1'
    arguments = json.dumps({'tool':'logs'})
    def model_dump(self, **kwargs):
        return {'type':self.type,'name':self.name,'call_id':self.call_id,'arguments':self.arguments}


class FakeProvider:
    model = 'mock-not-a-live-model'
    def __init__(self, *, failure=False, repeat=False, delay=0):
        self.calls = []
        self.failure, self.repeat, self.delay = failure, repeat, delay
    async def request(self, *, instructions, messages, final=False, **kwargs):
        assert 'ground_truth' not in json.dumps(messages)
        assert 'acceptable_action_codes' not in json.dumps(messages)
        await asyncio.sleep(self.delay)
        self.calls.append({'model':self.model,'usage':{'input_tokens':10,'output_tokens':5}})
        if self.failure:
            raise ProviderFailure('GPT request failed: credit_balance_exhausted')
        if final:
            return SimpleNamespace(output_parsed=Diagnosis(report=InvestigationReport(
                incident_id='gmail-001', outcome='inconclusive', hypotheses=[], recommended_actions=[],
                limitations=['Mock provider did not diagnose']),ranked_cause_codes=[],findings=[],action_codes=[]))
        return SimpleNamespace(output=[Call()] if len(self.calls)==1 or self.repeat else [])


def run(tmp_path, provider, **kwargs):
    return asyncio.run(investigate(Simulation(ROOT/'data/incidents/gmail-001.json'), provider, RUBRIC, tmp_path, **kwargs))


def test_baseline_collects_tools_and_persists_measured_usage(tmp_path):
    provider = FakeProvider()
    result = run(tmp_path, provider)
    assert len(result.trace) == 1
    assert result.input_tokens == 30 and result.output_tokens == 15
    assert (tmp_path/'gmail-001.json').exists()
    assert (tmp_path/'traces/gmail-001.json').exists()
    assert result.report.outcome == 'inconclusive'


def test_quota_error_preserves_inconclusive_artifact(tmp_path):
    result = run(tmp_path, FakeProvider(failure=True))
    assert result.report.outcome == 'inconclusive' and not result.trace
    assert 'credit_balance_exhausted' in result.report.limitations[0]


def test_tool_budget_stops_repeated_calls(tmp_path):
    result = run(tmp_path, FakeProvider(repeat=True), max_tool_calls=1)
    assert len(result.trace) == 1
    assert 'Tool-call budget exhausted' in result.report.limitations


def test_timeout_preserves_artifact(tmp_path):
    result = run(tmp_path, FakeProvider(delay=1), timeout_seconds=0.01)
    assert 'Investigation deadline exceeded' in result.report.limitations
    assert result.input_tokens is None


def test_context_limit_prevents_request(tmp_path):
    provider = FakeProvider()
    result = run(tmp_path, provider, max_context_chars=10)
    assert provider.calls == [] and result.input_tokens is None
    assert result.report.outcome == 'inconclusive'


def test_env_loading_and_strict_function_schema(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    path = tmp_path/'.env'
    path.write_text('OPENAI_API_KEY=test-local-only\nOPENAI_MODEL=test-model\n')
    assert load_config(path) == ('test-local-only','test-model')
    schema = tool_definition()['parameters']
    assert set(schema['required']) == set(schema['properties'])
    assert schema['additionalProperties'] is False


def test_provider_errors_do_not_include_raw_exception_or_secret():
    class BrokenResponses:
        async def create(self, **kwargs):
            raise RuntimeError('secret-value-in-an-upstream-diagnostic')
    provider = GPTProvider('test-secret', 'mock', client=SimpleNamespace(responses=BrokenResponses()))
    async def scenario():
        try:
            await provider.request(instructions='test', messages=[])
        except ProviderFailure as exc:
            assert 'secret' not in str(exc)
    asyncio.run(scenario())
    assert 'secret' not in json.dumps(provider.calls)


def test_duplicate_model_queries_are_bounded(tmp_path):
    result = run(tmp_path, FakeProvider(repeat=True), max_tool_calls=16)
    assert len(result.trace) == 2
    assert 'Per-query retry limit exceeded' in result.report.limitations


def test_rejected_report_is_saved_and_marked_failed(tmp_path):
    class InvalidProvider(FakeProvider):
        async def request(self, **kwargs):
            response = await super().request(**kwargs)
            if kwargs.get('final'):
                response.output_parsed.report.incident_id = 'invented-incident'
            return response
    result = run(tmp_path, InvalidProvider())
    assert result.run_status == 'failed'
    metadata = json.loads((tmp_path/'traces/gmail-001.json').read_text())
    assert any(item['phase'] == 'rejected_report' for item in metadata['dialogue'])
