import asyncio
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
import pytest
from orange_incident.plain import PlainClient, PlainFailure
from orange_incident.server import create_app
from orange_incident.tickets import TicketStore

ROOT=Path(__file__).resolve().parents[1]
COMPLAINT={'name':'Demo User','email':'demo@example.com','company':'Atlas','title':'Gmail failures across tenants',
           'description':'Gmail sends started failing after the release.', 'scenario_id':'gmail-001'}


def test_graphql_adapter_maps_customer_and_thread_and_reads_back():
    calls=[]
    def handle(request):
        import json
        body=json.loads(request.content)
        calls.append(body)
        assert request.headers['authorization']=='Bearer test-only'
        query=body['query']
        if 'UpsertCustomer(' in query:
            return httpx.Response(200,json={'data':{'upsertCustomer':{'customer':{'id':'c-demo'},'error':None}}})
        if 'CreateSupportThread(' in query:
            assert body['variables']['input']['externalId']=='ticket-local'
            return httpx.Response(200,json={'data':{'createThread':{'thread':{'id':'th-demo'},'error':None}}})
        return httpx.Response(200,json={'data':{'thread':{'id':'th-demo','externalId':'ticket-local','title':'From Plain','description':'From Plain body'}}})
    async def run():
        client=PlainClient('test-only',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        delivery=await client.create_thread(COMPLAINT,'ticket-local')
        assert delivery=={'thread_id':'th-demo','customer_id':'c-demo'}
        assert (await client.read_thread('th-demo'))['title']=='From Plain'
        await client.close()
    asyncio.run(run())
    assert len(calls)==3


def test_plain_failure_is_redacted_and_not_retried():
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(503,text='sensitive upstream diagnostic')
    async def run():
        client=PlainClient('test-only',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        with pytest.raises(PlainFailure) as exc:
            await client.create_thread(COMPLAINT,'ticket-local')
        assert 'sensitive' not in str(exc.value)
        await client.close()
    asyncio.run(run())
    assert len(calls)==1


class FakePlain:
    def __init__(self,fail=False):
        self.external_id=None
        self.creates=0
        self.reads=0
        self.fail=fail
    async def create_thread(self,complaint,external_id):
        self.creates+=1
        self.external_id=external_id
        if self.fail:
            raise PlainFailure('Simulated uncertain delivery')
        return {'thread_id':'thread-live-demo','customer_id':'customer-live-demo'}
    async def read_thread(self,thread_id):
        self.reads+=1
        return {'id':thread_id,'externalId':self.external_id,'title':'Title read from Plain','description':'Complaint read from Plain for investigation.'}
    async def close(self):
        pass


def test_live_handoff_requires_plain_read_before_investigation(tmp_path):
    plain=FakePlain()
    async def investigate(ticket,root,output):
        assert plain.reads==1
        assert ticket['complaint']['title']==COMPLAINT['title']
        assert ticket['complaint']['description']==COMPLAINT['description']
        assert ticket['plain']['summary']=='Complaint read from Plain for investigation.'
        return {'run_status':'completed','report':{'outcome':'inconclusive'},'trace':[]}
    app=create_app(ROOT,db_path=tmp_path/'db.sqlite',run_worker=False,plain_client=plain,investigator=investigate)
    with TestClient(app) as client:
        response=client.post('/api/tickets',json=COMPLAINT,headers={'Idempotency-Key':'key'})
        ticket_id=response.json()['ticket']['id']
        assert response.json()['ticket']['status']=='awaiting_plain_read'
        assert response.json()['ticket']['plain']['mode']=='live'
        assert app.state.store.claim() is None
        asyncio.run(app.state.process_next())
        ticket=client.get('/api/tickets/'+ticket_id).json()
        assert ticket['status']=='needs_review'
        assert any(e['type']=='plain_thread_read' for e in ticket['events'])
        client.post('/api/tickets',json=COMPLAINT,headers={'Idempotency-Key':'key'})
        assert plain.creates==1


def test_uncertain_plain_delivery_is_not_queued_or_blindly_retried(tmp_path):
    plain=FakePlain(fail=True)
    app=create_app(ROOT,db_path=tmp_path/'db.sqlite',run_worker=False,plain_client=plain)
    with TestClient(app) as client:
        for _ in range(2):
            result=client.post('/api/tickets',json=COMPLAINT,headers={'Idempotency-Key':'key'}).json()
        assert result['ticket']['status']=='plain_attention_required'
        assert app.state.store.claim() is None and plain.creates==1


def test_thread_correlation_prevents_cross_ticket_ingestion(tmp_path):
    store=TicketStore(tmp_path/'db.sqlite')
    ticket_id,_=store.submit(COMPLAINT,'one',plain_mode='live')
    store.plain_created(ticket_id,'thread-one','customer-one')
    with pytest.raises(ValueError,match='correlation'):
        store.plain_confirmed(ticket_id,{'id':'thread-two','externalId':ticket_id,'title':'Wrong'})
    assert store.get(ticket_id)['status']=='awaiting_plain_read'


def test_generated_plain_summary_does_not_replace_immutable_customer_question(tmp_path):
    store=TicketStore(tmp_path/'inbox.sqlite')
    ticket_id,_=store.submit(COMPLAINT,'original',plain_mode='live')
    store.plain_created(ticket_id,'thread-original','customer-original')
    store.plain_confirmed(ticket_id,{'id':'thread-original','externalId':ticket_id,'title':'AI-generated title','description':'An inferred cause from an AI summary.',
                                    'original_messages':[{'entry_id':'message-original','text':COMPLAINT['description']}]})
    ticket=store.get(ticket_id)
    assert ticket['complaint']==ticket['original_complaint']==COMPLAINT
    assert ticket['plain']['summary']=='An inferred cause from an AI summary.'
    event=next(e for e in ticket['events'] if e['type']=='plain_thread_read')
    assert event['payload']['original_plain_message_verified'] and event['payload']['summary_differs_from_original']
