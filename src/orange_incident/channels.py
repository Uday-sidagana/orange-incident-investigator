"""Linear and Slack HTTP adapters; no implicit retries of message/issue creation."""
import html
from uuid import UUID
import httpx


class DeliveryFailure(RuntimeError):
    def __init__(self,message,*,uncertain=False,code=None):
        super().__init__(message)
        self.uncertain=uncertain
        self.code=code


class LinearClient:
    def __init__(self,api_key,team_id='',client=None):
        self.api_key,self.team_id=api_key,team_id
        self.client=client or httpx.AsyncClient(timeout=20)

    async def graphql(self,query,variables=None,*,mutation=False):
        try:
            response=await self.client.post('https://api.linear.app/graphql',
                headers={'Authorization':self.api_key},json={'query':query,'variables':variables or {}})
        except httpx.RequestError:
            raise DeliveryFailure('Linear request could not be confirmed.',uncertain=mutation) from None
        if response.status_code>=500:
            raise DeliveryFailure('Linear service failed; inspect delivery before retrying.',uncertain=mutation)
        if response.status_code!=200:
            raise DeliveryFailure('Linear rejected the request. Check credentials, permissions, and rate limits.')
        try:
            body=response.json()
        except ValueError:
            raise DeliveryFailure('Linear returned an invalid response.',uncertain=mutation) from None
        if body.get('errors') or not isinstance(body.get('data'),dict):
            raise DeliveryFailure('Linear GraphQL operation failed. Check permissions and input.',uncertain=mutation)
        return body['data']

    async def verify(self):
        data=await self.graphql('query VerifyLinear { viewer { id } teams { nodes { id name key } } }')
        if not (data.get('viewer') or {}).get('id'):
            raise DeliveryFailure('Linear identity verification failed.')
        teams=(data.get('teams') or {}).get('nodes',[])
        selected=None
        if self.team_id:
            requested=self.team_id.strip().casefold()
            matches=[team for team in teams if requested in (team['id'].casefold(),team['name'].casefold(),team['key'].casefold())]
            if len(matches)!=1:
                raise DeliveryFailure('The configured Linear team must identify exactly one accessible team.')
            selected=matches[0]
            self.team_id=selected['id']
        return {'verified':True,'teams':teams,'selected_team':selected}

    async def create(self,ticket,description):
        try:
            UUID(self.team_id)
        except ValueError:
            await self.verify()
        data=await self.graphql('''mutation CreateIncidentIssue($input: IssueCreateInput!) {
            issueCreate(input:$input) { success issue { id identifier url } }
        }''',{'input':{'teamId':self.team_id,'title':ticket['complaint']['title'],'description':description}},mutation=True)
        result=data.get('issueCreate') or {}
        issue=result.get('issue') or {}
        if not result.get('success') or not issue.get('id'):
            raise DeliveryFailure('Linear did not confirm issue creation.',uncertain=True)
        return issue

    async def update(self,reference,description):
        data=await self.graphql('''mutation UpdateIncidentIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id:$id,input:$input) { success issue { id identifier url } }
        }''',{'id':reference['id'],'input':{'description':description}},mutation=True)
        result=data.get('issueUpdate') or {}
        if not result.get('success'):
            raise DeliveryFailure('Linear did not confirm the issue update.',uncertain=True)
        return result.get('issue') or reference

    async def close(self):
        await self.client.aclose()


class SlackClient:
    def __init__(self,token,channel_id='',client=None):
        self.token,self.channel_id=token,channel_id
        self.client=client or httpx.AsyncClient(timeout=20)

    async def call(self,method,payload=None,*,mutation=False):
        allowed={'auth.test','conversations.info','conversations.list','chat.postMessage','chat.update'}
        if method not in allowed:
            raise ValueError('Unsupported Slack operation')
        try:
            if method.startswith('conversations.'):
                response=await self.client.get('https://slack.com/api/'+method,
                    headers={'Authorization':f'Bearer {self.token}'},params=payload or {})
            else:
                response=await self.client.post('https://slack.com/api/'+method,
                    headers={'Authorization':f'Bearer {self.token}'},json=payload or {})
        except httpx.RequestError:
            raise DeliveryFailure('Slack delivery could not be confirmed.',uncertain=mutation) from None
        if response.status_code>=500:
            raise DeliveryFailure('Slack service failed; inspect delivery before retrying.',uncertain=mutation)
        if response.status_code!=200:
            raise DeliveryFailure('Slack rejected the HTTP request. Check configuration and rate limits.')
        try:
            data=response.json()
        except ValueError:
            raise DeliveryFailure('Slack returned an invalid response.',uncertain=mutation) from None
        if not data.get('ok'):
            safe={'invalid_auth','not_authed','token_revoked','missing_scope','not_in_channel','channel_not_found','is_archived','ratelimited','account_inactive','not_allowed_token_type'}
            reason=data.get('error') if data.get('error') in safe else 'request_rejected'
            raise DeliveryFailure(f'Slack: {reason}.',uncertain=mutation and data.get('error') not in safe,code=reason)
        return data

    async def verify(self):
        if self.token.startswith('xapp-'):
            raise DeliveryFailure('Slack requires the Bot User OAuth Token (xoxb-...), not an app-level token (xapp-...).')
        auth=await self.call('auth.test')
        result={'verified':True,'authentication_verified':True,'workspace':auth.get('team'),'bot_id':auth.get('bot_id')}
        if self.channel_id:
            try:
                channel=(await self.call('conversations.info',{'channel':self.channel_id})).get('channel') or {}
            except DeliveryFailure as exc:
                if exc.code!='missing_scope':
                    raise
                result.update(verified=False,channel_read_verified=False,
                    note='Authentication works. Channel metadata needs an optional read scope; verify posting separately with a controlled test.')
                return result
            if channel.get('is_archived') or not channel.get('is_member'):
                raise DeliveryFailure('Invite the Slack bot to the configured non-archived channel.')
            result['channel']=channel.get('name')
            result['channel_read_verified']=True
        return result

    async def find_channel(self,name):
        name=name.lstrip('#').casefold()
        cursor=''
        for _ in range(10):
            data=await self.call('conversations.list',{'types':'public_channel','exclude_archived':'true','limit':100,'cursor':cursor})
            matches=[channel for channel in data.get('channels',[]) if channel.get('name','').casefold()==name]
            if matches:
                return matches[0]['id']
            cursor=(data.get('response_metadata') or {}).get('next_cursor','')
            if not cursor:
                break
        raise DeliveryFailure('Public Slack channel not found. Supply its channel ID or check channel visibility.')

    async def post(self,text,*,thread_ts=None,channel_id=None,blocks=None):
        # Escape special Slack constructs from user content; do not notify arbitrary mentions.
        payload={'channel':channel_id or self.channel_id,'text':html.escape(text[:3800],quote=False),
                 'mrkdwn':False,'parse':'none','unfurl_links':False,'unfurl_media':False}
        if blocks is not None:
            payload['blocks']=blocks
        if thread_ts:
            payload['thread_ts']=thread_ts
        data=await self.call('chat.postMessage',payload,mutation=True)
        if not data.get('ts') or not data.get('channel'):
            raise DeliveryFailure('Slack did not confirm message creation.',uncertain=True)
        return {'channel':data['channel'],'ts':data['ts']}

    async def update(self,reference,text,*,blocks=None):
        payload={'channel':reference['channel'],'ts':reference['ts'],
                 'text':html.escape(text[:3800],quote=False)}
        if blocks is not None:
            payload['blocks']=blocks
        await self.call('chat.update',payload,mutation=True)
        return reference

    async def close(self):
        await self.client.aclose()
