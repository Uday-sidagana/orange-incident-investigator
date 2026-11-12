import asyncio
from pathlib import Path
import pytest
from orange_incident.demo import workflow_demo
from orange_incident.engine import AgentResult, Engine, Limits, Task
from orange_incident.models import Hypothesis, Query
from orange_incident.tools import Simulation

FIXTURE = Path(__file__).resolve().parents[1] / 'data/incidents/gmail-001.json'


def engine(agent, **limits):
    sim = Simulation(FIXTURE)
    return Engine(sim.incident, sim.query, {r: agent for r in ['observability', 'dependency', 'critic', 'reasoning']}, Limits(**limits))


def test_critic_followup_and_saved_trace(tmp_path):
    target = tmp_path / 'workflow.json'
    state = asyncio.run(workflow_demo(FIXTURE, target))
    assert state.followup_rounds == 1
    assert all(t.status == 'complete' for t in state.tasks)
    assert any(e.query.tool == 'reproduce' for e in state.evidence)
    assert any(e.status == 'error' for e in state.evidence)
    assert state.report.outcome == 'inconclusive'
    assert state.mode == 'scripted_workflow'
    assert target.exists()


def test_parallel_tasks_and_snapshot_isolation():
    async def scenario():
        entered = 0
        both = asyncio.Event()
        async def agent(task, state, tools):
            nonlocal entered
            assert state.objections == []
            state.objections.append('local change')
            entered += 1
            if entered == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 1)
            return AgentResult()
        run = engine(agent)
        state = await run.run([Task(id='a', role='observability', question='a'), Task(id='b', role='dependency', question='b')])
        assert all(t.status == 'complete' for t in state.tasks)
        assert state.objections == []
    asyncio.run(scenario())


def test_global_budget_counts_retries():
    async def agent(task, state, tools):
        await tools.query(Query(tool='metrics'))
        return AgentResult()
    run = engine(agent, max_tool_calls=1)
    state = asyncio.run(run.run([Task(id='a', role='observability', question='a')]))
    assert state.tool_calls == 1 and len(state.evidence) == 1
    assert state.tasks[0].status == 'failed'
    assert state.status == 'inconclusive'


def test_failed_agent_skips_dependents_but_preserves_independent_work():
    async def agent(task, state, tools):
        if task.id == 'bad':
            raise RuntimeError('simulated agent failure')
        await tools.query(Query(tool='deployments'))
        return AgentResult()
    run = engine(agent)
    state = asyncio.run(run.run([
        Task(id='bad', role='observability', question='a'),
        Task(id='good', role='dependency', question='b'),
        Task(id='dependent', role='reasoning', question='c', dependencies=['bad'])]))
    assert [t.status for t in state.tasks] == ['failed', 'complete', 'skipped']
    assert len(state.evidence) == 1


def test_deadline_cancels_work():
    async def agent(task, state, tools):
        await asyncio.sleep(1)
        return AgentResult()
    run = engine(agent, timeout_seconds=0.01)
    state = asyncio.run(run.run([Task(id='a', role='observability', question='a')]))
    assert state.tasks[0].status == 'failed'
    assert state.status == 'inconclusive'
    assert 'Execution deadline exceeded' in state.limitations


def test_unknown_evidence_is_rejected():
    async def agent(task, state, tools):
        return AgentResult(hypotheses=[Hypothesis(description='Unsupported', supporting_evidence=['invented'], contradicting_evidence=[], confidence='high', assumptions=[])])
    run = engine(agent)
    state = asyncio.run(run.run([Task(id='a', role='reasoning', question='a')]))
    assert state.tasks[0].status == 'failed' and state.hypotheses == []


def test_permissions_and_cycles():
    async def agent(task, state, tools):
        await tools.query(Query(tool='deployments'))
        return AgentResult()
    run = engine(agent)
    state = asyncio.run(run.run([Task(id='a', role='observability', question='a')]))
    assert 'PermissionError' in state.tasks[0].error
    run = engine(agent)
    state = asyncio.run(run.run([Task(id='a', role='dependency', question='a', dependencies=['b']), Task(id='b', role='dependency', question='b', dependencies=['a'])]))
    assert all(t.status == 'skipped' for t in state.tasks)


def test_followup_budget():
    async def agent(task, state, tools):
        return AgentResult(followups=[Task(id='next', role='dependency', question='next')])
    run = engine(agent, max_followup_rounds=0)
    state = asyncio.run(run.run([Task(id='critic', role='critic', question='check')]))
    assert len(state.tasks) == 1 and state.tasks[0].status == 'failed'


def test_unknown_dependency_rejected_before_run():
    async def agent(*args):
        return AgentResult()
    with pytest.raises(ValueError, match='Unknown task dependency'):
        asyncio.run(engine(agent).run([Task(id='a', role='critic', question='check', dependencies=['missing'])]))


def test_invalid_candidate_cannot_commit_followups_or_shared_state():
    from orange_incident.contracts import Candidate
    async def agent(task,state,tools):
        return AgentResult(candidates=[Candidate(code='invented',hypothesis=Hypothesis(description='Unsupported',supporting_evidence=['invented'],contradicting_evidence=[],confidence='high',assumptions=[]))],
            followups=[Task(id='should-not-run',role='dependency',question='Do not execute invalid output')])
    run=engine(agent)
    state=asyncio.run(run.run([Task(id='critic',role='critic',question='Check')]))
    assert len(state.tasks)==1
    assert state.candidates==[] and state.tasks[0].status=='failed'
