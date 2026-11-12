"""Matched single-model investigator using the team's provider, tools and validators."""
import asyncio
import json
from pathlib import Path
from time import monotonic
from typing import Literal
from pydantic import Field
from .contracts import Diagnosis, Submission
from .engine import Engine, Limits, ToolAccess
from .llm_agents import AgentProvider, LivePolicies, ModelLimits, configuration, CURRENT_TASK
from .models import InvestigationReport, StrictModel, Query
from .provider import ProviderFailure


class SingleTask(StrictModel):
    id: str='single-agent'
    role: Literal['single_agent']='single_agent'
    question: str='Investigate the incident, compare explanations, gather verification and produce an evidence-backed report.'
    dependencies: list[str]=Field(default_factory=list)
    status: str='running'


class SingleAccess(ToolAccess):
    ALLOWED={'single_agent':set(Query.model_fields['tool'].annotation.__args__)}


async def run_single_agent(simulation,output,*,root=None,model='gpt-5.4',provider=None,limits=None,event_sink=None):
    root=Path(root or Path.cwd()); output=Path(output); started=monotonic()
    (output/'traces').mkdir(parents=True,exist_ok=True)
    owned=provider is None
    if owned:
        key,_=configuration(root)
        provider=AgentProvider(key,{'single_agent':model},limits=ModelLimits(max_collection_rounds=20,max_queries_per_task=24))
    def record(event):
        with (output/'traces/events.jsonl').open('a') as journal:journal.write(json.dumps(event)+'\n')
        if event_sink:event_sink(event)
    engine=Engine(simulation.incident,simulation.query,{},limits=limits or Limits(timeout_seconds=360),mode='live_agents',event_sink=record)
    provider.event_sink=engine.emit
    rubric=json.loads((root/'data/rubric.json').read_text()); policies=LivePolicies(provider,rubric)
    task=SingleTask(); diagnosis=None; errors=[]
    token=CURRENT_TASK.set(task.id)
    async def investigate():
        nonlocal diagnosis
        engine.emit({'event':'task_started','task':task.id,'role':task.role,'question':task.question,'available_evidence_ids':[]})
        state=await policies.collect(task,engine.state,SingleAccess(engine,'single_agent',task.id))
        diagnosis=await policies.validated_decision(task,state,Diagnosis,'''You are one autonomous investigator, not a multi-agent team. Produce the final investigation report after checking alternative causes and your own verification gaps. Rank hypotheses and cause codes together. Use public vocabulary definitions, exact observed citations, qualitative confidence and proposed actions. A probable cause requires a supported mechanism and adequate discriminating evidence, not a verified production fix. Remain inconclusive if material evidence is missing. Do not claim remediation occurred. Distinguish facts from assumptions. Keep the report concise.''')
        if diagnosis.report.incident_id!=simulation.incident.id:raise ProviderFailure('Wrong report incident')
        engine.emit({'event':'agent_result','task':task.id,'role':task.role,'result':diagnosis.model_dump()})
        engine.emit({'event':'task_finished','task':task.id,'role':task.role,'status':'complete'})
    try:
        await asyncio.wait_for(investigate(),engine.limits.timeout_seconds)
    except (ProviderFailure,TimeoutError,ValueError,RuntimeError) as exc:
        errors.append(str(exc) if isinstance(exc,ProviderFailure) else type(exc).__name__)
        diagnosis=None
        engine.emit({'event':'task_finished','task':task.id,'role':task.role,'status':'failed','error':errors[-1]})
    finally:
        (output/'traces/model-calls.json').write_text(json.dumps({'models':provider.models,'limits':provider.limits.model_dump(),'calls':provider.calls},indent=2)+'\n')
        if owned:await provider.close()
        CURRENT_TASK.reset(token)
    report=diagnosis.report if diagnosis else InvestigationReport(incident_id=simulation.incident.id,outcome='inconclusive',hypotheses=[],recommended_actions=['Review execution failure and obtain missing evidence.'],limitations=errors or ['No valid report'])
    usage=[c['usage'] for c in provider.calls if c.get('usage')]
    result=Submission(incident_id=simulation.incident.id,approach='single_agent',run_status='completed' if diagnosis else 'failed',report=report,
                      ranked_cause_codes=diagnosis.ranked_cause_codes if diagnosis else [],findings=diagnosis.findings if diagnosis else [],action_codes=diagnosis.action_codes if diagnosis else [],
                      trace=engine.state.evidence,latency_seconds=monotonic()-started,input_tokens=sum(u['input_tokens'] for u in usage) if usage else None,
                      output_tokens=sum(u['output_tokens'] for u in usage) if usage else None)
    (output/f'{simulation.incident.id}.json').write_text(result.model_dump_json(indent=2)+'\n')
    return result
