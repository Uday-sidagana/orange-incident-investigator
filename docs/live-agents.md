# Model-driven investigation runtime

`INVESTIGATION_RUNTIME=openai` runs six GPT roles over the existing read-only synthetic telemetry tools. This is inference, not model training. No diagnostic rule from the deterministic simulation selects the answer.

| Role | Default model | Responsibility / capabilities |
| --- | --- | --- |
| Orchestrator | gpt-4.1-mini | Frames investigation questions; starts a dependency-controlled task graph. |
| Observability | gpt-4.1-mini | Chooses queries over logs, metrics, connection views and refresh history. |
| Dependency | gpt-4.1-mini | Chooses deployment, service dependency and precomputed reproduction queries. |
| Reasoning | gpt-5.4 | Retrieves historical/reference context; ranks evidence-backed competing explanations. |
| Critic | gpt-5.4 | Challenges causal claims and requests targeted follow-up observations. |
| Reporting | gpt-4.1-mini | Produces a structured report for review; cannot confirm a cause without critic approval. |

The topology and permissions are enforced in code. The models choose the questions, evidence requests, hypotheses, checks and conclusions. The observability and dependency branches run concurrently. A critic follow-up schedules collection, reassessment, then another critique. If another cycle cannot fit the remaining budget, the workflow reserves capacity to report uncertainty. All roles receive a shared evidence snapshot; they cannot read files, expected answers, or evaluator labels.

## Configuration

Keep `OPENAI_API_KEY` in the ignored `.env`. `OPENAI_MODEL` selects the base model; `OPENAI_REASONING_MODEL` selects reasoning and critic models. Optional `OPENAI_<ROLE>_MODEL` overrides one role, including `OPENAI_CRITIC_MODEL`. Use `INVESTIGATION_RUNTIME=simulation` and restart to return to free deterministic verification.

```sh
.venv/bin/orange agents --fixture data/incidents/gmail-001.json --output runs/agents/gmail-001
```

This command does not enqueue Plain, Linear or Slack messages. The server path uses the same agent runtime and adds the existing durable outbound workflow.

## Bounds and failure behavior

GPT-5.4 requests use low reasoning effort. The first read of each evidence source is unfiltered discovery; later reads can narrow to observed field values. Native function schemas enforce this separately for each source, and citation schemas bind envelope IDs to their actual record IDs.

An investigation has at most 20 tasks, 24 evidence attempts including retries, two critic follow-up rounds and a 360-second deadline. The model transport permits at most 24 requests, 4,000 output tokens per request, 100,000 input characters per request and 700,000 cumulative input characters. These are resource bounds, not a dollar-cost guarantee. At most two model requests run concurrently. There is no automatic model escalation. Transient API rate limits, service errors and connection failures receive at most one bounded retry; attempts count toward the shared request/context limits. Authentication and quota errors are not retried. Invalid structured conclusions receive at most one correction request; invalid citations or vocabulary remain rejected after that.

The engine checks role permissions and observed evidence IDs before accepting conclusions. Finding citations must resolve to canonical observed records; derived views do not count as independent evidence. The critic must approve a supported candidate without unresolved material checks before reporting can use a probable-cause outcome. Its typed `blocking_checks` distinguishes checks that could change the diagnosis from optional coverage caveats; it can clear overcautious preliminary checks, with review notes retained in the workflow. These checks establish structural grounding, not semantic truth: human review and evaluation are still required.

Failed/incomplete/refused API requests, exhausted budgets and invalid outputs remain failed/inconclusive rather than falling back to a scripted answer. No repair, deployment or customer reply is executed. Human feedback is stored; it does not automatically update prompts, knowledge or model weights.

Workflow and tool traces, model snapshots, measured usage and request statuses are saved under the run's `traces/` directory. Keys and raw provider exceptions are excluded. Token totals cover successful responses with reported usage; cancelled requests can incur provider usage not present in the local total.

## Evaluation

Start with development cases and evidence-removal checks. Keep held-out cases untouched while refining prompts, and record changes and failed runs. CLI smoke tests show feasibility only; they are not a 32-case performance claim or a controlled single-agent comparison. See `evaluation/splits.json` for the frozen partition.

Implementation references: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4), [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

## Post-comparison context handling

After the frozen matched comparison, the operational runtime was revised to deduplicate identical observations while retaining conflicting payloads, all query attempts and explicit derived views. Citable IDs are remapped only to canonical observed copies; the full trace remains unchanged. Native collection summaries are reused instead of requesting a second summary from another paid call. Critic follow-ups now reserve both request and context capacity for reporting. These changes were tested in a separately labeled recovery, not substituted into the original benchmark score.
