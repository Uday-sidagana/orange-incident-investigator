"""Scripted scheduling demo, not model reasoning or an evaluation baseline."""
from pathlib import Path
from .engine import AgentResult, Engine, Task
from .models import InvestigationReport, Query
from .tools import Simulation


async def scripted_agent(task, state, tools):
    if task.role == 'orchestrator':
        return AgentResult(followups=[
            Task(id='observe', role='observability', question='Collect logs and metrics'),
            Task(id='changes', role='dependency', question='Collect changes and dependencies'),
            Task(id='reason', role='reasoning', question='Retrieve background', dependencies=['observe', 'changes']),
            Task(id='challenge', role='critic', question='Request omitted evidence', dependencies=['reason']),
        ])
    if task.role == 'observability':
        for tool in ['logs', 'metrics']:
            await tools.query(Query(tool=tool))
    elif task.role == 'dependency':
        names = ['deployments', 'dependencies'] if task.id == 'changes' else ['reproduce']
        for tool in names:
            await tools.query(Query(tool=tool))
    elif task.role == 'reasoning':
        for tool in ['history', 'knowledge']:
            await tools.query(Query(tool=tool))
    elif task.role == 'critic':
        return AgentResult(objections=['Scripted check: controlled reproduction has not been collected.'], followups=[
            Task(id='reproduce', role='dependency', question='Collect available sandbox reproduction records'),
            Task(id='report', role='reporting', question='Summarize workflow limitations', dependencies=['reproduce']),
        ])
    elif task.role == 'reporting':
        return AgentResult(report=InvestigationReport(
            incident_id=state.incident.id, outcome='inconclusive', hypotheses=[], recommended_actions=[],
            limitations=['Scripted workflow only; no model evaluated hypotheses or diagnosed the incident.']))
    return AgentResult()


async def workflow_demo(fixture: Path, output: Path):
    sim = Simulation(fixture)
    roles = ['orchestrator', 'observability', 'dependency', 'reasoning', 'critic', 'reporting']
    engine = Engine(sim.incident, sim.query, {role: scripted_agent for role in roles})
    return await engine.run([Task(id='plan', role='orchestrator', question='Schedule demonstration')], output)
