# Measured single-agent versus multi-agent comparison

Twenty new public-documentation-inspired synthetic cases, one first attempt per architecture per case. Both use GPT-5.4 with low reasoning effort, identical saved Plain incident text, the same nine evidence tools and failure-injection rules, the same public vocabulary and citation validator, and identical global limits. Multi-agent cases enter through real Plain; queue and outbound time are excluded from the inference latency measurement.

The first-attempt outputs are preserved independently of assistant reviews and any subsequent operational recovery. Wrong abstentions and execution failures count as incorrect.

| Metric | Multi-agent team | Single agent |
| --- | ---: | ---: |
| Root-cause accuracy (includes outcome) | 85.0% | 85.0% |
| Outcome accuracy | 85.0% | 85.0% |
| Grounded correct reports | 85.0% | 75.0% |
| Mean citation validity | 95.0% | 90.0% |
| Mean finding precision | 42.0% | 46.2% |
| Mean finding recall | 95.0% | 86.7% |
| Mean annotated action precision | 22.8% | 37.1% |
| Mean tool attempts | 12.7 | 10.0 |
| Mean inference seconds | 163.5 | 64.4 |
| Median inference seconds | 164.5 | 59.4 |
| Reported input tokens | 1,707,458 | 561,755 |
| Reported output tokens | 197,509 | 76,726 |
| Reported total tokens | 1,904,967 | 638,481 |

Paired outcomes: both correct: 15, only multi correct: 2, only single correct: 2, both incorrect: 1.

## Per-case results

| Case | Expected | Multi-agent first attempt | Single-agent first attempt | Assistant review |
| --- | --- | --- | --- | --- |
| notion-access-033 | notion_resource_not_shared | Incorrect · inconclusive · completed | Correct · probable_cause · completed | needs_work |
| notion-event-034 | trigger_event_kind_mismatch | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| github-org-035 | github_organization_approval | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| github-token-036 | redacted_token_relay_design | Incorrect · inconclusive · failed | Correct · probable_cause · completed | needs_work |
| github-setup-037 | obsolete_trigger_setup_path | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| sheets-plane-038 | connection_surface_isolation | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| sheets-discovery-039 | tool_discovery_truncation | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| sheets-id-040 | spreadsheet_identifier_kind | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| airtable-expiry-041 | authentication_initiation_expired | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| airtable-batch-042 | provider_batch_record_limit | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| slack-user-043 | slack_user_scope_configuration | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| slack-plan-044 | provider_feature_entitlement | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| slack-ingress-045 | provider_event_ingress_misrouting | Correct · probable_cause · completed | Incorrect · inconclusive · failed | accepted |
| slack-redirect-046 | oauth_redirect_uri_mismatch | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| gmail-shape-047 | attachment_reference_shape | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| gmail-file-048 | temporary_file_reference_expired | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| session-policy-049 | session_tool_policy_block | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |
| log-gap-050 | Inconclusive | Incorrect · probable_cause · completed | Incorrect · probable_cause · completed | needs_work |
| delivery-dedupe-051 | webhook_receiver_not_idempotent | Correct · probable_cause · completed | Incorrect · inconclusive · failed | accepted |
| slack-schedule-052 | scheduled_attachment_semantics | Correct · probable_cause · completed | Correct · probable_cause · completed | accepted |

## Interpretation and limits

- This is an author-visible, closed-vocabulary synthetic cohort, not blind external evaluation. Original held-out cases were not used. Prompts, models, dataset and validators were hash-frozen before execution; the first-attempt score is not improved by selecting retries.
- A grounded correct report requires both correct cause/outcome and all annotated finding requirements. Citation validity checks that referenced observed records exist; neither metric alone proves every sentence or proposed action is correct. Assistant review notes inspect wording, counter-evidence, remediation and uncertainty.
- Controls are precomputed sandbox observations, not live provider experiments. Some flat control records retain initial diagnostic fields; dataset ambiguities are called out in review notes rather than silently changed after seeing model results.
- Latency excludes Plain queue, Slack/Linear delivery and review. Multi-agent and baseline runs shared local/provider resources (original team workers and up to three baseline workers in a later input-matching pass), so these numbers are not a controlled production throughput study.
- Token totals sum provider-reported usage, including reasoning tokens. Failed/cancelled requests without usage may still incur provider charges; these totals are not a billing reconciliation.
- One sample per architecture per case is insufficient for broad statistical superiority claims. Extra critics and tool calls can add useful checks, excessive abstention, cost and additional failure opportunities; measured outcomes decide the comparison.

