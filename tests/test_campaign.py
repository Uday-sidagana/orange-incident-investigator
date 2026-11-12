import asyncio,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from orange_incident.activity import agent_log
from orange_incident.server import create_app
from orange_incident.single_agent import run_single_agent
from orange_incident.llm_agents import ModelLimits
from orange_incident.models import Query,InvestigationReport,Hypothesis
from orange_incident.contracts import Diagnosis,Finding,Citation
from orange_incident.tools import Simulation

ROOT=Path(__file__).resolve().parents[1]

def test_two_workers_can_investigate_independently_without_duplicate_claims(tmp_path):
    async def run():
        entered=[]; both=asyncio.Event()
        async def investigate(ticket,root,output):
            entered.append(ticket['id'])
            if len(entered)==2:both.set()
            await asyncio.wait_for(both.wait(),2)
            return {'run_status':'completed','report':{'outcome':'inconclusive'}}
        app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',runtime='simulation',investigator=investigate,worker_count=2)
        for i in range(2):app.state.store.submit({'name':'Demo','email':'demo@example.invalid','company':'Demo','title':'Fictional incident','description':'A fictional incident to exercise queue concurrency.','scenario_id':'gmail-001'},str(i))
        await asyncio.gather(app.state.process_next(),app.state.process_next())
        assert len(set(entered))==2 and all(t['status']=='needs_review' for t in app.state.store.list())
    asyncio.run(run())


def test_work_log_keeps_retries_records_questions_and_decisions():
    def event(kind,**kwargs):return {'type':kind,'created_at':'2026-11-12T10:00:00Z','payload':{'task':'observe','role':'observability',**kwargs}}
    events=[event('task_started',question='Inspect impact',dependencies=[],available_evidence_ids=['ev_prior']),
            event('tool_started',query={'tool':'metrics'}),event('tool_finished',tool='metrics',status='error',evidence_id='ev_bad',result={'records':[],'error':{'retryable':True}}),
            event('tool_started',query={'tool':'metrics'}),event('tool_finished',tool='metrics',status='ok',evidence_id='ev_good',result={'records':[{'failures':50}]}),
            event('agent_result',result={'notes':['Observed failures'],'candidates':[],'objections':[]}),event('task_finished',status='complete')]
    task=agent_log({'id':'ticket','events':events})['tasks'][0]
    assert task['question']=='Inspect impact' and task['available_evidence_ids']==['ev_prior']
    assert [q['status'] for q in task['queries']]==['error','ok']
    assert task['queries'][1]['result']['records'][0]['failures']==50
    assert task['notes']==['Observed failures']


def test_matched_single_agent_uses_real_tool_boundary_and_shared_output_contract(tmp_path):
    class Fake:
        models={'single_agent':'fake'};limits=ModelLimits(max_collection_rounds=20,max_queries_per_task=24);calls=[];requests=0
        event_sink=None
        def emit(self,event):pass
        async def request(self,role,instructions,messages,**kwargs):
            assert role=='single_agent'
            self.requests+=1
            self.calls.append({'usage':{'input_tokens':10,'output_tokens':5}})
            if not kwargs.get('schema'):
                if len(messages)>1:return SimpleNamespace(output=[])
                return SimpleNamespace(output=[SimpleNamespace(type='function_call',name='query_logs',arguments=Query(tool='logs').model_dump_json(),call_id='one',model_dump=lambda **k:{'type':'function_call','name':'query_logs','arguments':Query(tool='logs').model_dump_json(),'call_id':'one'})])
            data=json.loads(messages[0]['content']);e=data['evidence'][0]
            return SimpleNamespace(output_parsed=Diagnosis(report=InvestigationReport(incident_id=data['incident']['id'],outcome='inconclusive',hypotheses=[],recommended_actions=['Collect evidence'],limitations=['Fake transport']),ranked_cause_codes=[],findings=[Finding(code='pre_provider_failure',statement='Observed event',citations=[Citation(evidence_id=e['evidence_id'],record_id=e['records'][0]['record_id'])])],action_codes=['collect_missing_telemetry']))
    result=asyncio.run(run_single_agent(Simulation(ROOT/'data/incidents/gmail-001.json'),tmp_path,root=ROOT,provider=Fake()))
    assert result.approach=='single_agent' and result.run_status=='completed' and len(result.trace)==1
    assert result.input_tokens==30


def test_new_cohort_source_provenance_and_inconclusive_case():
    cases=json.loads((ROOT/'evaluation/prospective-v3.json').read_text())
    assert len(cases)==20 and len({c['id'] for c in cases})==20
    assert all(c['source_url'].startswith('https://docs.composio.dev/kb/guide/') for c in cases)
    assert sum(c['expected_cause'] is None for c in cases)==1
    for c in cases:
        fixture=json.loads((ROOT/f"data/incidents/{c['id']}.json").read_text())
        assert all('cause_code' not in row for rows in fixture['sources'].values() for row in rows)


def test_work_log_separates_recovery_attempts_with_reused_task_ids():
    def event(kind,**payload):return {'type':kind,'created_at':'2026-11-12T10:00:00Z','payload':payload}
    events=[event('investigation_started'),event('task_started',task='plan',role='orchestrator',question='First attempt'),event('task_finished',task='plan',role='orchestrator',status='failed'),
            event('investigation_started'),event('task_started',task='plan',role='orchestrator',question='Recovery attempt'),event('task_finished',task='plan',role='orchestrator',status='complete')]
    tasks=agent_log({'id':'ticket','events':events})['tasks']
    assert [(task['attempt'],task['question'],task['status']) for task in tasks]==[(1,'First attempt','failed'),(2,'Recovery attempt','complete')]


def test_explicit_reinvestigation_is_idempotent_preserves_previous_report_and_thread(tmp_path):
    from orange_incident.tickets import TicketStore,Conflict
    store=TicketStore(tmp_path/'inbox.sqlite')
    ticket_id,_=store.submit({'name':'Demo','email':'demo@example.invalid','company':'Demo','title':'Synthetic incident','description':'A synthetic report to test explicit reinvestigation.','scenario_id':'gmail-001'},'initial')
    store.claim();store.finish(ticket_id,result={'run_status':'completed','report':{'outcome':'inconclusive'}})
    previous_thread=store.get(ticket_id)['plain']['thread_id']
    assert store.reinvestigate(ticket_id,'v31','Corrected controlled telemetry')
    assert not store.reinvestigate(ticket_id,'v31','Corrected controlled telemetry')
    with pytest.raises(Conflict):store.reinvestigate(ticket_id,'v31','Different request reason')
    ticket=store.get(ticket_id)
    assert ticket['status']=='queued' and ticket['plain']['thread_id']==previous_thread
    assert any(e['type']=='previous_investigation_saved' and e['payload']['result']['report']['outcome']=='inconclusive' for e in ticket['events'])


def test_corrected_success_controls_do_not_retain_active_error_states():
    cases=json.loads((ROOT/'evaluation/prospective-v3.json').read_text())
    for case in cases:
        fixture=json.loads((ROOT/f"data/incidents/{case['id']}.json").read_text())
        for record in fixture['sources']['reproduce']:
            if record.get('condition')!='corrected':continue
            assert record.get('check_passed') is True and record['status']<400
            assert not any(record.get(field) for field in ('error','oauth_error','validation_error'))
            if record.get('connection_state')=='ACTIVE':assert record.get('token_exchange_attempted') is True
            if record.get('pagination_completed'):assert record.get('has_more') is False
