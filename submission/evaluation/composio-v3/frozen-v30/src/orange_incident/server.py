"""Local support-demo API with explicit simulated/live Plain modes."""
import asyncio
from contextlib import asynccontextmanager, suppress
import json
import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, field_validator
from dotenv import dotenv_values
from .models import StrictModel
from .tickets import Conflict, TicketStore


class Complaint(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    email: str = Field(min_length=3,max_length=254)
    company: str = Field(min_length=1,max_length=150)
    title: str = Field(min_length=5,max_length=200)
    description: str = Field(min_length=15,max_length=5000)
    scenario_id: str = Field(min_length=1,max_length=80)

    @field_validator('email')
    @classmethod
    def basic_email(cls,value):
        # Demo identity, not an email-verification service.
        if '@' not in value or any(c.isspace() for c in value):
            raise ValueError('Enter an email address')
        return value


class Reinvestigation(StrictModel):
    reason: str = Field(min_length=10,max_length=1000)


class Review(StrictModel):
    reviewer: Literal['human','assistant']='human'
    verdict: Literal['accepted','needs_work']
    notes: str = Field(default='',max_length=5000)


async def codex_investigator(ticket, root, output):
    from .baseline import investigate
    from .codex_provider import CodexProvider
    from .tools import Simulation
    simulation=Simulation(root/'data/incidents'/f"{ticket['complaint']['scenario_id']}.json")
    # The customer's actual complaint becomes the investigation input, not ignored fixture prose.
    simulation.incident.title=ticket['complaint']['title']
    simulation.incident.description=ticket['complaint']['description']
    provider=CodexProvider()
    try:
        result=await investigate(simulation,provider,json.loads((root/'data/rubric.json').read_text()),output,timeout_seconds=300)
        return result.model_dump()
    finally:
        await provider.close()


def create_app(root: Path | None = None, *, db_path: Path | None = None, run_worker=True, investigator=None, plain_client=None, plain_mode=None, runtime=None, outbound_clients=None, worker_count=None):
    root=(root or Path.cwd()).resolve()
    store=TicketStore(db_path or root/'runs/server/inbox.sqlite')
    cases={p.stem:json.loads(p.read_text())['incident'] for p in (root/'data/incidents').glob('*.json')}
    config=dotenv_values(root/'.env') if (root/'.env').exists() else {}
    plain_mode='live' if plain_client is not None else (plain_mode or os.environ.get('PLAIN_MODE') or config.get('PLAIN_MODE') or 'simulated')
    if plain_mode not in ('live','simulated'):
        raise ValueError('PLAIN_MODE must be live or simulated')
    if plain_mode == 'live' and plain_client is None:
        from .plain import PlainClient
        key=os.environ.get('PLAIN_API_KEY') or config.get('PLAIN_API_KEY')
        if not key:
            raise ValueError('PLAIN_MODE=live requires PLAIN_API_KEY')
        plain_client=PlainClient(key)
    runtime=runtime or os.environ.get('INVESTIGATION_RUNTIME') or config.get('INVESTIGATION_RUNTIME') or 'simulation'
    if runtime not in ('simulation','codex','openai'):
        raise ValueError('INVESTIGATION_RUNTIME must be simulation, openai, or codex')
    async def simulation_investigator(ticket,root,output):
        from .investigation import run_simulation
        from .tools import Simulation
        simulation=Simulation(root/'data/incidents'/f"{ticket['complaint']['scenario_id']}.json")
        simulation.incident.title=ticket['complaint']['title']
        simulation.incident.description=ticket['complaint']['description']
        def activity(event):
            with store.connect() as db:
                store.event(db,ticket['id'],event['event'],{k:v for k,v in event.items() if k!='event'})
        result,state=await run_simulation(simulation,output,event_sink=activity)
        payload=result.model_dump()
        payload['workflow']={'mode':state.mode,'tasks':[task.model_dump() for task in state.tasks],
                             'objections':state.objections,'followup_rounds':state.followup_rounds,'status':state.status}
        return payload
    async def openai_investigator(ticket,root,output):
        from .llm_agents import run_live_agents
        from .tools import Simulation
        simulation=Simulation(root/'data/incidents'/f"{ticket['complaint']['scenario_id']}.json")
        simulation.incident.title=ticket['complaint']['title']
        simulation.incident.description=ticket['complaint']['description']
        def activity(event):
            with store.connect() as db:
                store.event(db,ticket['id'],event['event'],{k:v for k,v in event.items() if k!='event'})
        result,state=await run_live_agents(simulation,output,root=root,event_sink=activity)
        payload=result.model_dump()
        payload['workflow']={'mode':state.mode,'tasks':[task.model_dump() for task in state.tasks],
                             'objections':state.objections,'followup_rounds':state.followup_rounds,'status':state.status}
        return payload
    selected=investigator or {'simulation':simulation_investigator,'openai':openai_investigator,'codex':codex_investigator}[runtime]
    from .outbound import OutboundIntegrations
    integration_keys=['LINEAR_API_KEY','LINEAR_TEAM_ID','LINEAR_ENABLED','SLACK_BOT_TOKEN','SLACK_CHANNEL_ID','SLACK_ENABLED']
    notifications=OutboundIntegrations(store,{key:os.environ.get(key) or config.get(key) for key in integration_keys},clients=outbound_clients)
    worker_count=worker_count or int(os.environ.get('INVESTIGATION_WORKERS') or config.get('INVESTIGATION_WORKERS') or 1)
    if not 1<=worker_count<=3:raise ValueError('INVESTIGATION_WORKERS must be between 1 and 3')
    active=asyncio.Lock()

    async def process_next():
        async with active:
            waiting=store.pending_plain() if plain_mode == 'live' else None
            if waiting:
                try:
                    thread=await plain_client.read_thread(waiting['plain']['thread_id'])
                    store.plain_confirmed(waiting['id'],thread)
                except Exception:
                    store.plain_failed(waiting['id'])
            ticket=store.claim()
        if ticket is None:
            return False
        notifications.enqueue(ticket,'intake')
        try:
            result=await selected(ticket,root,root/'runs/server'/ticket['id'])
            if result.get('run_status') != 'completed':
                store.finish(ticket['id'],result=result,error='Investigation did not complete. Review the trace before retrying.')
            else:
                store.finish(ticket['id'],result=result)
        except asyncio.CancelledError:
            store.finish(ticket['id'],error='Worker stopped before completion; retry explicitly')
            raise
        except Exception:
            # Provider diagnostics and credentials never enter public ticket errors.
            store.finish(ticket['id'],error='Investigation failed. Check local runtime configuration and retry.')
        finished=store.get(ticket['id'])
        stage='report' if finished['status']=='needs_review' else 'failure'
        attempt=sum(e['type']=='investigation_started' for e in finished['events'])
        if attempt>1:stage+=f'-run-{attempt}'
        notifications.enqueue(finished,stage)
        return True

    async def worker():
        while True:
            if not await process_next():
                await asyncio.sleep(0.5)

    async def delivery_worker():
        while True:
            if not await notifications.process_one():
                await asyncio.sleep(0.5)

    @asynccontextmanager
    async def lifespan(app):
        store.mark_interrupted()
        store.mark_deliveries_interrupted()
        tasks=([asyncio.create_task(worker()) for _ in range(worker_count)]+[asyncio.create_task(delivery_worker())]) if run_worker else []
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks,return_exceptions=True)
            if plain_client is not None:
                await plain_client.close()
            await notifications.close()

    app=FastAPI(title='Orange Support Operations',version='0.2.0',lifespan=lifespan)
    app.state.store=store
    app.state.process_next=process_next
    app.state.process_delivery=notifications.process_one

    @app.get('/api/health')
    def health():
        return {'status':'ok','plain_mode':plain_mode,'runtime':runtime,'architecture':{'simulation':'simulated_six_role_workflow','openai':'live_six_role_workflow','codex':'single_agent_baseline'}[runtime],
                'worker_enabled':run_worker,'worker_count':worker_count,'customer_replies_sent':False,'integrations':notifications.status}

    @app.get('/api/scenarios')
    def scenarios():
        # No expected causes, remediation labels, or raw fixture/evaluator data are exposed.
        return [{'id':key,'title':case['title'],'description':case['description']} for key,case in sorted(cases.items())]

    @app.post('/api/tickets',status_code=202)
    async def submit(complaint:Complaint,idempotency_key:Annotated[str,Header(min_length=1,max_length=100)]):
        if complaint.scenario_id not in cases:
            raise HTTPException(422,'Select an available simulated environment')
        try:
            ticket_id,created=store.submit(complaint.model_dump(),idempotency_key,plain_mode)
        except Conflict as exc:
            raise HTTPException(409,str(exc)) from None
        if created and plain_mode == 'live':
            try:
                delivery=await plain_client.create_thread(complaint.model_dump(),ticket_id)
                store.plain_created(ticket_id,**delivery)
            except Exception:
                store.plain_failed(ticket_id)
        return {'ticket':store.get(ticket_id),'created':created}

    @app.get('/api/tickets')
    def tickets(summary:bool=False):
        if summary:return store.summaries()
        return store.list()

    @app.get('/api/tickets/{ticket_id}')
    def ticket(ticket_id:UUID):
        value=store.get(str(ticket_id))
        if value is None:
            raise HTTPException(404,'Ticket not found')
        return value

    @app.get('/api/tickets/{ticket_id}/agent-log')
    def work_log(ticket_id:UUID):
        from .activity import agent_log
        value=store.get(str(ticket_id))
        if value is None:raise HTTPException(404,'Ticket not found')
        return agent_log(value)

    @app.get('/api/comparison')
    def comparison():
        path=root/'runs/composio-v3/comparison.json'
        return json.loads(path.read_text()) if path.exists() else {'status':'not_started','cases':[]}

    @app.get('/api/comparison/{case_id}/baseline')
    def comparison_baseline(case_id:str):
        allowed=json.loads((root/'evaluation/splits.json').read_text()).get('prospective_comparison',[])
        if case_id not in allowed:raise HTTPException(404,'Case not found')
        path=root/'runs/composio-v3/single_agent'/case_id/f'{case_id}.json'
        if not path.exists():raise HTTPException(404,'Baseline not complete')
        return json.loads(path.read_text())

    @app.get('/api/comparison/{case_id}/baseline-log')
    def baseline_log(case_id:str):
        allowed=json.loads((root/'evaluation/splits.json').read_text()).get('prospective_comparison',[])
        if case_id not in allowed:raise HTTPException(404,'Case not found')
        path=root/'runs/composio-v3/single_agent'/case_id/'traces/events.jsonl'
        if not path.exists():raise HTTPException(404,'Baseline not started')
        return {'case_id':case_id,'events':[json.loads(line) for line in path.read_text().splitlines()]}

    @app.post('/api/tickets/{ticket_id}/retry',status_code=202)
    def retry(ticket_id:UUID):
        try:
            store.retry(str(ticket_id))
        except KeyError:
            raise HTTPException(404,'Ticket not found') from None
        except Conflict as exc:
            raise HTTPException(409,str(exc)) from None
        return store.get(str(ticket_id))

    @app.post('/api/tickets/{ticket_id}/reinvestigate',status_code=202)
    def reinvestigate(ticket_id:UUID,request:Reinvestigation,idempotency_key:Annotated[str,Header(min_length=1,max_length=100)]):
        try:created=store.reinvestigate(str(ticket_id),idempotency_key,request.reason)
        except KeyError:raise HTTPException(404,'Ticket not found') from None
        except Conflict as exc:raise HTTPException(409,str(exc)) from None
        return {'created':created,'ticket':store.get(str(ticket_id))}

    @app.post('/api/tickets/{ticket_id}/reviews')
    def review(ticket_id:UUID,feedback:Review):
        try:
            store.review(str(ticket_id),feedback.verdict,feedback.notes,reviewer=feedback.reviewer)
        except KeyError:
            raise HTTPException(404,'Ticket not found') from None
        except Conflict as exc:
            raise HTTPException(409,str(exc)) from None
        ticket=store.get(str(ticket_id))
        sequence=ticket['events'][-1]['sequence']
        notifications.enqueue(ticket,f'review-{sequence}')
        return store.get(str(ticket_id))

    @app.get('/api/integrations')
    def integration_status():
        return notifications.status

    @app.post('/api/tickets/{ticket_id}/sync',status_code=202)
    def sync_ticket(ticket_id:UUID):
        ticket=store.get(str(ticket_id))
        if ticket is None:
            raise HTTPException(404,'Ticket not found')
        if not notifications.clients:
            raise HTTPException(409,'Configure and enable an integration first')
        if not any(event['type']=='investigation_queued' for event in ticket['events']):
            raise HTTPException(409,'Ticket has not reached the investigation queue')
        notifications.enqueue(ticket,'intake')
        if ticket.get('result'):
            notifications.enqueue(ticket,'report' if ticket['status']!='failed' else 'failure')
        return store.get(str(ticket_id))

    @app.post('/api/integrations/deliveries/{job_id}/retry',status_code=202)
    def retry_delivery(job_id:int):
        try:
            store.retry_delivery(job_id)
        except KeyError:
            raise HTTPException(404,'Delivery not found') from None
        except Conflict as exc:
            raise HTTPException(409,str(exc)) from None
        return {'queued':True}

    static=root/'web' 
    if static.exists():
        app.mount('/assets',StaticFiles(directory=static),name='assets')
        @app.get('/',include_in_schema=False)
        def index():
            return FileResponse(static/'index.html')
    return app