## Review and source records

### notion-access-033

Assistant validation: current facts and safe next steps are sound, but the report abstains despite explicit page existence, valid token, missing integration page access and a discriminating 404-to-200 access control. This is excessive abstention against the authored probable-cause case; wrong-account selection is a caveat, not an observed alternative cause. No fix or customer reply was executed.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-notion). Ticket: `ef15b241-0b95-4dc9-9184-01b53afb6eaa`.

### notion-event-034

Assistant validation: correct event-kind diagnosis. Current logs show update events checked against a create trigger; the changed-event control succeeds. Tenant backlog is correctly distinguished from HTTP failures. Proposed configuration verification is appropriate and no deployed fix is claimed. Optional subscription/replay steps could be trimmed for clarity.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-notion). Ticket: `940b8a7f-5b24-4d98-aced-5a26afc3170e`.

### github-org-035

Assistant validation: the GitHub organization-approval diagnosis is supported by restricted-policy/pending-approval state and a matched approval control. The report correctly limits personal-access and upstream-origin claims, proposes organization-owner approval rather than a blanket reconnect, and does not claim deployment or customer sending. Verify replay eligibility for queued jobs before rerunning them.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-github). Ticket: `f2dc5bed-8e6d-4649-a4bb-3cbc081667ac`.

### github-token-036

Assistant validation: the first attempt failed at the model context bound during reassessment and produced no usable diagnosis. This is an execution failure, not a correct abstention or a verified credential problem. Preserve the original benchmark result and recover the same issue separately with bounded context handling.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-github). Ticket: `312dd75b-5c86-4813-8994-f974a495ebc6`.

### github-setup-037

Assistant validation: correct obsolete GitHub V2 setup-path diagnosis, supported by the failing endpoint and a matched successful trigger-instance upsert control. It correctly separates unrelated deployment timing and healthy provider access. The proposed action should state the supported-path change more directly; additional upstream traces are useful scope checks rather than a reason to retry the obsolete endpoint.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-github). Ticket: `3ba73351-3641-4383-ad7f-a6791df85b3a`.

### sheets-plane-038

Assistant validation: correct connection-surface isolation diagnosis. Current MCP requests have zero MCP connections despite an active Platform connection, and the changed-surface control succeeds. Authentication through the actual client surface is appropriate; no cross-project credential sharing or automatic remediation is claimed. Account-selection alternatives are explicitly scoped caveats.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-googlesheets). Ticket: `847ad6e6-8ee1-4495-ae3d-77aadc5e6a51`.

### sheets-discovery-039

Assistant validation: correct truncated-discovery diagnosis and pagination/larger-limit remedy; provider outage and missing catalog action are appropriately distinguished. Metrics correctly separate blocked business operations from HTTP failures. Dataset caveat: the corrected control retains first-page counters alongside pagination_completed=true, so those counters must not be read as the final combined tool count.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-googlesheets). Ticket: `c96ec4bc-9252-4516-a2e7-e18415306702`.

### sheets-id-040

Assistant validation: correct display-name versus spreadsheet-ID diagnosis and supported changed-identifier control. The proposed direct-ID operation is appropriate. Precision caveat: without a provider_called or boundary trace, the report should avoid asserting exactly which layer emitted the 400; this does not change the supported identifier remedy.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-googlesheets). Ticket: `0517ca66-993e-4b35-a27d-2c00803b086f`.

### airtable-expiry-041

Assistant validation: correct expired authentication-initiation diagnosis, distinct from revoked consent or token refresh. The observed age exceeds the stated window before exchange; using a fresh link is the supported next step. Dataset caveat: the fresh ACTIVE control retains token_exchange_attempted=false, so it corroborates link-age handling but does not prove a completed production token exchange. The report appropriately states control limitations.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-airtable). Ticket: `6e21eac4-0bd7-4cdd-859a-b68c3f5c45a2`.

