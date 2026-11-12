"""Model-independent scheduling and persistence. Agents receive snapshots, not fixtures."""
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
from typing import Literal
from .models import Incident, InvestigationReport, Hypothesis, Query, StrictModel, ToolResult
from pydantic import Field
from .contracts import Candidate, Finding

Role = Literal['orchestrator', 'observability', 'dependency', 'reasoning', 'critic', 'reporting']


class Task(StrictModel):
    id: str
    role: Role
    question: str
    dependencies: list[str] = Field(default_factory=list)
    status: Literal['pending', 'running', 'complete', 'failed', 'skipped'] = 'pending'
    error: str | None = None


class Limits(StrictModel):
    max_tasks: int = Field(default=20, ge=1)
    max_tool_calls: int = Field(default=24, ge=1)
    max_followup_rounds: int = Field(default=2, ge=0)
    max_attempts: int = Field(default=2, ge=1, le=3)
    timeout_seconds: float = Field(default=60, gt=0)


class AgentResult(StrictModel):
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    followups: list[Task] = Field(default_factory=list)
    report: InvestigationReport | None = None
    notes: list[str] = Field(default_factory=list)
    candidates: list[Candidate] | None = None
    findings: list[Finding] | None = None


class State(StrictModel):
    incident: Incident
    mode: Literal['scripted_workflow', 'deterministic_simulation', 'live_agents']
    tasks: list[Task] = Field(default_factory=list)
    evidence: list[ToolResult] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    report: InvestigationReport | None = None
    tool_calls: int = 0
    followup_rounds: int = 0
    status: Literal['running', 'complete', 'inconclusive'] = 'running'
    candidates: list[Candidate] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class BudgetExceeded(RuntimeError):
    pass


class ToolAccess:
    """Per-role capability boundary. Calls and retries share one global budget."""
    ALLOWED = {
        'orchestrator': set(),
        'observability': {'logs', 'metrics', 'connections', 'refresh_history'},
        'dependency': {'deployments', 'dependencies', 'reproduce'},
        'reasoning': {'history', 'knowledge'},
        'critic': set(), 'reporting': set(),
    }

    def __init__(self, engine, role: Role, task_id=None):
        self.engine, self.role, self.task_id = engine, role, task_id

    async def query(self, query: Query) -> ToolResult:
        if query.tool not in self.ALLOWED[self.role]:
            raise PermissionError(f'{self.role} cannot use {query.tool}')
        for _ in range(self.engine.limits.max_attempts):
            # No await between checking and reserving: atomic in this event loop.
            if self.engine.state.tool_calls >= self.engine.limits.max_tool_calls:
                raise BudgetExceeded('Tool-call budget exhausted')
            self.engine.state.tool_calls += 1
            self.engine.emit({'event':'tool_started','role':self.role,'task':self.task_id,'query':query.model_dump()})
            result = await self.engine.tool(query)
            self.engine.state.evidence.append(result)
            self.engine.emit({'event':'tool_finished','role':self.role,'task':self.task_id,'tool':query.tool,'status':result.status,'evidence_id':result.evidence_id,'records':len(result.records),'result':result.model_dump()})
            if not result.error or not result.error.retryable:
                return result
        return result


Agent = Callable[[Task, State, ToolAccess], Awaitable[AgentResult]]


