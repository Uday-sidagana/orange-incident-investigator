import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from orange_incident.server import create_app
from orange_incident.tickets import TicketStore

ROOT=Path(__file__).resolve().parents[1]
PAYLOAD={'name':'Demo User','email':'demo@example.com','company':'Atlas','title':'Gmail send failure spike',
         'description':'Gmail sends began failing across our application around the last release.', 'scenario_id':'gmail-001'}


def test_submit_persist_and_idempotency_conflict(tmp_path):
    db=tmp_path/'inbox.sqlite'
    app=create_app(ROOT,db_path=db,run_worker=False,plain_mode='simulated')
    with TestClient(app) as client:
        first=client.post('/api/tickets',json=PAYLOAD,headers={'Idempotency-Key':'one'})
        assert first.status_code == 202
        ticket_id=first.json()['ticket']['id']
        second=client.post('/api/tickets',json=PAYLOAD,headers={'Idempotency-Key':'one'})
        assert not second.json()['created'] and second.json()['ticket']['id']==ticket_id
        different=dict(PAYLOAD,title='Different complaint')
        assert client.post('/api/tickets',json=different,headers={'Idempotency-Key':'one'}).status_code==409
        assert len(client.get('/api/tickets').json())==1
        assert client.get('/api/tickets/'+ticket_id).json()['plain']['mode']=='simulated'
    assert TicketStore(db).get(ticket_id)['complaint']==PAYLOAD


def test_invalid_case_and_no_evaluator_data(tmp_path):
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated')
    with TestClient(app) as client:
        assert client.post('/api/tickets',json=dict(PAYLOAD,scenario_id='../evaluation/ground_truth'),headers={'Idempotency-Key':'one'}).status_code==422
        assert client.post('/api/tickets',json=PAYLOAD).status_code==422
        cases=client.get('/api/scenarios').json()
        assert len(cases)==len(list((ROOT/'data/incidents').glob('*.json')))
        assert all(set(case)=={'id','title','description'} for case in cases)
        assert client.get('/evaluation/ground_truth.json').status_code==404
        assert client.get('/').status_code==200


def test_worker_passes_complaint_and_saves_report(tmp_path):
    async def investigator(ticket,root,output):
        assert ticket['complaint']['description']==PAYLOAD['description']
        return {'run_status':'completed','report':{'outcome':'inconclusive'},'trace':[]}
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',investigator=investigator)
    ticket_id,_=app.state.store.submit(PAYLOAD,'one')
    assert asyncio.run(app.state.process_next())
    value=app.state.store.get(ticket_id)
    assert value['status']=='needs_review'
    assert value['events'][-1]['payload']['sent'] is False
    assert not asyncio.run(app.state.process_next())


def test_failed_worker_redacts_error_and_explicit_retry(tmp_path):
    async def broken(*args):
        raise RuntimeError('secret-from-upstream-do-not-display')
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',investigator=broken)
    ticket_id,_=app.state.store.submit(PAYLOAD,'one')
    asyncio.run(app.state.process_next())
    assert app.state.store.get(ticket_id)['status']=='failed'
    assert 'secret' not in app.state.store.get(ticket_id)['error']
    with TestClient(app) as client:
        assert client.post('/api/tickets/'+ticket_id+'/retry').status_code==202
        assert client.post('/api/tickets/'+ticket_id+'/retry').status_code==409


def test_restart_marks_active_work_failed_without_automatic_model_retry(tmp_path):
    db=tmp_path/'inbox.sqlite'
    store=TicketStore(db)
    ticket_id,_=store.submit(PAYLOAD,'one')
    store.claim()
    app=create_app(ROOT,db_path=db,run_worker=False,plain_mode='simulated')
    with TestClient(app):
        assert app.state.store.get(ticket_id)['status']=='failed'
        assert app.state.store.claim() is None


def test_concurrent_workers_do_not_claim_same_job(tmp_path):
    store=TicketStore(tmp_path/'inbox.sqlite')
    store.submit(PAYLOAD,'one')
    async def claim():
        return await asyncio.to_thread(store.claim)
    async def run():
        return await asyncio.gather(claim(),claim())
    results=asyncio.run(run())
    assert sum(result is not None for result in results)==1


def test_custom_issue_never_inherits_demo_evidence(tmp_path):
    from orange_incident.server import ticket_evidence
    from orange_incident.models import Query
    async def investigator(ticket,root,output):
        simulation=ticket_evidence(ticket,root)
        assert simulation.incident.id==ticket['id']
        result=await simulation.query(Query(tool='logs'))
        assert result.status=='partial' and not result.complete and result.records==[]
        assert 'No live production telemetry' in simulation.incident.description
        return {'run_status':'completed','report':{'outcome':'inconclusive'},'trace':[]}
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',investigator=investigator)
    with TestClient(app) as client:
        body={k:v for k,v in PAYLOAD.items() if k!='scenario_id'}
        response=client.post('/api/tickets',json=body,headers={'Idempotency-Key':'custom'})
        assert response.status_code==202
        ticket=response.json()['ticket'];assert ticket['complaint']['scenario_id']=='custom'
        asyncio.run(app.state.process_next())
        assert client.get('/api/tickets/'+ticket['id']).json()['result']['report']['outcome']=='inconclusive'


def test_custom_evidence_is_scoped_validated_and_incomplete(tmp_path):
    from orange_incident.server import ticket_evidence
    from orange_incident.models import Query
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',runtime='openai')
    with TestClient(app) as client:
        body=dict(PAYLOAD,scenario_id='custom',evidence={'logs':[{'record_id':'custom:1','status':401}]})
        response=client.post('/api/tickets',json=body,headers={'Idempotency-Key':'custom'})
        assert response.status_code==202
        simulation=ticket_evidence(response.json()['ticket'],ROOT)
        result=asyncio.run(simulation.query(Query(tool='logs')))
        assert result.records==body['evidence']['logs'] and not result.complete
        for evidence in [{'logs':[{'status':401}]},{'secret_api':[]},{'logs':[{'record_id':'1','timestamp':'yesterday'}]}]:
            assert client.post('/api/tickets',json=dict(body,evidence=evidence),headers={'Idempotency-Key':'invalid'}).status_code==422
        assert client.post('/api/tickets',json=dict(body,scenario_id='gmail-001'),headers={'Idempotency-Key':'fixture'}).status_code==422


def test_clean_checkout_serves_packaged_comparison_without_local_runs(tmp_path):
    import json,shutil
    (tmp_path/'evaluation').mkdir()
    shutil.copy2(ROOT/'evaluation/splits.json',tmp_path/'evaluation/splits.json')
    bundle=tmp_path/'submission/evaluation/composio-v3';bundle.mkdir(parents=True)
    source=ROOT/'submission/evaluation/composio-v3'
    shutil.copy2(source/'comparison.json',bundle/'comparison.json')
    case='github-org-035'
    for folder in ['single_agent_plain_matched']:
        shutil.copytree(source/folder/case,bundle/folder/case)
    app=create_app(tmp_path,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated')
    with TestClient(app) as client:
        comparison=client.get('/api/comparison').json()
        assert comparison['status']=='complete' and len(comparison['cases'])==20
        baseline=client.get('/api/comparison/'+case+'/baseline')
        assert baseline.status_code==200 and baseline.json()['incident_id']==case
        assert client.get('/api/comparison/'+case+'/baseline-log').status_code==200
        assert client.get('/api/comparison/not-a-case/baseline').status_code==404
