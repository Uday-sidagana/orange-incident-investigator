"""Plain GraphQL adapter. No blind retries of thread-creation mutations."""
import httpx

ENDPOINT='https://core-api.uk.plain.com/graphql/v1'


class PlainFailure(RuntimeError):
    pass


class PlainClient:
    def __init__(self,api_key,client=None):
        self.client=client or httpx.AsyncClient(timeout=20)
        self.api_key=api_key

    async def graphql(self,query,variables=None):
        try:
            response=await self.client.post(ENDPOINT,headers={'Authorization':f'Bearer {self.api_key}'},
                json={'query':query,'variables':variables or {}})
            response.raise_for_status()
            body=response.json()
        except Exception:
            raise PlainFailure('Plain request failed; delivery may be uncertain. Do not blindly resubmit.') from None
        if body.get('errors') or not isinstance(body.get('data'),dict):
            raise PlainFailure('Plain rejected the GraphQL request. Check API permissions and configuration.')
        return body['data']

    async def verify(self):
        data=await self.graphql('query VerifyIdentity { myMachineUser { id } }')
        if not (data.get('myMachineUser') or {}).get('id'):
            raise PlainFailure('Plain did not return a machine-user identity')
        return True

    async def create_thread(self,complaint,external_id):
        customer=await self.graphql('''mutation UpsertCustomer($input: UpsertCustomerInput!) {
          upsertCustomer(input:$input) { customer { id } error { code } }
        }''',{'input':{'identifier':{'emailAddress':complaint['email']},
            'onCreate':{'fullName':complaint['name'],'email':{'email':complaint['email'],'isVerified':False}},
            'onUpdate':{}}})
        value=customer.get('upsertCustomer',{})
        if value.get('error') or not (value.get('customer') or {}).get('id'):
            raise PlainFailure('Plain customer upsert failed. Check customer permissions.')
        customer_id=value['customer']['id']
        thread=await self.graphql('''mutation CreateSupportThread($input: CreateThreadInput!) {
          createThread(input:$input) { thread { id externalId } error { code } }
        }''',{'input':{'customerIdentifier':{'customerId':customer_id},'title':complaint['title'],
            'description':complaint['description'],'externalId':external_id,
            'components':[{'componentText':{'text':complaint['description']}}]}})
        value=thread.get('createThread',{})
        if value.get('error') or not (value.get('thread') or {}).get('id'):
            raise PlainFailure('Plain thread creation failed. Inspect Plain before retrying.')
        return {'thread_id':value['thread']['id'],'customer_id':customer_id}

    async def read_thread(self,thread_id):
        data=await self.graphql('''query ReadSupportThread($id: ID!) {
          thread(threadId:$id) { id externalId title description customer { id } }
        }''',{'id':thread_id})
        if not data.get('thread'):
            raise PlainFailure('Plain thread could not be read')
        return data['thread']

    async def close(self):
        await self.client.aclose()