### airtable-batch-042

Assistant validation: correct record-count limit, with the failing 25-record request exceeding the observed maximum of ten and a successful ten-record control. Splitting batches, respecting rate limits and checking partial completion are appropriate. Payload-byte limits and release attribution remain alternatives, not established causes. The exact emitting boundary of the 422 is not observed and should stay qualified.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-airtable). Ticket: `30901b50-bf24-4e80-83a6-536077c1d58c`.

### slack-user-043

Assistant validation: correct bot-scope versus user-scope diagnosis and targeted reconnect remedy. The report correctly limits absent account-selection evidence and flags a real dataset flaw: the corrected control succeeds but retains the original missing_scope error string. Preserve this first result, correct the control after the frozen run, and rerun the affected pair.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack). Ticket: `daf6136c-a2dc-4aec-88a4-97234f715d3a`.

### slack-plan-044

Assistant validation: correct Slack AI-search feature/plan entitlement diagnosis, supported by the configured plan, disabled capability flag and changed-plan control. It proposes an eligible feature path or supported alternative rather than scope escalation. Exact upstream-versus-local 403 origin is appropriately left unverified.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack). Ticket: `f6c27e16-440f-4e20-91a2-7a8864830c7c`.

### slack-ingress-045

Assistant validation: correct provider-event ingress misrouting diagnosis. The observed subscription target differs from the intended ingress, event creation succeeds but ingress is absent, and the corrected target control receives the event. Restoring the expected target and testing a new event is appropriate; secret rotation is only conditional on future evidence of verification failures.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack). Ticket: `b04e00a2-d438-4adc-b742-81a86e9db604`.

### slack-redirect-046

Assistant validation: correct static OAuth callback versus short connect-link mismatch. Matching the app redirect setting to the auth flow callback is the appropriate remedy; the example URI must not be treated as a global constant. Dataset caveat: the corrected control retains the old oauth_error label despite success; this is a generator defect to correct and reevaluate separately.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack). Ticket: `10755f3b-2110-4253-8e49-ce51f9747826`.

### gmail-shape-047

Assistant validation: correct uploaded-file-object versus signed-URL argument diagnosis, with explicit pre-provider validation failure and a changed-shape control. It scopes the sampled failure instead of asserting all tenant failures share it. Dataset caveat: the successful control retains a stale validation_error label; correct this field and rerun the affected pair after preserving the first result.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-gmail). Ticket: `2c4ec441-3ca1-4af6-b448-4bd74d7a1416`.

### gmail-file-048

Assistant validation: correct expired temporary file-reference diagnosis; credentials are valid and the failed lookup occurs before the provider call. The fresh-reference remedy and verifying send status before retry are appropriate. The queue may contribute to expiry, but the report correctly says the missing per-request timing prevents proving that deeper cause. Extra scheduled-message/DB-capacity actions are weakly supported and should be trimmed.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-gmail). Ticket: `06b2bf4e-cef7-4a6a-a9fa-c87852982534`.

### session-policy-049

Assistant validation: correct session-policy denial despite provider scope availability. The provider is not called and the authorized narrow-tool exception control succeeds. It preserves least privilege and distinguishes discovery, policy state and provider grants; the exact policy change origin remains unverified. No global widening or permission bypass is recommended.

