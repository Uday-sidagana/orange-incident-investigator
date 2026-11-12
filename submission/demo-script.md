# Demo recording guide

Aim for roughly 6–8 minutes. This is a suggested format, not an assignment-imposed duration. Show two incidents: one supported diagnosis and one honest inconclusive outcome. Keep an optional GitHub example for discussion. Real model outputs vary; demonstrate the actual report, including limitations, rather than promising a predetermined result.

## Before recording

1. Start `orange serve` from the repository root and open http://127.0.0.1:8000.
2. Confirm the banner says live Plain and six GPT agents. Slack and Linear should be enabled. Keep the relevant workspace/channel and the repository's architecture/results pages in separate tabs.
3. Prepare the fictional details below. Never display `.env`, API keys or authorization headers. The video can show integration status and tool results without credentials.
4. Rehearse once. Allow several minutes of model latency. You can pause recording or make a clearly labeled “investigation completed after …” cut; do not present an old report as the new ticket. Follow the same ticket ID through the workflow.
5. If an integration or model request fails, show the actual failure and explicit retry. Do not claim a successful run that did not occur. A failed run is distinct from a completed inconclusive report.

## Opening — 0:00–0:40

Suggested narration:

> “This is a production incident investigator in a fictional Composio-inspired environment. I used my support-pipeline experience to frame the workflow, then built it with substantial Codex assistance. The operational evidence is synthetic; Plain intake, Slack and Linear are real integrations. The goal is to investigate and compare explanations, not simply generate a convincing answer.”

Point to the runtime banner and say the normal demonstration uses stronger reasoning/critic models and smaller collection/reporting models. The benchmark uses a separate all-GPT-5.4 configuration for fairness.

## Scenario 1 — Gmail failures with a misleading authentication lead

### Submit

| Form field | Value |
| --- | --- |
| Name | Demo Reviewer |
| Email | demo-reviewer@example.com |
| Company | Atlas Demo |
| Request type | **Gmail send failures across tenants** (`gmail-001`) |
| Subject | Gmail sends failing after this morning's release |

Description to paste:

> Since about 10:00 UTC, Gmail sends have started failing and work is backing up. Users suspect authentication because an auth change happened nearby. There was also a tool-executor release. Please investigate the affected tenants and failure path before asking everyone to reconnect. Compare behavior across versions and distinguish provider errors from requests that fail before reaching Gmail.

Select the prepared environment before editing the subject/description, since selecting it populates the form. State explicitly: **“This environment supplies authored telemetry; selecting it does not provide an answer to the model.”**

### What to show while it runs — about 0:40–2:30

- Submit and follow the same ticket in Operations. Open Plain to show its created thread and original complaint.
- Show the Linear issue and Slack thread. They receive intake and later report updates, not an automatic customer reply.
- Open the agent work log. Show task questions, exact query inputs/results and model usage. These are recorded decision summaries, not private chain-of-thought.
- Point out observability and dependency tasks can run concurrently; reasoning waits for both; the critic can request follow-up. Show an actual follow-up if the run contains one—do not claim every run must have one.
- The authored Gmail case injects a first metrics timeout. Show the failed attempt and bounded retry if queried. Incomplete history remains incomplete rather than becoming proof that no similar case exists.

Suggested narration:

> “The complaint suggests auth, but that is a hypothesis. The agents inspect the failed execution, granted scopes, release/version behavior and control observations. Each positive finding needs a record ID from a tool result. Connections and refresh views are convenience views of underlying observations, not independent confirmations.”

### Expected investigation and report — about 2:30–3:40

Reviewer-only expectation: **recipient-mapping regression in the new executor version**, rather than missing Gmail scope. The fixture contains version-specific failures, valid send scope, a pre-provider validation failure and sandbox reproduction observations that distinguish mappings. The exact authored counts/fields can be inspected in `data/incidents/gmail-001.json`; do not narrate numbers the actual run did not collect.

Show ranked hypotheses, exact finding citations, counter-evidence, confidence, limitations and proposed corrective actions. A nearby deployment is correlation until the mechanism/control supports it. The control tool reads precomputed mocked observations; it did not send a real email or execute a live repair.

Suggested narration:

> “Here the observed failure path and comparison support the mapping explanation. Reconnecting accounts would not address the demonstrated mechanism. The proposed mitigation and fix still require validation and approval: this system has not changed production or sent a customer response.”

If the model instead reports inconclusive or fails, explain the actual blocker. The evaluator reference is not a guarantee of current model behavior.