class Engine:
    def __init__(self, incident: Incident, tool, agents: dict[str, Agent],
                 limits: Limits | None = None, mode='scripted_workflow', event_sink=None):
        self.state = State(incident=incident, mode=mode)
        self.tool, self.agents = tool, agents
        self.limits = limits or Limits()
        self.event_sink = event_sink

    def emit(self, event):
        self.state.events.append(event)
        if self.event_sink:
            try:
                self.event_sink(event)
            except Exception:
                message='Investigation activity could not be persisted'
                if message not in self.state.limitations:
                    self.state.limitations.append(message)

    def add_tasks(self, tasks: list[Task]):
        ids = [task.id for task in self.state.tasks] + [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError('Task IDs must be unique')
        if len(ids) > self.limits.max_tasks:
            raise BudgetExceeded('Task budget exhausted')
        for task in tasks:
            if task.status != 'pending' or task.id in task.dependencies:
                raise ValueError('New tasks must be pending and cannot depend on themselves')
            if any(dep not in ids for dep in task.dependencies):
                raise ValueError('Unknown task dependency')
        self.state.tasks.extend(task.model_copy(deep=True) for task in tasks)

    async def _execute(self, task: Task, snapshot: State):
        task.status = 'running'
        self.emit({'event': 'task_started', 'task': task.id, 'role':task.role, 'at': monotonic(),'question':task.question,'dependencies':task.dependencies,'available_evidence_ids':[e.evidence_id for e in snapshot.evidence]})
        try:
            agent = self.agents[task.role]
            output = AgentResult.model_validate(await agent(task.model_copy(deep=True), snapshot, ToolAccess(self, task.role, task.id)))
            evidence_ids = {e.evidence_id for e in self.state.evidence if e.status != 'error' and e.error is None}
            hypotheses = output.hypotheses + (output.report.hypotheses if output.report else [])
            hypotheses += [c.hypothesis for c in output.candidates or []]
            for hypothesis in hypotheses:
                if not set(hypothesis.supporting_evidence + hypothesis.contradicting_evidence) <= evidence_ids:
                    raise ValueError('Agent cited unknown or failed evidence')
            valid_records = {e.evidence_id:{r.get('record_id') for r in e.records} for e in self.state.evidence if e.evidence_id in evidence_ids}
            findings=list(output.findings or [])+[f for c in output.candidates or [] for f in c.findings]
            for finding in findings:
                if any(c.record_id not in valid_records.get(c.evidence_id,set()) for c in finding.citations):
                    raise ValueError('Finding cited an unobserved record')
            if output.report:
                if task.role != 'reporting' or output.report.incident_id != self.state.incident.id:
                    raise ValueError('Invalid report author or incident ID')
                if any(t.status in ('pending','running') and t.id != task.id for t in self.state.tasks):
                    raise ValueError('Report cannot finalize while investigation tasks remain')
            if output.followups and task.role not in ('orchestrator', 'critic'):
                raise ValueError('Only orchestrator and critic may schedule tasks')
            # Validate all outputs before committing follow-ups or shared conclusions.
            if output.followups:
                investigative_followup=task.role == 'critic' and any(t.role != 'reporting' for t in output.followups)
                if investigative_followup and self.state.followup_rounds >= self.limits.max_followup_rounds:
                    raise BudgetExceeded('Follow-up round budget exhausted')
                self.add_tasks(output.followups)
                if investigative_followup:
                    self.state.followup_rounds += 1
            if output.candidates is not None:
                self.state.candidates=output.candidates
            if output.findings is not None:
                self.state.findings=output.findings
            self.state.hypotheses.extend(output.hypotheses)
            self.state.objections.extend(output.objections)
            if output.report:
                self.state.report=output.report
            self.emit({'event': 'agent_result', 'task': task.id, 'role':task.role, 'result': output.model_dump()})
            task.status = 'complete'
        except asyncio.CancelledError:
            task.status, task.error = 'failed', 'Execution deadline exceeded'
            raise
        except Exception as exc:
            task.status, task.error = 'failed', f'{type(exc).__name__}: {exc}'
            self.state.limitations.append(f'{task.id}: {task.error}')
        finally:
            self.emit({'event': 'task_finished', 'task': task.id, 'role':task.role, 'status': task.status, 'at': monotonic()})

    async def _schedule(self):
        while any(t.status == 'pending' for t in self.state.tasks):
            by_id = {t.id: t for t in self.state.tasks}
            for task in self.state.tasks:
                if task.status == 'pending' and any(by_id[d].status in ('failed', 'skipped') for d in task.dependencies):
                    task.status, task.error = 'skipped', 'Dependency failed'
                    self.state.limitations.append(f'{task.id}: dependency failed')
            ready = [t for t in self.state.tasks if t.status == 'pending' and all(by_id[d].status == 'complete' for d in t.dependencies)]
            if not ready:
                for task in self.state.tasks:
                    if task.status == 'pending':
                        task.status, task.error = 'skipped', 'Unresolvable task dependencies'
                        self.state.limitations.append(f'{task.id}: unresolvable dependencies')
                break
            snapshot = self.state.model_copy(deep=True)
            await asyncio.gather(*(self._execute(task, snapshot.model_copy(deep=True)) for task in ready))

    async def run(self, tasks: list[Task], output: Path | None = None) -> State:
        self.add_tasks(tasks)
        try:
            await asyncio.wait_for(self._schedule(), timeout=self.limits.timeout_seconds)
        except TimeoutError:
            self.state.limitations.append('Execution deadline exceeded')
            for task in self.state.tasks:
                if task.status == 'pending':
                    task.status, task.error = 'skipped', 'Execution deadline exceeded'
        if self.state.report is None or self.state.limitations:
            self.state.status = 'inconclusive'
            if self.state.report:
                self.state.report.outcome = 'inconclusive'
                self.state.report.limitations.extend(self.state.limitations)
        else:
            self.state.status = 'complete' if self.state.report.outcome == 'probable_cause' else 'inconclusive'
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(self.state.model_dump_json(indent=2) + '\n')
        return self.state
