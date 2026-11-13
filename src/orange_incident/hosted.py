"""Password-protected Vercel entrypoint and durable queue dispatch.

No database connection, secret or worker is required at build/import time.
"""
import asyncio
import base64
import hashlib
import hmac
import os
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI
from starlette.responses import JSONResponse,Response
from .server import create_app

TOPICS={'investigate':'orange-investigations','deliver':'orange-deliveries'}


def required_settings():
    missing=[key for key in ('DATABASE_URL','DEMO_PASSWORD') if not os.environ.get(key)]
    if os.environ.get('DEMO_PASSWORD') and len(os.environ['DEMO_PASSWORD'])<16:missing.append('DEMO_PASSWORD (at least 16 characters)')
    runtime=os.environ.get('INVESTIGATION_RUNTIME','openai')
    if runtime not in ('openai','simulation'):missing.append('INVESTIGATION_RUNTIME (openai or simulation)')
    if os.environ.get('PLAIN_MODE')=='live' and not os.environ.get('PLAIN_API_KEY'):missing.append('PLAIN_API_KEY')
    for provider,names in [('LINEAR',('LINEAR_API_KEY','LINEAR_TEAM_ID')),('SLACK',('SLACK_BOT_TOKEN','SLACK_CHANNEL_ID'))]:
        if os.environ.get(provider+'_ENABLED','false').lower()=='true':missing.extend(name for name in names if not os.environ.get(name))
    if runtime=='openai' and not os.environ.get('OPENAI_API_KEY'):missing.append('OPENAI_API_KEY')
    return missing


def create_service(root,*,store=None,dispatch=None,output_root=None,investigator=None):
    if store is None:
        from .postgres import PostgresTicketStore
        store=PostgresTicketStore(os.environ['DATABASE_URL'])
    if dispatch is None:
        async def dispatch(ticket_id,kind):await publish_work(store,ticket_id,kind)
    return create_app(Path(root),store=store,dispatch=dispatch,hosted=True,run_worker=False,
                      runtime=os.environ.get('INVESTIGATION_RUNTIME','openai'),
                      output_root=output_root,investigator=investigator)


async def publish_work(store,ticket_id,kind):
    from vercel.queue import send
    ticket=store.get(ticket_id)
    if ticket is None:raise ValueError('Unknown ticket')
    generation=max((e['sequence'] for e in ticket['events'] if e['type'] in
                    ('investigation_queued','delivery_queued','delivery_requeued','review_recorded')),default=0)
    key=hashlib.sha256(f'{kind}:{ticket_id}:{generation}'.encode()).hexdigest()
    message_id=await send(TOPICS[kind],{'ticket_id':ticket_id},idempotency_key=key)
    with store.connect() as db:
        store.event(db,ticket_id,'job_dispatched',{'kind':kind,'message_id':message_id})


class HostedApplication:
    def __init__(self,root,factory=None):
        self.root=Path(root);self.factory=factory or create_service;self.inner=None;self.lock=asyncio.Lock()

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return
        headers={k.decode().lower():v.decode() for k,v in scope.get('headers',[])}
        if scope.get('path')=='/healthz':
            missing=required_settings()
            response=JSONResponse({'status':'setup_required' if missing else 'ok','deployment':'vercel','missing':missing},status_code=503 if missing else 200)
            await response(scope,receive,send);return
        password=os.environ.get('DEMO_PASSWORD','')
        if len(password)<16:
            await JSONResponse({'detail':'Configure a DEMO_PASSWORD of at least 16 characters before enabling this deployment.'},status_code=503)(scope,receive,send);return
        authenticated=False
        try:
            scheme,encoded=headers.get('authorization','').split(' ',1)
            username,supplied=base64.b64decode(encoded,validate=True).decode().split(':',1)
            authenticated=(scheme.lower()=='basic' and hmac.compare_digest(username.encode(),os.environ.get('DEMO_USERNAME','reviewer').encode()) and hmac.compare_digest(supplied.encode(),password.encode()))
        except (ValueError,UnicodeError):pass
        if not authenticated:
            await Response('Sign in to the private incident demo.',status_code=401,headers={'WWW-Authenticate':'Basic realm="Incident investigation demo", charset="UTF-8"','Cache-Control':'no-store'})(scope,receive,send);return
        if scope.get('method') not in ('GET','HEAD','OPTIONS'):
            origin=headers.get('origin')
            if headers.get('sec-fetch-site')=='cross-site' or (origin and urlsplit(origin).netloc!=headers.get('host')):
                await JSONResponse({'detail':'Cross-site write rejected.'},status_code=403)(scope,receive,send);return
        if required_settings():
            await JSONResponse({'detail':'Hosted configuration is incomplete. Check deployment environment variables.'},status_code=503)(scope,receive,send);return
        if self.inner is None:
            async with self.lock:
                if self.inner is None:
                    try:self.inner=self.factory(self.root)
                    except Exception:
                        await JSONResponse({'detail':'Hosted storage is not ready. Check the database configuration.'},status_code=503)(scope,receive,send);return
        async def protected_send(message):
            if message['type']=='http.response.start':
                message={**message,'headers':list(message.get('headers',[]))+[(b'cache-control',b'private, no-store'),(b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'DENY')]}
            await send(message)
        await self.inner(scope,receive,protected_send)


def create_entrypoint(root,factory=None):
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.mount('/',HostedApplication(root,factory))
    return app
