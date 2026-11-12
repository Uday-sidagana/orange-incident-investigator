# Orange Incident Investigator

A six-agent production incident investigator built for the Orange Invest assignment. It investigates synthetic operational evidence, compares hypotheses, asks for follow-up checks, and produces a reviewable report with citations and explicit uncertainty. A local portal connects real Plain intake to real Linear and Slack updates when configured.

**Start with [the submission index](submission/README.md), [architecture](docs/architecture.md), [measured comparison](docs/comparison-results.md), and the [technical note (under 500 words)](submission/technical-note.md).**

## Run without credentials

Python 3.11+ is required. Run from the repository root; fixture and web assets are loaded relative to it.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
pip install -e . --no-deps
cp .env.example .env
pytest -q
orange validate-dataset
orange simulate --output runs/local-example
orange serve --port 8000
```

Open http://127.0.0.1:8000. With the example configuration, select a prepared environment: these are deterministic simulation runs, clearly labeled, with no model requests or real integration writes. **My own issue requires the GPT runtime.** SQLite inbox state and new run artifacts are written to ignored `runs/`.

Alternatively install current dependencies with `pip install -e '.[dev]'` instead of the lock file. Exact tested versions are pinned in `requirements-lock.txt`; the lock is a tested dependency set, not a guarantee of future provider behavior.

## Run the real GPT team

Edit the ignored `.env`:

```dotenv
INVESTIGATION_RUNTIME=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_REASONING_MODEL=gpt-5.4
```

Restart `orange serve`. Reasoning and critic default to GPT-5.4; the other four roles default to GPT-4.1 mini. Per-role overrides are documented in `.env.example`. API model access and usage are external dependencies; API calls require funded provider access. Simulation and tests do not require it.

Standalone model runs:

```sh
orange agents --fixture data/incidents/gmail-001.json --output runs/team-gmail
orange single-agent --fixture data/incidents/gmail-001.json --output runs/single-gmail
```

The single-agent default is GPT-5.4. For a new architecture comparison, configure **all six team roles** as GPT-5.4 to match it, use fresh tool instances, and record the profile. The preserved comparison below used that matched configuration, not the operational mixed-model defaults. `orange investigate --provider codex` is a separate development adapter; its results are not included in that comparison.

## Plain, Linear and Slack

Credentials are optional and disabled in the example configuration. Set `PLAIN_MODE=live`, `PLAIN_API_KEY`, and the Linear/Slack keys, destinations and enable flags in `.env` to use your own workspaces. See [integration setup](docs/linear-slack-setup.md).

```sh
orange plain-check
orange integrations-check
```

The live path creates a Plain thread, reads it back and checks its correlation ID, then queues investigation. It preserves the original portal complaint separately from Plain's generated summary. It does **not** ingest arbitrary existing Plain threads or use a webhook. Slack/Linear deliveries have persisted status, explicit retry and idempotent reconciliation. Customer responses remain drafts; no customer message or code fix is executed.

The local portal has no authentication or tenant isolation and binds to loopback. Keep it local. Workspaces and credentials are not shared in this repository.

## Your own issue and knowledge boundaries

The portal defaults to **My own issue**. Submit a custom complaint through the same live intake and GPT workflow without selecting a predefined scenario. Optional evidence JSON accepts the nine tool names as keys; records need unique `record_id` values. Missing sources remain incomplete. Supplied observations are not independently verified. Without supporting evidence, expect hypotheses, an inconclusive outcome and concrete requests for missing data.

No live Composio telemetry or shared searchable Composio KB is connected. Public guides informed the dataset; they are not automatically searched for arbitrary complaints. The agent cause vocabulary is predefined. Telemetry and historical cases take priority; KB lookup is a last-priority fallback. KB guidance must be labeled and sourced, and cannot alone establish a probable cause. Feedback records review notes; it does not train weights or automatically update knowledge.

## Evidence and evaluation

- **52** synthetic incidents: the original 16 development / 16 held-out split, plus 20 prospective comparison cases. The held-out split was not used for the reported 20-case comparison.
- Nine structured read-only tools: logs, metrics, deployments, dependencies, history, knowledge, precomputed reproduction controls, connection and refresh-history views.
- Six real model roles, typed shared state, parallel observability/dependency work, critic feedback, role capabilities, bounded retries and global execution limits.
- Operations exposes task questions, evidence, tool results, model usage, conclusions and critic decisions. These are decision summaries, not private model reasoning.

| Matched 20-case comparison | Multi-agent | Single-agent |
| --- | ---: | ---: |
| Correct cause and outcome | 17/20 | 17/20 |
| Grounded-correct reports | 17/20 | 15/20 |
| Mean tool attempts | 12.65 | 10.0 |
| Mean inference seconds | 163.5 | 64.4 |
| Reported total tokens | 1,904,967 | 638,481 |

This author-visible synthetic cohort does not establish general superiority. The report discloses an input-matching correction, separate five-case data-correction checks, a later runtime recovery, and remaining report-quality issues. The measured frozen runtime differs from the latest operational code.

Preserved submissions, traces, manifests, reviews and CSVs are included under [submission/evaluation](submission/evaluation), so a clean checkout retains the evidence. Evaluation in the UI uses local `runs/` if available and otherwise reads the packaged results. Historical local-ticket links may not resolve in a fresh empty inbox; the packaged reports remain inspectable.

```sh
python scripts/verify_submission.py
```

This offline check validates packaged checksums and reproduces recorded scores. It makes no provider requests or integration writes. Automated unit tests use fake provider transports for orchestration; passing tests are not additional LLM performance measurements.

## Submission and demonstration

- [Demo scenarios and narration](submission/demo-script.md)
- [Architecture and agent coordination](docs/architecture.md)
- [Evaluation methodology](docs/evaluation.md)
- [Technical note](submission/technical-note.md)
- [Collaboration summary and attribution](submission/collaboration-summary.md)
- [Authentic coding-assistant transcript](submission/transcript/conversation.md)
- [Requirements checklist and remaining handoff items](submission/README.md)

Older milestone notes under `docs/` are retained as development history. This README, architecture, evaluation methodology and submission index describe the final handoff. There is no enrichment provider, Notion connection, automatic repair/deployment, automatic model training, public hosting, or general Plain inbox ingestion.
