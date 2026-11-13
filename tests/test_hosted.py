import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from functools import partial
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from orange_incident.server import create_app
from orange_incident.hosted import create_entrypoint,publish_work,create_service
from orange_incident.tickets import TicketStore,Conflict
from orange_incident.cloud_worker import investigate,deliver

ROOT=Path(__file__).resolve().parents[1]
BODY={'name':'Hosted Demo','email':'hosted@example.com','company':'Demo','title':'Gmail incident from hosted intake','description':'Gmail messages have stopped sending for several customers.','scenario_id':'gmail-001'}
PASSWORD='private-review-password-1234'

@pytest.fixture(params=['sqlite','postgres'])
def store(request,tmp_path):
    if request.param=='sqlite':yield TicketStore(tmp_path/'inbox.sqlite');return
    url=os.environ.get('POSTGRES_TEST_URL')
    if not url:pytest.skip('Set POSTGRES_TEST_URL to run real Postgres contract tests')
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from orange_incident.postgres import PostgresTicketStore
    schema='test_'+uuid4().hex
    with psycopg.connect(url,autocommit=True) as db:db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:yield PostgresTicketStore(make_conninfo(url,options=f'-c search_path={schema}'))
    finally:
        with psycopg.connect(url,autocommit=True) as db:db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_store_targeted_claim_is_atomic_and_preserves_paid_work_lease(store):
    a,_=store.submit(BODY,'one');b,_=store.submit(BODY,'two')
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:store.claim(a,lease_seconds=280),range(2)))
    claims=[r for r in results if r]
    assert len(claims)==1 and claims[0]['id']==a
    assert store.get(b)['status']=='queued'
    old_token=claims[0]['_work_token']
    assert not store.expire_hosted_work(a)
    with store.connect() as db:db.execute('UPDATE tickets SET work_deadline=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),a))
    assert store.expire_hosted_work(a)
    assert store.get(a)['status']=='failed'
    store.retry(a);new=store.claim(a,lease_seconds=280)
    assert not store.finish(a,error='late result from old worker',work_token=old_token)
    assert store.get(a)['status']=='investigating'
    assert store.finish(a,result={'report':{'outcome':'inconclusive'}},work_token=new['_work_token'])
    assert store.get(a)['status']=='needs_review'


def test_postgres_compatible_idempotency_delivery_and_review_contract(store):
    tid,created=store.submit(BODY,'same');assert created
    assert store.submit(BODY,'same')==(tid,False)
    with pytest.raises(Conflict):store.submit(dict(BODY,title='Another incident'),'same')
    other,_=store.submit(BODY,'other')
    store.enqueue_delivery(other,'slack','intake')
    store.enqueue_delivery(tid,'slack','intake');store.enqueue_delivery(tid,'slack','intake')
    job=store.claim_delivery(['slack'],ticket_id=tid)
    assert job['ticket_id']==tid
    store.delivery_complete(job,{'channel':'test','ts':'1'})
    assert store.delivery_reference(tid,'slack')['ts']=='1'
    assert len(store.get(tid)['deliveries'])==1
    assert store.claim_delivery(['slack'],ticket_id=tid) is None
    store.finish(tid,result={'report':{'outcome':'inconclusive'}})
    store.review(tid,'accepted','Reviewed')
    assert store.get(tid)['status']=='reviewed'
    assert len(store.summaries())==2


def test_expired_delivery_is_not_blindly_replayed(store):
    tid,_=store.submit(BODY,'one');store.enqueue_delivery(tid,'slack','intake')
    job=store.claim_delivery(['slack'],ticket_id=tid)
    with store.connect() as db:db.execute('UPDATE delivery_jobs SET updated_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=121)).isoformat(),job['id']))
    store.expire_hosted_deliveries(tid)
    assert store.get(tid)['deliveries'][0]['status']=='attention_required'
    assert store.claim_delivery(['slack'],ticket_id=tid) is None
    with pytest.raises(Conflict):store.retry_delivery(job['id'])


def test_hosted_authentication_precedes_database_and_blocks_cross_site_writes(tmp_path,monkeypatch):
    calls=[]
    def factory(root):
        calls.append(root)
        return create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',hosted=True)
    monkeypatch.setenv('DATABASE_URL','postgresql://not-contacted')
    monkeypatch.setenv('DEMO_PASSWORD',PASSWORD)
    app=create_entrypoint(ROOT,factory)
    with TestClient(app) as client:
        for route in ['/','/assets/app.js','/api/tickets','/api/health','/docs']:
            response=client.get(route);assert response.status_code==401
        assert calls==[]
        assert client.get('/healthz').status_code==200
        auth=('reviewer',PASSWORD)
        assert client.get('/api/scenarios',auth=auth).status_code==200
        assert len(calls)==1
        assert client.get('/api/scenarios',auth=auth).headers['cache-control']=='private, no-store'
        assert client.post('/api/tickets',json=BODY,auth=auth,headers={'Origin':'https://attacker.example','Idempotency-Key':'one'}).status_code==403
        assert client.post('/api/tickets',json=BODY,auth=auth,headers={'Origin':'http://testserver','Idempotency-Key':'one'}).status_code==202


def test_entrypoint_fails_closed_without_secrets_and_never_initializes_database(monkeypatch):
    monkeypatch.delenv('DEMO_PASSWORD',raising=False);monkeypatch.delenv('DATABASE_URL',raising=False)
    def fail(root):raise AssertionError('Must not initialize a database on import or before authentication')
    with TestClient(create_entrypoint(ROOT,fail)) as client:
        assert client.get('/').status_code==503
        assert client.get('/healthz').json()['status']=='setup_required'
    monkeypatch.setenv('DEMO_PASSWORD','too-short')
    with TestClient(create_entrypoint(ROOT,fail)) as client:assert client.get('/').status_code==503


def test_queue_publish_failure_keeps_same_ticket_and_allows_explicit_dispatch(tmp_path):
    calls=[]
    async def dispatch(tid,kind):
        calls.append((tid,kind))
        if len(calls)==1:raise RuntimeError('provider-secret-should-not-escape')
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',hosted=True,dispatch=dispatch)
    with TestClient(app) as client:
        first=client.post('/api/tickets',json=BODY,headers={'Idempotency-Key':'stable'})
        assert first.status_code==503 and 'provider-secret' not in first.text
        retry=client.post('/api/tickets',json=BODY,headers={'Idempotency-Key':'stable'})
        assert retry.status_code==202 and not retry.json()['created']
        assert len(client.get('/api/tickets').json())==1
        tid=retry.json()['ticket']['id']
        assert client.post('/api/tickets/'+tid+'/dispatch').status_code==202
        assert calls[0][0]==calls[1][0]==tid


def test_hosted_cold_start_does_not_interrupt_running_work(tmp_path):
    store=TicketStore(tmp_path/'inbox.sqlite');tid,_=store.submit(BODY,'one');store.claim(tid,lease_seconds=280)
    app=create_app(ROOT,store=store,run_worker=False,hosted=True,plain_mode='simulated')
    with TestClient(app):assert store.get(tid)['status']=='investigating'


def test_queue_redelivery_does_not_repeat_completed_paid_inference(store):
    calls=[];dispatches=[]
    async def investigator(ticket,root,output):
        calls.append(ticket['id']);assert str(output).startswith('/');return {'run_status':'completed','report':{'outcome':'inconclusive'},'trace':[]}
    def factory(root,store=None,output_root=None):
        async def dispatch(tid,kind):dispatches.append((tid,kind))
        return create_app(root,store=store,output_root=output_root,run_worker=False,hosted=True,plain_mode='simulated',investigator=investigator,dispatch=dispatch)
    tid,_=store.submit(BODY,'one');other,_=store.submit(BODY,'other')
    async def publish(tid,kind):dispatches.append((tid,kind))
    asyncio.run(investigate(tid,root=ROOT,store=store,factory=factory,publish=publish))
    asyncio.run(investigate(tid,root=ROOT,store=store,factory=factory,publish=publish))
    assert calls==[tid] and store.get(tid)['status']=='needs_review'
    assert store.get(other)['status']=='queued'
    assert all(kind=='deliver' for _,kind in dispatches)


def test_publish_uses_stable_queue_deduplication_key(tmp_path,monkeypatch):
    import sys
    sends=[]
    async def send(topic,payload,**options):sends.append((topic,payload,options));return 'test-message'
    monkeypatch.setitem(sys.modules,'vercel.queue',SimpleNamespace(send=send))
    store=TicketStore(tmp_path/'inbox.sqlite');tid,_=store.submit(BODY,'one')
    asyncio.run(publish_work(store,tid,'investigate'));asyncio.run(publish_work(store,tid,'investigate'))
    assert sends[0][2]['idempotency_key']==sends[1][2]['idempotency_key']
    store.claim(tid);store.finish(tid,error='test failure');store.retry(tid)
    asyncio.run(publish_work(store,tid,'investigate'))
    assert sends[-1][2]['idempotency_key']!=sends[0][2]['idempotency_key']


def test_active_invocation_is_not_replaced_by_redelivery(store):
    tid,_=store.submit(BODY,'active');store.claim(tid,lease_seconds=280)
    def factory(root,store=None,output_root=None):
        return create_app(root,store=store,run_worker=False,hosted=True,plain_mode='simulated',output_root=output_root)
    with pytest.raises(RuntimeError,match='holds the investigation lease'):
        asyncio.run(investigate(tid,root=ROOT,store=store,factory=factory))
    assert store.get(tid)['status']=='investigating'
    assert sum(e['type']=='investigation_started' for e in store.get(tid)['events'])==1


def test_hosted_gpt_deadline_fits_hobby_function_limit(tmp_path,monkeypatch):
    from orange_incident.contracts import Submission
    from orange_incident.models import InvestigationReport
    import orange_incident.llm_agents as agents
    observed=[]
    async def run(simulation,output,*,root,event_sink,limits):
        observed.append(limits.timeout_seconds)
        report=InvestigationReport(incident_id=simulation.incident.id,outcome='inconclusive',hypotheses=[],recommended_actions=['Collect missing evidence'],limitations=['Test transport'])
        result=Submission(incident_id=simulation.incident.id,approach='multi_agent',run_status='completed',report=report)
        state=SimpleNamespace(mode='live_agents',tasks=[],objections=[],followup_rounds=0,status='inconclusive')
        return result,state
    monkeypatch.setattr(agents,'run_live_agents',run)
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,hosted=True,plain_mode='simulated',runtime='openai')
    tid,_=app.state.store.submit(BODY,'one')
    asyncio.run(app.state.process_next(tid))
    assert observed==[240] and app.state.store.get(tid)['status']=='needs_review'


def test_interrupted_plain_creation_requires_inspection_not_duplicate_create(store):
    tid,_=store.submit(BODY,'plain','live')
    assert not store.expire_hosted_plain(tid)
    with store.connect() as db:db.execute('UPDATE tickets SET updated_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=121)).isoformat(),tid))
    assert store.expire_hosted_plain(tid)
    assert store.get(tid)['status']=='plain_attention_required'
    assert store.claim(tid,lease_seconds=280) is None
    assert not store.get(tid)['events'][-1]['payload']['blind_retry_allowed']