## Scenario 2 — missing telemetry and an inconclusive result

### Submit

| Form field | Value |
| --- | --- |
| Name / email / company | Same fictional details as above |
| Request type | **Intermittent execution failures with missing telemetry** (`unknown-012`) |
| Subject | Intermittent 502s; missing traces and metrics |

Description to paste:

> We are seeing sporadic 502 responses from tool execution, but we cannot find complete request traces or metrics for the affected window. A recent release and an upstream issue are both possible. Please establish what the available evidence supports, what cannot be determined, and the exact information needed before choosing a mitigation.

### What to show — about 3:40–5:00

- Same intake, queue and six-role workflow.
- Partial log/reproduction results and unavailable metrics. Do not call the result a provider outage merely because a 502 appears.
- A completed **inconclusive** report, explicit limitations and requests for missing evidence. A permanent metrics failure is an authored feature of this scenario, not a live metrics integration outage.
- Critic feedback and bounded termination. Acceptance feedback is saved; it does not train weights or send the draft.

Suggested narration:

> “The system should stop confidently enough to admit uncertainty. A failed query does not establish that a service is healthy, and an incomplete trace does not prove an upstream failure. This outcome preserves plausible alternatives and specifies which observations would change the diagnosis.”

### Alternative: an entirely custom complaint

Choose **My own issue** and enter the same symptoms without evidence. No prepared telemetry will be attached. The live custom-intake rehearsal already completed all six roles with an inconclusive outcome and concrete evidence requests. This is useful to explain the product boundary, but the prepared missing-telemetry case shows richer tool failure handling.

## Evaluation and close — about 5:00–6:30

Open Evaluation. Suggested narration:

> “I compared the architectures on twenty new, author-visible synthetic cases using GPT-5.4 in both approaches, the same saved incident text, tools and global limits. Both got 17 of 20 causes/outcomes correct. The team had 17 grounded-correct reports versus 15 for the baseline, at about 164 versus 64 seconds per case and 1.90 million versus 638 thousand reported total tokens. The result shows an evidence-coverage tradeoff, not a general multi-agent superiority claim.”

Explain briefly that the input-matching correction, separate control-data corrections and operational recovery are disclosed. Do not blend later successful reruns into the original score. Show the technical note and authentic coding-assistant transcript in the repository.

Close with:

> “Next I would prioritize blind repeated evaluations, semantic review of proposed remedies and authenticated production telemetry. Shared KB retrieval, general Plain inbox ingestion, enrichment and repair execution are outside this prototype. KB is a labeled last-priority fallback, not proof of what happened in an incident.”

## Optional GitHub discussion example

Select **GitHub personal repositories work but organization jobs fail** (`github-org-035`). Complaint: “Personal repository calls work, but organization jobs fail even after reconnecting. Please check the effective connection and organization policy rather than assuming my GitHub UI access proves the OAuth app is approved.”

The authored evidence contains valid credentials, restricted organization OAuth policy, pending app approval and a successful sandbox comparison with approval granted. Expected diagnosis: organization-owner approval is required for the intended OAuth app. Explain that **this diagnosis can come from the incident observations**. If KB guidance is consulted, it must be labeled and linked; documentation alone would not confirm that cause for an arbitrary “missing repos” complaint.

## Useful answers if asked

- **Did you train these models?** No. Review notes are recorded; no fine-tuning or automatic learning is implemented.
- **Are the tools real?** Plain/Linear/Slack APIs are real when configured. Investigation tools expose structured synthetic observations or supplied custom evidence.
- **Can it fix the incident?** It recommends actions and drafts a reply. It does not deploy patches or send customer messages.
- **Why multiple agents?** Distinct capabilities, parallel collection and independent critique. The measured cost/latency tradeoff is disclosed.
- **What did you personally contribute?** Domain framing, workflow requirements, integration setup and acceptance feedback—including the custom-ticket and KB-boundary tests. Codex implemented much of the code and evaluation tooling; the transcript documents the division.

## Rehearsal record

Both prepared environments completed through live Plain, GPT investigation and acknowledged Linear/Slack updates. Gmail produced `recipient_mapping_regression` on explicit retry; its first report failed duplicate finding-code validation and remains preserved. The insufficient-telemetry case completed inconclusively. See `submission/evaluation/submission-demo/verification.json` and the individual reports for measured timing and exact rehearsal inputs. These operational rehearsals are separate from the frozen model comparison.
