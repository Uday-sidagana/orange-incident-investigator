"""Evaluator-only code; never import this module from agent runtime modules.

Scoring uses explicit labels and annotated evidence requirements, not keyword matching
or an LLM judge. Narrative entailment still needs human review.
"""
import json
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from .models import InvestigationReport, StrictModel, ToolResult


from .contracts import Citation, Finding, Submission


def load_dataset(root: Path):
    truth = json.loads((root/'evaluation/ground_truth.json').read_text())
    fixtures = {p.stem: json.loads(p.read_text()) for p in (root/'data/incidents').glob('*.json')}
    if set(fixtures) != set(truth):
        raise ValueError('Fixture and ground-truth incident sets differ')
    return fixtures, truth


def validate_dataset(root: Path) -> dict:
    from .models import Incident, Query
    fixtures, truth = load_dataset(root)
    splits = json.loads((root/'evaluation/splits.json').read_text())
    split_ids = [case_id for ids in splits.values() for case_id in ids]
    if len(split_ids) != len(set(split_ids)) or set(split_ids) != set(fixtures):
        raise ValueError('Development/held-out split must partition the dataset')
    all_record_ids = set()
    for case_id, fixture in fixtures.items():
        incident = Incident.model_validate(fixture['incident'])
        if incident.id != case_id or set(fixture) != {'incident', 'sources', 'failures'}:
            raise ValueError(f'{case_id}: invalid runtime fixture boundary')
        if set(fixture['sources']) != set(Query.model_fields['tool'].annotation.__args__):
            raise ValueError(f'{case_id}: missing tool source')
        records = {}
        for rows in fixture['sources'].values():
            for row in rows:
                record_id = row['record_id']
                if record_id in all_record_ids:
                    raise ValueError(f'Duplicate record ID: {record_id}')
                all_record_ids.add(record_id)
                records[record_id] = row
        expected = truth[case_id]
        if expected['expected_outcome'] not in ('probable_cause', 'inconclusive'):
            raise ValueError(f'{case_id}: invalid outcome')
        if (expected['cause_code'] is None) != (expected['expected_outcome'] == 'inconclusive'):
            raise ValueError(f'{case_id}: outcome/cause mismatch')
        for refs in expected['findings'].values():
            if not refs or not set(refs) <= records.keys():
                raise ValueError(f'{case_id}: invalid expected evidence records')
    return {'incidents': len(fixtures), 'records': len(all_record_ids),
            'inconclusive_incidents': sum(t['expected_outcome']=='inconclusive' for t in truth.values()),
            'failure_injection_incidents': sum(bool(f['failures']) for f in fixtures.values())}


