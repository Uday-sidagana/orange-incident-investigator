import asyncio
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from orange_incident.channels import DeliveryFailure,LinearClient,SlackClient
from orange_incident.outbound import OutboundIntegrations
from orange_incident.server import create_app
from orange_incident.tickets import Conflict,TicketStore

ROOT=Path(__file__).resolve().parents[1]
COMPLAINT={'name':'Demo','email':'demo@example.invalid','company':'Atlas','title':'A demo integration incident',
           'description':'This is a fictional incident for integration verification.','scenario_id':'gmail-001'}


class FakeLinear:
    def __init__(self,fail=False,uncertain=False):
        self.created=[]
        self.updated=[]
        self.fail,self.uncertain=fail,uncertain
    async def create(self,ticket,description):
        if self.fail:
            raise DeliveryFailure('Simulated rejection',uncertain=self.uncertain)
        self.created.append(ticket['id'])
        return {'id':'issue-one','identifier':'DEMO-1','url':'https://linear.app/demo/issue/DEMO-1'}
    async def update(self,reference,description):
        self.updated.append((reference['id'],description))
        return reference
    async def close(self):
        pass


class FakeSlack:
    def __init__(self):
        self.messages=[]
        self.updates=[]
    async def post(self,text,*,thread_ts=None,channel_id=None,blocks=None):
        self.messages.append({'text':text,'thread_ts':thread_ts,'channel_id':channel_id,'blocks':blocks})
        return {'channel':channel_id or 'channel-one','ts':f'{len(self.messages)}.000001'}
    async def update(self,reference,text,*,blocks=None):
        self.updates.append({'reference':reference,'text':text,'blocks':blocks})
        return reference
    async def close(self):
        pass


def prepared(tmp_path):
    store=TicketStore(tmp_path/'inbox.sqlite')
    ticket_id,_=store.submit(COMPLAINT,'one')
    return store,store.get(ticket_id)


def test_outbox_deduplicates_root_and_reuses_linear_issue_and_slack_thread(tmp_path):
    store,ticket=prepared(tmp_path)
    linear,slack=FakeLinear(),FakeSlack()
    service=OutboundIntegrations(store,clients={'linear':linear,'slack':slack})
    service.enqueue(ticket,'intake')
    service.enqueue(ticket,'intake')
    service.enqueue(ticket,'report')
    async def drain():
        while await service.process_one():
            pass
    asyncio.run(drain())
    assert linear.created==[ticket['id']]
    assert len(linear.updated)==1 and linear.updated[0][0]=='issue-one'
    assert len(slack.messages)==2
    assert slack.messages[0]['thread_ts'] is None
    assert slack.messages[1]['thread_ts']=='1.000001'
    assert slack.messages[1]['channel_id']=='channel-one'
    assert len(slack.updates)==1 and slack.updates[0]['reference']['ts']=='1.000001'
    assert all(job['status']=='complete' for job in store.get(ticket['id'])['deliveries'])


def test_definite_failure_blocks_followup_then_manual_retry_unblocks(tmp_path):
    store,ticket=prepared(tmp_path)
    linear=FakeLinear(fail=True)
    service=OutboundIntegrations(store,clients={'linear':linear})
    service.enqueue(ticket,'intake')
    service.enqueue(ticket,'report')
    asyncio.run(service.process_one())
    asyncio.run(service.process_one())
    jobs=store.get(ticket['id'])['deliveries']
    assert [job['status'] for job in jobs]==['failed','blocked']
    linear.fail=False
    store.retry_delivery(jobs[0]['id'])
    asyncio.run(service.process_one())
    asyncio.run(service.process_one())
    assert len(linear.created)==1 and len(linear.updated)==1


def test_uncertain_creation_is_never_blindly_retried(tmp_path):
    store,ticket=prepared(tmp_path)
    service=OutboundIntegrations(store,clients={'linear':FakeLinear(fail=True,uncertain=True)})
    service.enqueue(ticket,'intake')
    asyncio.run(service.process_one())
    job=store.get(ticket['id'])['deliveries'][0]
    assert job['status']=='attention_required'
    with pytest.raises(Conflict):
        store.retry_delivery(job['id'])
    assert not asyncio.run(service.process_one())


def test_restart_does_not_resend_unacknowledged_create(tmp_path):
    store,ticket=prepared(tmp_path)
    store.enqueue_delivery(ticket['id'],'slack','intake')
    store.claim_delivery(['slack'])
    store.mark_deliveries_interrupted()
    assert store.get(ticket['id'])['deliveries'][0]['status']=='attention_required'
    assert store.claim_delivery(['slack']) is None


