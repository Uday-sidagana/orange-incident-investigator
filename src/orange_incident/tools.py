"""Read-only tools. This module never reads evaluation ground truth."""
import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from .models import Incident, Query, ToolError, ToolResult


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Simulation:
    def __init__(self, fixture: Path | dict, inject_failures: bool = True):
        self.data = fixture if isinstance(fixture, dict) else json.loads(fixture.read_text())
        self.incident = Incident.model_validate(self.data["incident"])
        self.inject_failures = inject_failures
        self.attempts: dict[str, int] = {}
        self.trace: list[ToolResult] = []

    async def query(self, query: Query) -> ToolResult:
        await asyncio.sleep(0)  # Yield so independent tasks can run concurrently.
        key = query.model_dump_json()
        attempt = self.attempts.get(key, 0) + 1
        self.attempts[key] = attempt
        evidence_id = "ev_" + hashlib.sha256(f"{self.incident.id}:{key}:{attempt}".encode()).hexdigest()[:12]
        failure = self.data.get("failures", {}).get(query.tool, {}) if self.inject_failures else {}
        if attempt <= failure.get("timeout_attempts", 0):
            result = ToolResult(evidence_id=evidence_id, query=query, status="error", complete=False,
                                error=ToolError(code="timeout", message="Simulated telemetry timeout", retryable=True), attempt=attempt)
        else:
            records = []
            for record in self.data["sources"].get(query.tool, []):
                if any(getattr(query, field) is not None and record.get(field) != getattr(query, field)
                       for field in ("service", "tenant", "version")):
                    continue
                if query.start or query.end:
                    if "timestamp" not in record:
                        continue
                    when = timestamp(record["timestamp"])
                    if query.start and when < timestamp(query.start):
                        continue
                    if query.end and when > timestamp(query.end):
                        continue
                if query.search and query.search.casefold() not in json.dumps(record).casefold():
                    continue
                records.append(record)
            partial = len(records) > query.limit or failure.get("incomplete", False)
            result = ToolResult(evidence_id=evidence_id, query=query, status="partial" if partial else "ok",
                                complete=not partial, records=records[:query.limit], attempt=attempt,
                                warning="Results are incomplete; absence is not proof" if partial else None)
        self.trace.append(result)
        return result

    async def query_with_retry(self, query: Query, max_attempts: int = 2) -> ToolResult:
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        for _ in range(max_attempts):
            result = await self.query(query)
            if not result.error or not result.error.retryable:
                return result
        return result