def score(submission: Submission, fixture: dict, expected: dict) -> dict:
    if submission.incident_id != fixture['incident']['id']:
        raise ValueError('Submission does not match fixture')
    records = {r['record_id']: r for rows in fixture['sources'].values() for r in rows}
    # Only records actually returned by a valid successful/partial tool envelope can ground a claim.
    trace = {}
    for result in submission.trace:
        if result.evidence_id in trace:
            raise ValueError('Duplicate evidence IDs in trace')
        trace[result.evidence_id] = result

    def valid_citation(citation):
        envelope = trace.get(citation.evidence_id)
        if envelope is None or envelope.status == 'error' or envelope.error is not None:
            return False
        canonical = records.get(citation.record_id)
        if canonical is None or canonical not in envelope.records or canonical not in fixture['sources'][envelope.query.tool]:
            return False
        query = envelope.query
        if any(getattr(query, field) is not None and canonical.get(field) != getattr(query, field)
               for field in ('service', 'tenant', 'version')):
            return False
        if query.search and query.search.casefold() not in json.dumps(canonical).casefold():
            return False
        if query.start or query.end:
            from .tools import timestamp
            if 'timestamp' not in canonical:
                return False
            when = timestamp(canonical['timestamp'])
            if query.start and when < timestamp(query.start):
                return False
            if query.end and when > timestamp(query.end):
                return False
        return True

    annotated = expected['findings']
    details = []
    valid_citations = total_citations = grounded = 0
    for finding in submission.findings:
        refs = set()
        for citation in finding.citations:
            total_citations += 1
            if valid_citation(citation):
                valid_citations += 1
                refs.add(citation.record_id)
        required = set(annotated.get(finding.code, []))
        supported = bool(required) and required <= refs and all(valid_citation(c) for c in finding.citations)
        grounded += supported
        details.append({'code':finding.code, 'expected':bool(required), 'grounded':supported,
                        'missing_record_ids':sorted(required-refs)})
    cause = expected['cause_code']
    predicted = submission.ranked_cause_codes
    outcome_correct = submission.run_status == 'completed' and submission.report.outcome == expected['expected_outcome']
    # Abstention receives credit only on incidents whose evidence was authored as insufficient.
    top1 = outcome_correct and (True if cause is None else bool(predicted) and predicted[0] == cause)
    top3 = outcome_correct and (True if cause is None else cause in predicted[:3])
    expected_count = len(annotated)
    grounded_recall = grounded / expected_count if expected_count else 1.0
    grounded_precision = grounded / len(submission.findings) if submission.findings else 0.0
    actions = set(submission.action_codes)
    allowed = set(expected['acceptable_action_codes'])
    return {
        'incident_id':submission.incident_id, 'approach':submission.approach,
        'outcome_correct':bool(outcome_correct), 'root_cause_top1':bool(top1), 'root_cause_top3':bool(top3),
        'grounded_top1':bool(top1 and grounded_recall == 1.0),
        'finding_precision':grounded_precision, 'finding_recall':grounded_recall,
        'citation_validity':valid_citations/total_citations if total_citations else 0.0,
        'action_precision':len(actions & allowed)/len(actions) if actions else 0.0,
        'acceptable_action_present':bool(actions & allowed),
        'tool_calls':len(submission.trace), 'latency_seconds':submission.latency_seconds,
        'input_tokens':submission.input_tokens, 'output_tokens':submission.output_tokens,
        'finding_details':details,
        'limitations':['Label-based scoring does not verify prose entailment, confidence calibration, or action safety. Trace provenance is trusted; this is not a tamper-proof evaluator.'],
    }


def score_directory(root: Path, submissions: Path, output: Path, split: str = 'all') -> dict:
    fixtures, truth = load_dataset(root)
    if split != 'all':
        splits = json.loads((root/'evaluation/splits.json').read_text())
        if split not in splits:
            raise ValueError(f'Unknown dataset split: {split}')
        selected = set(splits[split])
        fixtures = {key:value for key,value in fixtures.items() if key in selected}
        truth = {key:value for key,value in truth.items() if key in selected}
    results, seen = [], set()
    for path in sorted(submissions.glob('*.json')):
        submission = Submission.model_validate_json(path.read_text())
        key = (submission.approach, submission.incident_id)
        if key in seen:
            raise ValueError(f'Duplicate run for {key}; use separate directories for repeated trials')
        seen.add(key)
        if submission.incident_id not in fixtures:
            raise ValueError(f'Unknown incident: {submission.incident_id}')
        results.append(score(submission, fixtures[submission.incident_id], truth[submission.incident_id]))
    summaries = {}
    for approach in sorted({r['approach'] for r in results}):
        runs = [r for r in results if r['approach'] == approach]
        summary = {'submitted':len(runs), 'expected':len(fixtures),
                   'missing_incidents':sorted(set(fixtures)-{r['incident_id'] for r in runs}),
                   'root_cause_accuracy_all_incidents':sum(r['root_cause_top1'] for r in runs)/len(fixtures)}
        for metric in ['root_cause_top1','root_cause_top3','grounded_top1','finding_precision','finding_recall','citation_validity','action_precision','tool_calls','latency_seconds','input_tokens','output_tokens']:
            measured = [r[metric] for r in runs if r[metric] is not None]
            summary[f'mean_{metric}'] = sum(measured)/len(measured) if measured else None
            summary[f'{metric}_measured_runs'] = len(measured)
        summaries[approach] = summary
    payload = {'split':split, 'results':results, 'summary':summaries,
               'warning':'simulation and scorer_test results exercise deterministic rules/evaluator mechanics, not LLM-agent performance. Missing measurements remain null. Missing incidents count as incorrect in all-incidents accuracy.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload,indent=2)+'\n')
    return payload
