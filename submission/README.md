# Submission index

Project: **Orange Incident Investigator** — Uday Sidagana.

This handoff contains the runnable implementation and the preserved evaluation evidence. Public Composio guidance inspired the fictional environment; no real Composio telemetry or private customer-ticket corpus is included.

| Requested item | Location | Status |
| --- | --- | --- |
| Runnable implementation and setup | [README](../README.md), [locked dependencies](../requirements-lock.txt), `src/`, `web/` | Prepared; fresh-install verification recorded below |
| Architecture diagram and coordination | [Architecture](../docs/architecture.md) | Prepared |
| Synthetic dataset and tests | `data/incidents/`, `evaluation/`, `tests/` | 52 cases; automated verification included |
| Same-tools model comparison | [Results](../docs/comparison-results.md), [methodology](../docs/evaluation.md), [preserved artifacts](evaluation/) | 20 matched pairs; separate five corrected-data pairs |
| Technical note, at most 500 words | [Technical note](technical-note.md) | 407 whitespace-separated words |
| Coding-assistant transcript | [Authentic visible dialogue](transcript/conversation.md), [machine-readable dialogue](transcript/conversation.jsonl), [tool audit](transcript/tool-audit.jsonl), [export manifest](transcript/manifest.json) | Exported with explicit exclusions/redactions; final snapshot boundary recorded |
| Demo video requested by email | [Exact scenarios and narration](demo-script.md) | Script prepared; candidate still needs to record and share the video |
| AI contribution disclosure | [Collaboration summary](collaboration-summary.md) | Edited retrospective summary, explicitly not a replacement transcript |

The transcript preserves casual wording, mistakes and corrections rather than inventing more polished exchanges. Original visible messages are distinct from recorded tool activity. Private reasoning, system/developer instructions, environment-only messages, image binaries and credentials are excluded as described in its manifest. The original source transcript is left untouched locally; the readable export retains message order.

## Reviewer path

1. Read the root README and technical note.
2. Run the offline setup, tests and `python scripts/verify_submission.py`.
3. Open the local portal and Evaluation tab. Packaged comparison results work without a pre-existing `runs/` directory. The historical ticket IDs in evaluation refer to the author's local demo inbox; use the packaged ticket/report JSON and work logs on a fresh installation.
4. Review the current architecture and the frozen-comparison limitations. Running new agents produces new samples with the current runtime and requires provider access.
5. Inspect `evaluation/composio-v3/` for original twenty-case data and `single_agent_plain_matched/` for the matched baseline. Preliminary unmatched scores are archived, not final. The v3.1 and recovery directories are separate evidence.

## Verify the package offline

```sh
python scripts/verify_submission.py
```

The artifact manifest enumerates checksums. The verifier reproduces all fifty scores across the original twenty pairs and corrected five pairs, verifies twenty-five input hashes, checks transcript file hashes and enforces the technical-note word limit. See [verification record](verification.json) for the final setup/test checks. These checks do not claim additional live-model accuracy.

## External dependencies and incomplete functionality

Funded OpenAI access is required for real GPT investigation. Plain/Linear/Slack require reviewer-owned credentials and destinations, and must be explicitly enabled. The default offline mode performs no model requests or external writes. No credentials, live SQLite database, local auth files or `.env` are shipped.

No general Plain inbox/webhook ingestion, live provider telemetry, shared searchable Composio KB, enrichment, Notion integration, automatic repairs/deployments, customer response sending, model-weight training, authenticated public hosting or tenant isolation is implemented. Custom complaints can be investigated without fixtures but may remain inconclusive. KB is fallback guidance and cannot establish an incident cause by itself.

## Remaining candidate handoff actions

- Record the demo using `demo-script.md`; upload it with reviewer-accessible permissions.
- Add the final video link to the submission email.
- If submitting the private GitHub repository, grant access to the specified reviewer account(s); their identities have not been supplied. The ZIP is an alternative if their process accepts an attachment.
- Send the submission email before the deadline in the hiring email. The supplied email says **13 November, 11:30 AM**, without a timezone.

[Submission email draft](submission-email.md) is prepared locally and has not been sent.
