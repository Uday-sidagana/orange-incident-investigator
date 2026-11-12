# Complete deterministic investigation workflow

## Purpose

Build and test the investigation plumbing before spending time or credits on live-agent behavior. This mode is an explicit finite diagnostic rule system, not Codex inference, model training, or the completed multi-agent assignment. It does not prove general diagnostic ability.

Select this mode with `INVESTIGATION_RUNTIME=simulation`; the configured demo now uses `openai` for the [live GPT runtime](live-agents.md). Plain remains independently configured; it can use the verified real workspace or simulated intake. No OpenAI key or Codex session is needed for the deterministic worker.

## Run

```sh
orange simulate --fixture data/incidents/gmail-001.json --output runs/simulation
orange simulate-suite --output runs/simulation-check
orange score --submissions runs/simulation-check/submissions --output runs/simulation-check/evaluation
orange serve --port 8000
```

The suite's checks use all authored scenarios, including the evidence-insufficient case. They are simulation regression checks, not held-out model evaluation results. No token counts are fabricated; token fields remain null.

## Six role responsibilities

1. **Orchestrator:** creates initial Observability and Dependency tasks and a dependent Reasoning → Critic path.
2. **Observability:** queries logs, metrics, connection state, and refresh history through role-limited tools. Independent queries and the Dependency task run concurrently.
3. **Dependency:** retrieves deployments and dependencies; a later control task retrieves sandbox reproduction observations.
4. **Reasoning:** retrieves historical/reference context on its first pass, applies explicit rules to current observations, and emits ranked candidates, claims with record citations, assumptions, actions, and missing checks.
5. **Critic:** challenges missing controlled evidence. It schedules a Dependency verification task followed by Reasoning and another Critic pass. If control evidence remains missing, the report stays inconclusive. A terminal reporting task does not consume a further evidence-gathering round.
6. **Reporting:** produces a report from shared candidates with confidence levels, supporting/contradicting evidence, assumptions, recommendations, and explicit execution/data limitations. It does not execute fixes or claim deployment/recovery.

Rules inspect returned fields and relationships, not incident IDs, titles, expected labels, or canned scenario answers. They cover the authored diagnostic patterns and remain limited to those patterns. The runtime module does not import benchmark code or read evaluator files. Connection views preserve log provenance and are excluded from independent causal corroboration.

## Evidence and reliability

Evidence envelopes preserve query, status, completeness, error, attempt, and stable record references. Every retry consumes the same global call budget. Missing tools and partial results stay visible. Shared conclusions and newly scheduled tasks are validated before being committed; invented/failed evidence and unobserved record citations are rejected.

The scheduler bounds elapsed time, tasks, tool calls, retries, and control rounds. Dependency failures skip dependent work and produce a failed/inconclusive execution rather than a fabricated diagnosis. Task and tool events are persisted to the ticket activity stream and final traces.

The engine uses in-memory working state with saved final snapshots and durable ticket events. It does not resume a half-completed model conversation after a crash. Restarted jobs require an explicit retry.

## Portal, Plain, and review

A user submits a complaint against a selected synthetic telemetry environment. In live Plain mode, customer/thread creation is followed by a read-back and external-ID check. The returned complaint then enters the six-role simulation. The operations UI shows role tasks, tool activity, critic objections, findings, hypotheses, limitations, and an unsent response draft.

Accept/needs-work review actions save the verdict and debugging notes. They do not silently update prompts/knowledge, alter expected answers, send a reply, or execute a fix. Linear and Slack outbound adapters and a durable delivery queue are implemented, with live setup pending credentials and destinations. PeopleDataLabs and Notion remain unconnected. General Plain inbox ingestion, signed webhooks, outbound Plain report notes, and automatic customer replies remain separate integrations; none are falsely simulated as completed external actions.

## Live-agent handoff

The replacement boundary is the engine's role-to-policy mapping:

`async policy(task: Task, state: State, tools: ToolAccess) -> AgentResult`

A model-backed role will receive a task, an isolated state snapshot, allowed tool descriptions, and public classification vocabulary. It should select tool queries and return the same structured candidate/finding/task/report objects. The Python host retains scheduling, persistence, budgets, evidence validation, and external integration logic. Model output must not directly access SQLite, secret configuration, fixture files, evaluator answers, or arbitrary shell/network tools.

`AgentResult.candidates` replaces current candidates after reassessment; prior structured results remain in the audit events. `findings` carry envelope and record references. Only Orchestrator/Critic can schedule tasks, and only Reporting can finalize a report. This role-level adapter is still to be implemented when live agents are introduced. Selecting `codex` today selects the existing single-agent baseline, not a model-backed six-agent team.

Before final submission: integrate real model policies, add shared token budgets, run the live single-agent/multi-agent comparison on equal tools/budgets, assess novel cases, review reports, and prepare the required submission artifacts. Simulation success does not replace that work.
