# Live GPT development verification

These are development smoke tests over authored synthetic telemetry, not held-out results or a full-suite model comparison. The agent runtime did not receive evaluator labels or deterministic diagnostic policies.

| Development case | Outcome | Top cause correct | Citation validity | Finding precision | Finding recall | Grounded top1 rubric | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gmail-001 | Probable cause | True | 100% | 33% | 50% | False | 106.6 |
| auth-002 | Probable cause | True | 100% | 40% | 67% | False | 91.0 |

The leading causes and accepted action codes match both development cases. Every cited record resolves, but this is structural citation validity, not independent proof of semantic entailment. Finding-code choices do not consistently match the annotated rubric (for example, a generic verification code instead of the specific grant-control code). This is an unresolved evaluation limitation; do not describe these runs as perfect grounded performance.

A separate development ablation removed logs, controlled reproductions and their derived views from the Gmail environment. It completed with an inconclusive outcome, requested missing causal telemetry, and did not confirm the hinted deployment as a cause.

Final pilot model routing: GPT-5.4 with low reasoning effort for reasoning and critique; GPT-4.1 mini for the other roles. Requests, token usage, model snapshots, workflow decisions and tool records are saved under `runs/live-agents-v7/`. The portal uses the same policies.

Earlier development iterations exposed invalid code/citation output, literal-filter misuse, overbroad verification demands and budget exhaustion. Failed and inconclusive runs remain under `runs/live-agents-v1` through `v6`; these were not held-out evaluations. Corrections included constrained vocabularies and paired citation schemas, source-specific unfiltered discovery, typed critic blocking checks and reporting-budget reservation. No model weights were trained.

Next evaluation work: define unambiguous global finding-code semantics, review prose/action safety, run the remaining development families, freeze prompts/model configuration, then evaluate held-out cases without adapting to their answers.

## Live portal delivery verification

A fictional `[DEMO GPT] Gmail sends fail for one tenant` request entered real Plain, was read back into the worker, and completed the six-role GPT workflow. This variation returned **inconclusive**, with missing-grant as the leading hypothesis and requests for production grant/account evidence. Thus the two successful CLI diagnoses do not establish stable classification across complaint wording and repeat runs. Further calibration/evaluation is required.

The saved local integration enable flags were found disabled and restored to the previously authorized enabled state. The existing completed ticket was synced without rerunning inference. Linear issue [SID-6](https://linear.app/sidagana/issue/SID-6/demo-gpt-gmail-sends-fail-for-one-tenant), Slack intake, threaded report, and channel summary update all completed with one attempt each. No customer response was sent and no repair was executed. The sanitized verification artifact is `runs/gpt-portal-smoke.json`.

A subsequent general prompt clarification distinguishes approval of a probable failure mechanism from verification of a deployed remedy. Offline regression checks pass; its effect across the model benchmark has not yet been measured.
