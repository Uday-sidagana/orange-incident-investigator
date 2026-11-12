# Deterministic workflow verification

These are authored simulation regression checks, not LLM accuracy or held-out evaluation. The diagnostic rules were written with knowledge of the scenario families. No model was called by these runs.

| Incident | Outcome | Leading diagnostic hypothesis | Tool calls | Critic control rounds |
| --- | --- | --- | ---: | ---: |
| auth-002 | probable_cause | missing_grant | 9 | 1 |
| cursor-010 | probable_cause | trigger_old_connection | 8 | 0 |
| duplicate-011 | probable_cause | unsafe_send_retry | 8 | 0 |
| gmail-001 | probable_cause | recipient_mapping_regression | 10 | 1 |
| pool-008 | probable_cause | connection_pool_exhaustion | 8 | 0 |
| provider-003 | probable_cause | provider_failure | 10 | 1 |
| quota-004 | probable_cause | provider_rate_limit | 8 | 0 |
| refresh-007 | probable_cause | credential_store_unavailable | 9 | 0 |
| signature-006 | probable_cause | webhook_secret_mismatch | 9 | 1 |
| tenant-009 | probable_cause | project_boundary_mismatch | 8 | 0 |
| unknown-012 | inconclusive | unconfirmed_change | 9 | 0 |
| webhook-005 | probable_cause | customer_endpoint_failure | 8 | 0 |

All twelve authored checks met their expected outcome and annotated evidence requirements. This verifies the finite policies and workflow mechanics only. The unknown case remains inconclusive rather than inventing a cause.

99 automated tests passed. They cover all six roles, critic-directed verification, incident-ID renaming, removal of causal observations, missing control evidence, retry/call budgets, record citations, derived-view provenance, queued portal execution, reviewer feedback, and rejection of invalid shared-state updates.

The existing live Plain demo thread was also read back and replayed through the six-role simulation: 10 tool calls, one control round, reviewable report, no new Plain records, no customer reply, and no pipeline model requests.

JavaScript syntax checks passed. Browser visual QA remains pending after the earlier headless-browser infrastructure timeout.

Reproduce with `orange simulate-suite --output runs/simulation-check` followed by `orange score --submissions runs/simulation-check/submissions --output runs/simulation-check/evaluation`.
