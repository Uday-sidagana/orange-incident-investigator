import asyncio
from pathlib import Path
import pytest
from pydantic import ValidationError
from orange_incident.models import Query
from orange_incident.tools import Simulation

FIXTURE = Path(__file__).resolve().parents[1] / 'data/incidents/gmail-001.json'


def test_transient_timeout_recovers_and_is_preserved():
    sim = Simulation(FIXTURE)
    result = asyncio.run(sim.query_with_retry(Query(tool='metrics')))
    assert result.status == 'ok'
    assert [r.status for r in sim.trace] == ['error', 'ok']
    assert sim.trace[0].error.code == 'timeout'
    assert len({r.evidence_id for r in sim.trace}) == 2


def test_partial_results_stay_partial():
    sim = Simulation(FIXTURE)
    result = asyncio.run(sim.query_with_retry(Query(tool='history')))
    assert result.status == 'partial' and not result.complete
    assert len(sim.trace) == 1


def test_version_comparison_and_query_filters():
    sim = Simulation(FIXTURE)
    old = asyncio.run(sim.query(Query(tool='reproduce', version='20261110')))
    new = asyncio.run(sim.query(Query(tool='reproduce', version='20261112')))
    assert old.records[0]['status'] == 200
    assert new.records[0]['status'] == 400
    logs = asyncio.run(sim.query(Query(tool='logs', tenant='atlas', start='2026-11-12T10:00:00Z')))
    assert len(logs.records) == 1 and logs.records[0]['status'] == 400


def test_retry_budget_stops():
    sim = Simulation(FIXTURE)
    sim.data['failures']['metrics']['timeout_attempts'] = 10
    result = asyncio.run(sim.query_with_retry(Query(tool='metrics'), max_attempts=2))
    assert result.status == 'error' and len(sim.trace) == 2


def test_truncation_is_explicit():
    result = asyncio.run(Simulation(FIXTURE).query(Query(tool='logs', limit=1)))
    assert len(result.records) == 1 and not result.complete


def test_invalid_input_rejected():
    with pytest.raises(ValidationError):
        Query(tool='logs', limit=0)
    with pytest.raises(ValidationError):
        Query(tool='logs', start='2026-11-12T12:00:00Z', end='2026-11-12T10:00:00Z')
    with pytest.raises(ValidationError):
        Query(tool='logs', start='2026-11-12T12:00:00')


def test_runtime_fixture_excludes_answer_keys():
    sim = Simulation(FIXTURE)
    assert set(sim.data) == {'incident', 'sources', 'failures'}