Source: [Composio guide](https://docs.composio.dev/kb/guide/platform-session-tool-policies). Ticket: `c0da2093-d508-4d9a-831d-bfac9b62635c`.

### log-gap-050

Assistant validation: the payload-storage explanation is supported, but the report answers that visibility question rather than establishing the intended execution-500 cause. It explicitly leaves the 500 mechanism unknown, so a probable-cause outcome for the execution incident is not justified against the authored reference. This is a scope mismatch, not a fabricated claim that storage settings caused the 500. Dataset caveat: the complaint/title leaves some ambiguity between these two symptoms; clarify the objective in a future version. The preliminary portal-text baseline failed structured alignment; the final input-matched baseline instead completed with a scope-mismatched probable-cause report. Neither establishes the underlying execution-500 cause.

Source: [Composio guide](https://docs.composio.dev/kb/guide/dashboard-log-storage). Ticket: `13ba47f6-f0f9-4a8c-b540-607e46eb61b0`.

### delivery-dedupe-051

Assistant validation: correct non-idempotent receiver diagnosis. One ingress event, two receipts with the same stable ID, and the deduplication control support processing retries once. Do not blame duplicate provider ingress. Quality caveat: subscription changes and disabling send retries are not established remedies here; retain legitimate at-least-once retries and focus on receiver deduplication.

Source: [Composio guide](https://docs.composio.dev/kb/guide/platform-triggers). Ticket: `2777613e-af76-4748-84b2-1a7fdb170eb9`.

### slack-schedule-052

Assistant validation: correct distinction between Slack legacy message formatting attachments and file upload. Scheduling text succeeds without a file; separate upload plus a body link succeeds in the control. Use an actual supported file link in the scheduled message, not an arbitrary file-object descriptor. No successful production fix is claimed.

Source: [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack). Ticket: `c5801ab9-6b74-45b6-be3a-0b7614d88b35`.

Machine-readable results: `runs/composio-v3/comparison.json` and `comparison.csv`. Frozen configuration: `manifest.json`. Original submissions, model calls, task logs and manual review records are retained under the same run directory.

## Input audit and preserved versions

Plain asynchronously rewrote 18 of the original 20 thread descriptions into summaries. A final audit caught that the initial baseline had received the portal text instead. Those preliminary baseline scores are preserved in `comparison-portal-text-preliminary.json` and are superseded here. The affected baselines were rerun once using the exact saved team input, frozen original runtime and original v3.0 telemetry. Two already-identical inputs were reused. All five corrected-data baselines were also input-matched. Input hashes and all 25 pair records are in `runs/plain-input-matching/results.json`; matched submissions and traces are under `single_agent_plain_matched/`.

This is a sequential, shared-resource comparison, not a randomized latency experiment. No best-of retry selection was used. Future portal intake now preserves the immutable original complaint separately from Plain's generated summary; historical benchmark inputs remain unchanged.

## Separate control-data correction check

Five successful sandbox controls retained stale diagnostic fields. Both approaches were rerun on corrected v3.1 telemetry with the original runtime, models, tools and limits. Both scored 5/5 correct and grounded. Team mean inference latency was 156.7 seconds and 472,420 total tokens; baseline was 51.6 seconds and 129,405 tokens. These five checks are separate from the original twenty, and do not demonstrate an accuracy improvement. Diffs, manifests, submissions and review notes are in `runs/composio-v31/`.

## Separate operational recovery

The original GitHub token-redaction team run exhausted its context budget. A later runtime revision deduplicates identical observations, preserves conflicting observations and query failures, reuses collector summaries and reserves context before critic follow-ups. Global caps remain unchanged. Under the normal mixed model profile, the same Plain issue then completed all six roles and correctly diagnosed dependence on redacted raw tokens. Review clarifies the authenticated tool/proxy remedy. This recovery does not replace the failed original score. See `runs/context-recovery/`.

## Interpretation

Citation validity checks observed-record references, not prose entailment. A report with no findings scores zero for citation coverage; that is not evidence of invented IDs. Grounded-correct requires the correct cause/outcome plus all annotated evidence requirements. Finding/action precision measures overlap with authored annotations, not percentage of truthful prose. Manual reviews flag unnecessary remedies and unsupported detail. The team improved grounded-correct coverage here (85% versus 75%) at roughly three times the reported tokens, with equal cause accuracy. This small author-visible synthetic cohort does not establish general superiority.

## Included submission artifacts

The preserved run directories referenced above are included under `submission/evaluation/` with the same cohort names. Use `python scripts/verify_submission.py` for credential-free score/hash verification. The current runtime has later context, custom-intake, KB-fallback and finding-consolidation revisions; their operational checks do not replace or extend the frozen twenty-case model scores.
