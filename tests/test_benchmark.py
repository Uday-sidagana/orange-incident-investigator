"""Oracle submissions below test scoring, never claim model performance."""
import asyncio
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from orange_incident.benchmark import Citation, Finding, Submission, load_dataset, score, score_directory, validate_dataset
from orange_incident.models import Hypothesis, InvestigationReport, Query
from orange_incident.tools import Simulation

ROOT = Path(__file__).resolve().parents[1]
FIXTURES, TRUTH = load_dataset(ROOT)


def oracle(case_id):
    fixture, expected = FIXTURES[case_id], TRUTH[case_id]
    sim = Simulation(ROOT/f'data/incidents/{case_id}.json', inject_failures=False)
    async def collect():
        for tool in fixture['sources']:
            await sim.query(Query(tool=tool))
    asyncio.run(collect())
    cause = expected['cause_code']
    evidence_by_record = {r['record_id']: e.evidence_id for e in sim.trace for r in e.records}
    return Submission(incident_id=case_id, approach='scorer_test',
        report=InvestigationReport(incident_id=case_id, outcome=expected['expected_outcome'],
            hypotheses=[Hypothesis(description='Oracle scorer test only', supporting_evidence=[], contradicting_evidence=[], confidence='high', assumptions=[])] if cause else [],
            recommended_actions=['Oracle scorer test only'], limitations=[]),
        ranked_cause_codes=[cause] if cause else [],
        findings=[Finding(code=code, statement='Oracle scorer test only', citations=[Citation(evidence_id=evidence_by_record[r], record_id=r) for r in refs]) for code,refs in expected['findings'].items()],
        action_codes=expected['acceptable_action_codes'], trace=sim.trace)


def test_dataset_coverage():
    result = validate_dataset(ROOT)
    assert result['incidents'] >= 10
    assert result['inconclusive_incidents'] >= 1
    assert result['failure_injection_incidents'] >= 3
    tags = {tag for t in TRUTH.values() for tag in t['tags']}
    assert {'latency','backlog','tenant_impact','misleading_history','permanent_tool_failure'} <= tags
    vocab = json.loads((ROOT/'data/rubric.json').read_text())
    assert {t['cause_code'] for t in TRUTH.values() if t['cause_code']} <= set(vocab['cause_codes'])


@pytest.mark.parametrize('case_id', sorted(FIXTURES))
def test_all_oracle_scores(case_id):
    result = score(oracle(case_id), FIXTURES[case_id], TRUTH[case_id])
    assert result['root_cause_top1'] and result['grounded_top1']
    assert result['finding_precision'] == result['finding_recall'] == result['citation_validity'] == 1
    assert result['acceptable_action_present']
    assert result['latency_seconds'] is None


def test_correct_cause_without_evidence_is_not_grounded():
    submission = oracle('gmail-001')
    submission.findings = []
    result = score(submission, FIXTURES['gmail-001'], TRUTH['gmail-001'])
    assert result['root_cause_top1'] and not result['grounded_top1']
    assert result['finding_recall'] == 0


def test_forged_record_and_unknown_citation_rejected():
    submission = oracle('auth-002')
    submission.trace[0].records[0]['granted_scopes'] = ['invented']
    submission.findings[1].citations[0].evidence_id = 'invented'
    result = score(submission, FIXTURES['auth-002'], TRUTH['auth-002'])
    assert result['finding_recall'] < 1 and result['citation_validity'] < 1


def test_failed_and_wrong_tool_citations_do_not_ground():
    submission = oracle('auth-002')
    submission.trace[0].status = 'error'
    submission.trace[1].query.tool = 'history'
    result = score(submission, FIXTURES['auth-002'], TRUTH['auth-002'])
    assert result['finding_recall'] < 1


def test_incomplete_trace_can_support_present_records():
    submission = oracle('auth-002')
    submission.trace[0].status = 'partial'
    submission.trace[0].complete = False
    result = score(submission, FIXTURES['auth-002'], TRUTH['auth-002'])
    assert result['finding_recall'] == 1


