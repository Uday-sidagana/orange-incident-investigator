import asyncio
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from orange_incident.benchmark import load_dataset, score
from orange_incident.engine import Limits
from orange_incident.investigation import run_simulation
from orange_incident.server import create_app
from orange_incident.tools import Simulation

ROOT=Path(__file__).resolve().parents[1]
FIXTURES,TRUTH=load_dataset(ROOT)


@pytest.mark.parametrize('case_id',sorted(k for k in FIXTURES if 'llm_only_case' not in TRUTH[k].get('tags',[])))
def test_authored_scenarios_through_all_six_simulated_roles(case_id,tmp_path):
    simulation=Simulation(ROOT/f'data/incidents/{case_id}.json')
    result,state=asyncio.run(run_simulation(simulation,tmp_path))
    assert result.approach=='simulation'
    assert result.input_tokens is None and result.output_tokens is None
    assert {task.role for task in state.tasks}=={'orchestrator','observability','dependency','reasoning','critic','reporting'}
    assert all(task.status=='complete' for task in state.tasks)
    measured=score(result,FIXTURES[case_id],TRUTH[case_id])
    assert measured['root_cause_top1'] and measured['grounded_top1']
    assert measured['citation_validity']==1
    assert (tmp_path/'traces/workflow.json').exists()


def test_critic_changes_confidence_after_control_check(tmp_path):
    result,state=asyncio.run(run_simulation(Simulation(ROOT/'data/incidents/gmail-001.json'),tmp_path))
    reasoning=[event['result']['candidates'][0] for event in state.events if event['event']=='agent_result' and event.get('role')=='reasoning']
    assert reasoning[0]['missing_checks']
    assert reasoning[0]['hypothesis']['confidence']=='medium'
    assert not reasoning[-1]['missing_checks']
    assert reasoning[-1]['hypothesis']['confidence']=='high'
    assert state.followup_rounds==1
    assert any('Missing verification' in objection for objection in state.objections)
    assert any(e.query.tool=='reproduce' for e in result.trace)


def test_renaming_incident_cannot_select_a_different_diagnosis(tmp_path):
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    sim.incident.id='arbitrary-new-identifier'
    sim.incident.title='Unfamiliar user wording'
    sim.incident.description='No solution keywords in this complaint.'
    result,_=asyncio.run(run_simulation(sim,tmp_path))
    assert result.ranked_cause_codes[0]=='recipient_mapping_regression'


def test_removing_causal_observations_prevents_known_answer(tmp_path):
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    sim.data['sources']['logs']=[]
    sim.data['sources']['reproduce']=[]
    sim.data['sources']['connections']=[]
    result,_=asyncio.run(run_simulation(sim,tmp_path))
    assert result.report.outcome=='inconclusive'
    assert 'recipient_mapping_regression' not in result.ranked_cause_codes


def test_missing_control_evidence_remains_inconclusive(tmp_path):
    sim=Simulation(ROOT/'data/incidents/gmail-001.json')
    sim.data['sources']['reproduce']=[]
    result,state=asyncio.run(run_simulation(sim,tmp_path))
    assert result.report.outcome=='inconclusive'
    assert state.followup_rounds==1
    assert any('Unresolved verification' in note for note in result.report.limitations)


def test_exhausted_budget_is_failed_execution_not_successful_diagnosis(tmp_path):
    result,state=asyncio.run(run_simulation(Simulation(ROOT/'data/incidents/gmail-001.json'),tmp_path,limits=Limits(max_tool_calls=1)))
    assert len(result.trace)<=1
    assert result.run_status=='failed'
    assert result.report.outcome=='inconclusive'


def test_portal_queue_simulation_and_review_without_model_or_network(tmp_path,monkeypatch):
    import orange_incident.codex_provider as provider
    monkeypatch.setattr(provider,'CodexProvider',lambda *a,**k:pytest.fail('Simulation must not construct a model provider'))
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',runtime='simulation')
    complaint={'name':'Demo Reviewer','email':'demo@example.invalid','company':'Atlas','title':'Gmail tool fails across customers',
               'description':'Gmail sends began failing across our application after a release.','scenario_id':'gmail-001'}
    with TestClient(app) as client:
        ticket=client.post('/api/tickets',json=complaint,headers={'Idempotency-Key':'simulation-e2e'}).json()['ticket']
        asyncio.run(app.state.process_next())
        ready=client.get('/api/tickets/'+ticket['id']).json()
        assert ready['status']=='needs_review'
        assert ready['result']['approach']=='simulation'
        assert ready['result']['workflow']['mode']=='deterministic_simulation'
        assert any(event['type']=='tool_finished' for event in ready['events'])
        reviewed=client.post('/api/tickets/'+ticket['id']+'/reviews',json={'verdict':'needs_work','notes':'Add an account-selection check.'}).json()
        assert reviewed['status']=='changes_requested'
        assert reviewed['events'][-1]['payload']['knowledge_updated'] is False
        assert reviewed['events'][-1]['payload']['response_sent'] is False
        assert client.get('/api/health').json()['runtime']=='simulation'


def test_derived_connection_view_is_not_independent_causal_evidence(tmp_path):
    sim=Simulation(ROOT/'data/incidents/refresh-007.json')
    result,_=asyncio.run(run_simulation(sim,tmp_path))
    views=[row for e in result.trace for row in e.records if row.get('source_kind')=='derived_view']
    assert any(row.get('connection_status')=='ACTIVE' and row.get('token_state')=='expired' for row in views)
    cited={c.record_id for f in result.findings for c in f.citations}
    assert not cited & {row['record_id'] for row in views}
