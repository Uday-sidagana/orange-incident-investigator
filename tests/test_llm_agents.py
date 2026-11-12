import asyncio
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from openai import AsyncOpenAI
from orange_incident.contracts import Candidate, Citation, Diagnosis, Finding
from orange_incident.engine import AgentResult, Engine, State, Task, ToolAccess
from orange_incident.llm_agents import AgentProvider, Critique, Followup, LivePolicies, ModelLimits, Plan, ReasoningDecision, ROLES, run_live_agents, validate_conclusions
from orange_incident.models import Hypothesis, InvestigationReport, Query
from orange_incident.provider import ProviderFailure
from orange_incident.tools import Simulation
import json

ROOT=Path(__file__).resolve().parents[1]
RUBRIC=json.loads((ROOT/'data/rubric.json').read_text())


def test_structured_calls_bound_usage_and_sanitize_provider_errors():
    requests=[]
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(401,json={'error':{'message':'secret-data','type':'invalid_request_error','code':'invalid_api_key'}})
    async def run():
        client=AsyncOpenAI(api_key='test-secret',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        provider=AgentProvider('test-secret',{r:'test-model' for r in ROLES},client=client,limits=ModelLimits(max_requests=1))
        with pytest.raises(ProviderFailure,match='invalid_api_key') as error:
            await provider.request('critic','Check',[],schema=Critique)
        assert 'secret-data' not in str(error.value) and 'test-secret' not in json.dumps(provider.calls)
        with pytest.raises(ProviderFailure,match='budget'):
            await provider.request('critic','Check',[],schema=Critique)
        await provider.close()
    asyncio.run(run())
    assert len(requests)==1 and requests[0]['store'] is False
    assert requests[0]['text']['format']['strict'] is True


def test_finding_validation_rejects_derived_and_unknown_records():
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    evidence=asyncio.run(sim.query(Query(tool='logs')))
    hypothesis=Hypothesis(description='Candidate',supporting_evidence=[evidence.evidence_id],contradicting_evidence=[],confidence='medium',assumptions=[])
    finding=Finding(code='pre_provider_failure',statement='Observed',citations=[Citation(evidence_id=evidence.evidence_id,record_id='invented')])
    decision=ReasoningDecision(candidates=[Candidate(code='recipient_mapping_regression',hypothesis=hypothesis)],findings=[finding],notes=[])
    with pytest.raises(ProviderFailure,match='citation'):
        validate_conclusions(decision,[evidence],RUBRIC)
    finding.citations[0].record_id=evidence.records[0]['record_id']
    evidence.records[0]['source_kind']='derived_view'
    with pytest.raises(ProviderFailure,match='citation'):
        validate_conclusions(decision,[evidence],RUBRIC)


class ScriptedProvider:
    """A model transport fake: exercises orchestration, not diagnostic performance."""
    def __init__(self,approve=True):
        self.models={r:'fake' for r in ROLES}; self.calls=[]; self.limits=ModelLimits(); self.approve=approve; self.event_sink=None
    def emit(self,event):
        pass
    async def request(self,role,instructions,messages,*,schema=None,allowed_tools=None,constraints=None,discovered_tools=None):
        self.calls.append({'role':role,'usage':{'input_tokens':10,'output_tokens':5}})
        data=json.loads(messages[0]['content'])
        if not schema:
            # Query once per collector. Tool responses cause collection to end on next turn.
            if len(messages)>1:
                return SimpleNamespace(output=[])
            tool={'observability':'logs','dependency':'deployments','reasoning':'history'}[role]
            return SimpleNamespace(output=[SimpleNamespace(type='function_call',name='query_evidence',arguments=Query(tool=tool).model_dump_json(),call_id=role,
                model_dump=lambda **kwargs:{'type':'function_call','name':'query_evidence','arguments':Query(tool=tool).model_dump_json(),'call_id':role})])
        if schema is Plan:
            parsed=Plan(observability_question='Inspect logs',dependency_question='Inspect changes',reasoning_question='Compare evidence',notes=[])
        elif schema.__name__=='CollectionSummary':
            parsed=schema(notes=['Read available evidence'])
        elif schema is Critique:
            parsed=Critique(approved=self.approve,objections=[] if self.approve else ['Missing verification'],followups=[],notes=[])
        else:
            evidence=next(e for e in data['evidence'] if e['query']['tool']=='logs')
            finding=Finding(code='pre_provider_failure',statement='Observed log event',citations=[Citation(evidence_id=evidence['evidence_id'],record_id=evidence['records'][0]['record_id'])])
            hypothesis=Hypothesis(description='A candidate explanation',supporting_evidence=[evidence['evidence_id']],contradicting_evidence=[],confidence='medium',assumptions=['Synthetic fake'])
            if schema is ReasoningDecision:
                parsed=ReasoningDecision(candidates=[Candidate(code='recipient_mapping_regression',hypothesis=hypothesis,findings=[finding],actions=['Inspect'],action_codes=['repair_recipient_mapping'])],findings=[finding],notes=[])
            else:
                parsed=Diagnosis(report=InvestigationReport(incident_id=data['incident']['id'],outcome='probable_cause',hypotheses=[hypothesis],recommended_actions=['Inspect'],limitations=[]),ranked_cause_codes=['recipient_mapping_regression'],findings=[finding],action_codes=['repair_recipient_mapping'])
        return SimpleNamespace(output_parsed=parsed)


@pytest.mark.parametrize('approved',[True,False])
def test_live_roles_integrate_without_simulation_policies_or_network(tmp_path,monkeypatch,approved):
    import orange_incident.investigation as simulation_policy
    monkeypatch.setattr(simulation_policy,'analyze',lambda *a:pytest.fail('Live agents must not invoke authored diagnostic rules'))
    provider=ScriptedProvider(approved)
    result,state=asyncio.run(run_live_agents(Simulation(ROOT/'data/incidents/gmail-001.json'),tmp_path,root=ROOT,provider=provider))
    assert result.approach=='multi_agent' and result.run_status=='completed'
    assert state.mode=='live_agents' and {t.role for t in state.tasks}==set(ROLES)
    assert result.report.outcome==('probable_cause' if approved else 'inconclusive')
    assert result.input_tokens==10*len(provider.calls)
    assert (tmp_path/'traces/model-calls.json').exists()


def test_model_cannot_bypass_role_tool_permission(tmp_path):
    class Denied(ScriptedProvider):
        async def request(self,*a,**kwargs):
            return SimpleNamespace(output=[SimpleNamespace(type='function_call',name='query_evidence',arguments=Query(tool='reproduce').model_dump_json(),call_id='denied',model_dump=lambda **kw:{})])
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    policy=LivePolicies(Denied(),RUBRIC)
    run=Engine(sim.incident,sim.query,{'observability':policy},mode='live_agents')
    state=asyncio.run(run.run([Task(id='obs',role='observability',question='Inspect')]))
    assert state.tasks[0].status=='failed' and state.tool_calls==0


def test_critic_schedules_targeted_reassessment_and_cannot_approve_missing_check():
    class Critical(ScriptedProvider):
        async def request(self,*args,**kwargs):
            return SimpleNamespace(output_parsed=Critique(approved=True,blocking_checks=['Controlled verification'],objections=[],followups=[Followup(role='dependency',question='Inspect the controlled comparison')],notes=[]))
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    evidence=asyncio.run(sim.query(Query(tool='logs')))
    candidate=Candidate(code='recipient_mapping_regression',hypothesis=Hypothesis(description='Possible regression',supporting_evidence=[evidence.evidence_id],contradicting_evidence=[],confidence='medium',assumptions=[]),missing_checks=['Controlled verification'])
    policy=LivePolicies(Critical(),RUBRIC)
    run=Engine(sim.incident,sim.query,{'critic':policy},mode='live_agents')
    state=State(incident=sim.incident,mode='live_agents',evidence=[evidence],candidates=[candidate])
    decision=asyncio.run(policy(Task(id='critic',role='critic',question='Check'),state,ToolAccess(run,'critic')))
    assert not policy.approved
    assert [t.role for t in decision.followups]==['dependency','reasoning','critic']
    assert decision.followups[1].dependencies==[decision.followups[0].id]
    assert decision.objections


def test_openai_server_health_and_actual_complaint_reach_agent_runtime(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from orange_incident.server import create_app
    import orange_incident.llm_agents as module
    seen=[]
    async def fake_run(simulation,output,**kwargs):
        seen.append((simulation.incident.title,simulation.incident.description))
        return await run_live_agents(simulation,output,root=ROOT,provider=ScriptedProvider())
    monkeypatch.setattr(module,'run_live_agents',fake_run)
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',runtime='openai')
    with TestClient(app) as client:
        assert client.get('/api/health').json()['architecture']=='live_six_role_workflow'
        body={'name':'Demo','email':'demo@example.invalid','company':'Demo','title':'Actual customer subject',
              'description':'Actual customer complaint describing a send failure.','scenario_id':'gmail-001'}
        ticket=client.post('/api/tickets',json=body,headers={'Idempotency-Key':'gpt-test'}).json()['ticket']
        asyncio.run(app.state.process_next())
        result=client.get('/api/tickets/'+ticket['id']).json()
        assert result['status']=='needs_review' and result['result']['approach']=='multi_agent'
        assert result['result']['workflow']['mode']=='live_agents'
    assert seen==[(body['title'],body['description'])]


def test_output_schema_limits_codes_and_citations_to_observed_vocabulary():
    from orange_incident.llm_agents import constrained_schema
    constraints={'rubric':RUBRIC,'evidence_ids':['ev_seen'],'record_ids':['observed-record']}
    schema=constrained_schema(ReasoningDecision,constraints)
    definitions=schema['$defs']
    assert definitions['Hypothesis']['properties']['supporting_evidence']['items']['enum']==['ev_seen']
    assert definitions['Citation']['properties']['record_id']['enum']==['observed-record']
    assert definitions['Candidate']['properties']['code']['enum']==RUBRIC['cause_codes']
    assert definitions['Finding']['properties']['code']['enum']==RUBRIC['finding_codes']
    assert set(schema['required'])==set(schema['properties'])


def test_discovery_tool_schema_forbids_overfiltering():
    seen=[]
    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(401,json={'error':{'message':'test','type':'invalid_request_error','code':'invalid_api_key'}})
    async def run():
        client=AsyncOpenAI(api_key='test',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        provider=AgentProvider('test',{r:'fake' for r in ROLES},client=client)
        with pytest.raises(ProviderFailure):
            await provider.request('observability','Discover',[],allowed_tools={'logs'})
        await provider.close()
    asyncio.run(run())
    properties=seen[0]['tools'][0]['parameters']['properties']
    assert properties['tool']['enum']==['logs']
    assert all(properties[field]['type']=='null' for field in ('service','tenant','version','start','end','search'))


def test_citation_schema_preserves_envelope_record_pairing():
    from orange_incident.llm_agents import constrained_schema
    constraints={'rubric':RUBRIC,'evidence_ids':['ev_one','ev_two'],'record_ids':['row-one','row-two'],
                 'catalogue':{'ev_one':['row-one'],'ev_two':['row-two']}}
    branches=constrained_schema(ReasoningDecision,constraints)['$defs']['Citation']['anyOf']
    assert [(b['properties']['evidence_id']['enum'],b['properties']['record_id']['enum']) for b in branches]==[(['ev_one'],['row-one']),(['ev_two'],['row-two'])]


def test_critic_reserves_reporting_capacity_when_budget_is_nearly_spent():
    class Critical(ScriptedProvider):
        requests=22
        async def request(self,*a,**kw):
            return SimpleNamespace(output_parsed=Critique(approved=False,objections=['Missing control'],followups=[Followup(role='dependency',question='Inspect reproduction')],notes=[]))
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    policy=LivePolicies(Critical(),RUBRIC)
    run=Engine(sim.incident,sim.query,{'critic':policy},mode='live_agents')
    decision=asyncio.run(policy(Task(id='critic',role='critic',question='Check'),run.state,ToolAccess(run,'critic')))
    assert [t.role for t in decision.followups]==['reporting']
    assert any('budget' in note for note in decision.objections)


def test_critic_can_clear_optional_coverage_caveat_after_review():
    class Critical(ScriptedProvider):
        async def request(self,*a,**kw):
            return SimpleNamespace(output_parsed=Critique(approved=True,blocking_checks=[],objections=[],followups=[],notes=['Coverage caveat does not change the observed mechanism.']))
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    evidence=asyncio.run(sim.query(Query(tool='logs')))
    finding=Finding(code='pre_provider_failure',statement='Observed',citations=[Citation(evidence_id=evidence.evidence_id,record_id=evidence.records[0]['record_id'])])
    candidate=Candidate(code='recipient_mapping_regression',hypothesis=Hypothesis(description='Observed mechanism',supporting_evidence=[evidence.evidence_id],contradicting_evidence=[],confidence='medium',assumptions=[]),findings=[finding],missing_checks=['Exhaustive tenant coverage'])
    policy=LivePolicies(Critical(),RUBRIC)
    run=Engine(sim.incident,sim.query,{'critic':policy},mode='live_agents')
    run.state.candidates=[candidate]
    decision=asyncio.run(policy(Task(id='critic',role='critic',question='Review'),run.state,ToolAccess(run,'critic')))
    assert policy.approved and decision.candidates[0].missing_checks==[]
    assert candidate.missing_checks==['Exhaustive tenant coverage']
    assert decision.followups[0].role=='reporting'


def test_kb_guidance_is_attributed_and_cannot_alone_confirm_incident():
    from orange_incident.llm_agents import label_kb_guidance
    sim=Simulation(ROOT/'data/incidents/github-org-035.json')
    evidence=asyncio.run(sim.query(Query(tool='knowledge')))
    finding=Finding(code='mechanism_observation',statement='Organization approval can be required.',citations=[Citation(evidence_id=evidence.evidence_id,record_id=evidence.records[0]['record_id'])])
    report=InvestigationReport(incident_id=sim.incident.id,outcome='probable_cause',hypotheses=[Hypothesis(description='Possible organization restriction',supporting_evidence=[evidence.evidence_id],contradicting_evidence=[],confidence='low',assumptions=[])],recommended_actions=['Check organization policy'],limitations=[])
    decision=Diagnosis(report=report,ranked_cause_codes=['github_organization_approval'],findings=[finding],action_codes=[])
    with pytest.raises(ProviderFailure,match='Knowledge-base guidance alone'):
        validate_conclusions(decision,[evidence],RUBRIC)
    decision.report.outcome='inconclusive'
    label_kb_guidance(decision,[evidence])
    assert decision.findings[0].statement.startswith('KB guidance (unverified for this incident):')
    assert 'https://docs.composio.dev/kb/guide/toolkits-github' in decision.report.limitations[-1]
    assert 'not independent verification' in decision.report.hypotheses[0].assumptions[-1]


def test_repeated_finding_codes_keep_both_observations_and_validate_every_citation():
    from orange_incident.llm_agents import consolidate_findings
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    evidence=asyncio.run(sim.query(Query(tool='logs')))
    a=Finding(code='tenant_impact',statement='Failure impact.',citations=[Citation(evidence_id=evidence.evidence_id,record_id=evidence.records[0]['record_id'])])
    b=Finding(code='tenant_impact',statement='Latency impact.',citations=[Citation(evidence_id=evidence.evidence_id,record_id=evidence.records[1]['record_id'])])
    decision=ReasoningDecision(candidates=[],findings=[a,b],notes=[])
    assert consolidate_findings(decision)
    assert len(decision.findings)==1 and len(decision.findings[0].citations)==2
    assert decision.findings[0].statement=='Failure impact. Latency impact.'
    validate_conclusions(decision,[evidence],RUBRIC)
    decision.findings[0].citations[1].record_id='invented'
    with pytest.raises(ProviderFailure,match='citation'):validate_conclusions(decision,[evidence],RUBRIC)