def test_mismatched_query_cannot_support_claim():
    submission = oracle('auth-002')
    submission.trace[0].query.tenant = 'not-the-observed-tenant'
    result = score(submission, FIXTURES['auth-002'], TRUTH['auth-002'])
    assert result['finding_recall'] < 1


def test_wrong_cause_and_irrelevant_finding_penalized():
    submission = oracle('auth-002')
    submission.ranked_cause_codes = ['provider_failure']
    submission.findings.append(Finding(code='pool_saturated', statement='Unsupported', citations=[]))
    result = score(submission, FIXTURES['auth-002'], TRUTH['auth-002'])
    assert not result['root_cause_top1']
    assert result['finding_precision'] < 1


def test_abstention_does_not_pass_solvable_case():
    submission = oracle('auth-002')
    submission.report.outcome = 'inconclusive'
    submission.report.hypotheses = []
    submission.ranked_cause_codes = []
    assert not score(submission, FIXTURES['auth-002'], TRUTH['auth-002'])['root_cause_top1']


def test_directory_counts_missing_cases_and_keeps_unknown_usage_null(tmp_path):
    submissions = tmp_path/'submissions'
    submissions.mkdir()
    (submissions/'one.json').write_text(oracle('auth-002').model_dump_json())
    output = tmp_path/'scores.json'
    result = score_directory(ROOT, submissions, output)
    summary = result['summary']['scorer_test']
    assert summary['submitted'] == 1 and len(summary['missing_incidents']) == len(FIXTURES)-1
    assert summary['root_cause_accuracy_all_incidents'] == 1/len(FIXTURES)
    assert summary['mean_input_tokens'] is None
    assert summary['input_tokens_measured_runs'] == 0
    assert output.exists()


def test_invalid_submission_and_duplicate_evidence_rejected():
    submission = oracle('auth-002')
    submission.report.incident_id = 'wrong'
    with pytest.raises(ValidationError):
        Submission.model_validate_json(submission.model_dump_json())
    submission = oracle('auth-002')
    submission.trace.append(submission.trace[0])
    with pytest.raises(ValueError, match='Duplicate evidence'):
        score(submission, FIXTURES['auth-002'], TRUTH['auth-002'])


def test_split_coverage_and_unknown_incident_guard(tmp_path):
    submissions = tmp_path/'submissions'
    submissions.mkdir()
    (submissions/'one.json').write_text(oracle('auth-002').model_dump_json())
    result = score_directory(ROOT, submissions, tmp_path/'scores.json', split='development')
    assert result['summary']['scorer_test']['expected'] == len(json.loads((ROOT/'evaluation/splits.json').read_text())['development'])
    with pytest.raises(ValueError, match='Unknown incident'):
        score_directory(ROOT, submissions, tmp_path/'scores.json', split='held_out')


@pytest.mark.parametrize('case_id', sorted(FIXTURES))
def test_each_incident_failure_schedule_runs_through_tools(case_id):
    sim = Simulation(ROOT/f'data/incidents/{case_id}.json')
    async def collect():
        for tool in FIXTURES[case_id]['sources']:
            result = await sim.query_with_retry(Query(tool=tool))
            spec = FIXTURES[case_id]['failures'].get(tool, {})
            if spec.get('timeout_attempts', 0) >= 2:
                assert result.status == 'error'
            elif spec.get('incomplete'):
                assert result.status == 'partial'
            else:
                assert result.status == 'ok'
    asyncio.run(collect())


def test_runtime_failure_does_not_earn_abstention_credit():
    submission = oracle('unknown-012')
    submission.run_status = 'failed'
    result = score(submission, FIXTURES['unknown-012'], TRUTH['unknown-012'])
    assert not result['root_cause_top1'] and not result['grounded_top1']