def test_slack_payload_disables_unfurl_and_unwanted_mentions():
    seen=[]
    def handle(request):
        import json
        payload=json.loads(request.content)
        seen.append(payload)
        return httpx.Response(200,json={'ok':True,'channel':'C-DEMO','ts':'1.0'})
    async def run():
        client=SlackClient('fake','C-DEMO',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        await client.post('Customer text <!channel> <@U123> & url',thread_ts='0.0')
        await client.close()
    asyncio.run(run())
    assert '<!channel>' not in seen[0]['text']
    assert seen[0]['mrkdwn'] is False and seen[0]['parse']=='none'
    assert seen[0]['thread_ts']=='0.0' and not seen[0]['unfurl_links']


def test_api_errors_and_timeout_are_redacted_and_classified():
    async def run():
        def deny(request):
            return httpx.Response(200,json={'ok':False,'error':'missing_scope','untrusted':'token-secret'})
        slack=SlackClient('token-secret','C',httpx.AsyncClient(transport=httpx.MockTransport(deny)))
        with pytest.raises(DeliveryFailure,match='missing_scope') as error:
            await slack.post('test')
        assert not error.value.uncertain and 'token-secret' not in str(error.value)
        await slack.close()
        def timeout(request):
            raise httpx.ReadTimeout('token-secret')
        linear=LinearClient('token-secret','11111111-1111-4111-8111-111111111111',httpx.AsyncClient(transport=httpx.MockTransport(timeout)))
        with pytest.raises(DeliveryFailure) as error:
            await linear.create({'complaint':{'title':'test'}},'test')
        assert error.value.uncertain and 'token-secret' not in str(error.value)
        await linear.close()
    asyncio.run(run())


def test_portal_investigation_is_independent_of_optional_delivery_failure(tmp_path):
    linear=FakeLinear(fail=True)
    app=create_app(ROOT,db_path=tmp_path/'inbox.sqlite',run_worker=False,plain_mode='simulated',runtime='simulation',outbound_clients={'linear':linear})
    with TestClient(app) as client:
        ticket=client.post('/api/tickets',json=COMPLAINT,headers={'Idempotency-Key':'one'}).json()['ticket']
        asyncio.run(app.state.process_next())
        assert client.get('/api/tickets/'+ticket['id']).json()['status']=='needs_review'
        asyncio.run(app.state.process_delivery())
        ready=client.get('/api/tickets/'+ticket['id']).json()
        assert ready['result']['approach']=='simulation' and ready['status']=='needs_review'
        assert ready['deliveries'][0]['status']=='failed'
        assert client.post('/api/tickets/'+ticket['id']+'/sync').status_code==202
        assert len(client.get('/api/tickets/'+ticket['id']).json()['deliveries'])==2


def test_config_without_enabled_flag_does_not_connect(tmp_path):
    store,ticket=prepared(tmp_path)
    service=OutboundIntegrations(store,config={'LINEAR_API_KEY':'fake','LINEAR_TEAM_ID':'fake'})
    service.enqueue(ticket,'intake')
    assert store.get(ticket['id'])['deliveries']==[]


def test_linear_personal_key_auth_and_issue_update_reference():
    requests=[]
    def handle(request):
        import json
        assert request.headers['authorization']=='test-personal-key'
        body=json.loads(request.content)
        requests.append(body)
        if 'CreateIncidentIssue' in body['query']:
            assert body['variables']['input']['teamId']=='11111111-1111-4111-8111-111111111111'
            return httpx.Response(200,json={'data':{'issueCreate':{'success':True,'issue':{'id':'issue-one','identifier':'DEMO-1','url':'https://linear.app/demo/issue/DEMO-1'}}}})
        assert body['variables']['id']=='issue-one'
        return httpx.Response(200,json={'data':{'issueUpdate':{'success':True,'issue':{'id':'issue-one'}}}})
    async def run():
        client=LinearClient('test-personal-key','11111111-1111-4111-8111-111111111111',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        reference=await client.create({'complaint':{'title':'Test incident'}},'Initial report')
        await client.update(reference,'Completed report')
        await client.close()
    asyncio.run(run())
    assert len(requests)==2


def test_read_only_slack_verification_checks_channel_membership():
    def handle(request):
        if request.url.path.endswith('auth.test'):
            return httpx.Response(200,json={'ok':True,'team':'Demo','bot_id':'BOT'})
        assert request.method=='GET'
        assert request.url.params['channel']=='C-DEMO'
        return httpx.Response(200,json={'ok':True,'channel':{'name':'orange-incidents','is_archived':False,'is_member':False}})
    async def run():
        client=SlackClient('test-only','C-DEMO',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        with pytest.raises(DeliveryFailure,match='Invite'):
            await client.verify()
        await client.close()
    asyncio.run(run())


def test_concurrent_delivery_claim_has_single_owner(tmp_path):
    store,ticket=prepared(tmp_path)
    store.enqueue_delivery(ticket['id'],'linear','intake')
    async def run():
        return await asyncio.gather(asyncio.to_thread(store.claim_delivery,['linear']),asyncio.to_thread(store.claim_delivery,['linear']))
    claimed=asyncio.run(run())
    assert sum(job is not None for job in claimed)==1


def test_linear_team_short_key_resolves_without_rewriting_credentials():
    def handle(request):
        return httpx.Response(200,json={'data':{'viewer':{'id':'viewer'},'teams':{'nodes':[{'id':'11111111-1111-4111-8111-111111111111','name':'Demo Team','key':'DEMO'}]}}})
    async def run():
        client=LinearClient('fake','DEMO',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        result=await client.verify()
        assert result['selected_team']['key']=='DEMO'
        assert client.team_id=='11111111-1111-4111-8111-111111111111'
        await client.close()
    asyncio.run(run())


def test_slack_app_level_token_explains_required_bot_token_without_network():
    def handle(request):
        pytest.fail('An app-level token should be rejected before channel calls')
    async def run():
        client=SlackClient('xapp-fake-test-only','C-DEMO',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        with pytest.raises(DeliveryFailure,match='Bot User OAuth Token'):
            await client.verify()
        await client.close()
    asyncio.run(run())


def test_slack_separates_authentication_from_optional_channel_read_scope():
    def handle(request):
        if request.url.path.endswith('auth.test'):
            return httpx.Response(200,json={'ok':True,'team':'Demo','bot_id':'BOT'})
        return httpx.Response(200,json={'ok':False,'error':'missing_scope'})
    async def run():
        client=SlackClient('fake','C-DEMO',httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        result=await client.verify()
        assert result['authentication_verified'] is True
        assert result['channel_read_verified'] is False and result['verified'] is False
        await client.close()
    asyncio.run(run())
