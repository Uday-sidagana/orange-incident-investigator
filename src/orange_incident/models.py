from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Incident(StrictModel):
    id: str
    title: str
    description: str
    start: str
    end: str
    services: list[str]


class Query(StrictModel):
    tool: Literal["logs", "metrics", "deployments", "dependencies", "history", "knowledge", "reproduce", "connections", "refresh_history"]
    service: str | None = Field(default=None, description="Exact service field match; null includes records without a service field")
    tenant: str | None = None
    version: str | None = None
    start: str | None = Field(default=None, description="Inclusive timezone-aware start. Initially use null for reproduce, dependencies, history, and knowledge; records may lack timestamps")
    end: str | None = Field(default=None, description="Inclusive timezone-aware end. Initially use null for reproduce, dependencies, history, and knowledge")
    search: str | None = Field(default=None, description="Literal case-insensitive substring filter, NOT semantic search or an instruction. Start with null; use a short observed string to narrow results")
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def check_range(self):
        from datetime import datetime
        for value in (self.start, self.end):
            if value:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("Query timestamps must include a timezone")
        if self.start and self.end:
            if datetime.fromisoformat(self.start.replace("Z", "+00:00")) > datetime.fromisoformat(self.end.replace("Z", "+00:00")):
                raise ValueError("start must precede end")
        return self


class ToolError(StrictModel):
    code: Literal["timeout", "invalid_query", "unavailable"]
    message: str
    retryable: bool


class ToolResult(StrictModel):
    evidence_id: str
    query: Query
    status: Literal["ok", "partial", "error"]
    records: list[dict[str, Any]] = Field(default_factory=list)
    complete: bool
    error: ToolError | None = None
    warning: str | None = None
    attempt: int


class Hypothesis(StrictModel):
    description: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    confidence: Literal["low", "medium", "high"]
    assumptions: list[str]


class InvestigationReport(StrictModel):
    incident_id: str
    outcome: Literal["probable_cause", "inconclusive"]
    hypotheses: list[Hypothesis]
    recommended_actions: list[str]
    limitations: list[str]
