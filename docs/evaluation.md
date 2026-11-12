# Evaluation methodology

## Cohorts and preserved versions

There are 52 synthetic incidents: 16 development cases, 16 author-visible held-out cases and 20 newly authored prospective comparison cases (033–052). The reported model comparison covers the latter twenty, not all 52 and not the original held-out split. Scenario authors had access to the reference answers; this is engineering evaluation, not a blind external benchmark.

The final input-matched comparison has one result per architecture/case. Both approaches use GPT-5.4, low reasoning effort, identical saved Plain incident title/description, the same nine tools, public vocabulary, failure schedules, validators and global limits. The team can distribute work across roles; the single agent receives the complete permitted tool set. Each run gets a fresh simulation so transient failure counters reset. Operational intake, outbound delivery and review time are excluded from model-inference latency.

Twenty original team runs are preserved. A final audit found that Plain had asynchronously summarized 18 incident descriptions, while the initial baseline used original portal text. The two already-identical baselines were reused; the other eighteen were rerun once with the exact saved team input, the frozen original runtime and original v3.0 telemetry. Input hashes and scores are in `submission/evaluation/plain-input-matching/results.json`. Preliminary portal-text baseline scores remain archived and are not the final comparison. This correction is input matching, not best-of-result selection.

Five successful-control records also retained stale diagnostic fields or ambiguous counters. Both architectures were rerun on the documented corrected v3.1 data, with their inputs matched. Both scored 5/5 correct and grounded. This separate check is not blended into the original twenty. A later GitHub context-budget recovery under the normal mixed-model configuration is operational verification, not a replacement for the original failed team score.

The frozen v3.0 source/data snapshot, manifests, original and matched submissions, model call logs, query traces, task logs and assistant review notes are packaged under `submission/evaluation/`. The latest runtime includes subsequent context, custom-intake and KB-policy changes; it has not received a fresh matched 20-case benchmark.

## Metrics

| Metric | Definition and qualification |
| --- | --- |
| Root-cause accuracy | Expected top-ranked cause and expected report outcome. Runtime failures count incorrect; a completed appropriate abstention may count correct. |
| Grounded-correct | Correct cause/outcome plus every authored required finding supported by its annotated observed records. Does not prove every prose statement. |
| Citation validity | Emitted finding references resolve to observed canonical records in the trace. Reports without citations score zero for per-case coverage; this is not evidence of fabricated IDs. |
| Finding precision/recall | Overlap with the authored finding-code and record requirements. Additional valid observations may be unannotated. |
| Action precision | Overlap with authored acceptable action codes; not semantic action-safety verification. Manual notes identify weak extra recommendations. |
| Tool attempts | Every recorded result envelope, including failures and retries. |
| Latency | Measured inference wall time, excluding queue and integration delivery. Runs shared local/provider resources; the matching pass ran later with up to three baselines concurrently. |
| Tokens | Provider-reported input plus output usage, including reported reasoning usage. Interrupted/unreported requests can incur usage absent from totals. Not a billing reconciliation. |

[Full results](comparison-results.md) include per-case exceptions. The team scored 17/20 correct and 17/20 grounded-correct; the baseline scored 17/20 and 15/20 respectively. No broad statistical superiority claim follows from twenty author-visible cases and one sampled output each.

## Boundaries and reproducibility

Model context contains the incident, public vocabulary and permitted tool results. Expected answers stay under `evaluation/ground_truth.json` and are not passed to the agents. Models do not receive arbitrary shell/file access. The cause vocabulary is closed-set, which limits generalization and simplifies classification. Operational simulator rules are authored diagnostic policies; their scores are not LLM benchmark results. No incident-specific answer lookup is used by the GPT policies.

Original cohort data is frozen under `submission/evaluation/composio-v3/frozen-v30/`; current `data/` includes the five documented control corrections. The offline verification command selects the proper version rather than silently scoring original reports against changed fixtures:

```sh
python scripts/verify_submission.py
```

It checks packaged file hashes, recomputes original and corrected-pair scores, verifies exact baseline-input hashes, checks transcript export hashes and enforces the technical-note word limit. No credentials, server or model calls are needed. Re-running the LLM workflows requires funded access and will produce new samples, not necessarily identical outputs. Do not rerun campaign scripts merely to inspect results: some create real integration records when enabled.

Confidence is qualitative, not calibrated. The scorer verifies labels and record support, not natural-language entailment, confidence calibration or repair safety. Assistant review notes are explicitly assistant-authored and should not be presented as independent expert grading. Original team failures include excessive abstention, a context-bound failure and a scope mismatch on the intentionally ambiguous logging/500 case. Extra suggested actions remain an improvement target.
