"""Shared report contracts; contains no evaluator labels or fixture access."""
from typing import Literal
from pydantic import Field, model_validator
from .models import Hypothesis, InvestigationReport, StrictModel, ToolResult


class Citation(StrictModel):
    evidence_id: str
    record_id: str


class Finding(StrictModel):
    code: str
    statement: str
    citations: list[Citation] = Field(default_factory=list)


class Submission(StrictModel):
    incident_id: str
    approach: Literal['single_agent', 'multi_agent', 'simulation', 'scorer_test']
    run_status: Literal['completed', 'failed'] = 'completed'
    report: InvestigationReport
    # Ranked alongside report.hypotheses; no per-incident answer list is sent to agents.
    ranked_cause_codes: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    action_codes: list[str] = Field(default_factory=list)
    trace: list[ToolResult] = Field(default_factory=list)
    latency_seconds: float | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def consistent(self):
        if self.report.incident_id != self.incident_id:
            raise ValueError('Report and submission incident IDs differ')
        if len(self.ranked_cause_codes) != len(self.report.hypotheses):
            raise ValueError('Ranked cause codes must align with report hypotheses')
        if len(set(self.ranked_cause_codes)) != len(self.ranked_cause_codes):
            raise ValueError('Ranked cause codes must be unique')
        if len({f.code for f in self.findings}) != len(self.findings):
            raise ValueError('Finding codes must be unique')
        if self.report.outcome == 'probable_cause' and not self.ranked_cause_codes:
            raise ValueError('A probable-cause report needs a ranked cause')
        return self



class Diagnosis(StrictModel):
    report: InvestigationReport
    ranked_cause_codes: list[str]
    findings: list[Finding]
    action_codes: list[str]


class Candidate(StrictModel):
    code: str
    hypothesis: Hypothesis
    findings: list[Finding] = Field(default_factory=list)
    action_codes: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    strength: int = Field(default=0, ge=0, le=10)
