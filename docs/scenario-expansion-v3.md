# Composio-inspired prospective evaluation cases

Twenty fictional customer incidents derived from public troubleshooting guidance. Telemetry, request IDs, tenants, changes and control outcomes are invented. These are not private Composio tickets or evidence of real provider outages. The evaluator answers below are never sent to agents.

| Case | Expected explanation | Correct next step | Public source |
| --- | --- | --- | --- |
| notion-access-033 | notion resource not shared | Share only the intended page with the existing Notion integration and verify access; do not widen unrelated permissions. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-notion) |
| notion-event-034 | trigger event kind mismatch | Select the current trigger for the intended update event and verify a new edit; preserve the existing connection. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-notion) |
| github-org-035 | github organization approval | Request approval from the GitHub organization owner for the intended OAuth app, then retest the organization resource. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-github) |
| github-token-036 | redacted token relay design | Route the provider request through authenticated tool/proxy execution rather than extracting a provider token. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-github) |
| github-setup-037 | obsolete trigger setup path | Create/upsert the V2 trigger directly through the supported trigger-instance path and verify a new event. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-github) |
| sheets-plane-038 | connection surface isolation | Connect Sheets through the MCP authentication flow used by this client; do not assume Platform connections are shared. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-googlesheets) |
| sheets-discovery-039 | tool discovery truncation | Paginate or raise the discovery limit, then execute the exact returned action slug on the intended version. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-googlesheets) |
| sheets-id-040 | spreadsheet identifier kind | Pass the intended spreadsheet ID, then verify the target and requested range before writing. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-googlesheets) |
| airtable-expiry-041 | authentication initiation expired | Start a fresh authentication initiation and complete it within its valid window; avoid retrying the expired link. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-airtable) |
| airtable-batch-042 | provider batch record limit | Split updates into batches of at most ten records, respect provider rate limits, and verify partial completion before retrying. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-airtable) |
| slack-user-043 | slack user scope configuration | Configure the needed user_scopes and reconnect the intended user; bot scopes do not authorize user-token actions. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack) |
| slack-plan-044 | provider feature entitlement | Check workspace eligibility and feature enablement; use a supported search alternative or obtain the required plan before retesting. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack) |
| slack-ingress-045 | provider event ingress misrouting | Restore the intended Slack app event-subscription ingress and verify a newly generated message before considering replay. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack) |
| slack-redirect-046 | oauth redirect uri mismatch | Match the OAuth app redirect setting to the auth config callback URI; keep the short per-connection link separate. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack) |
| gmail-shape-047 | attachment reference shape | Upload the file and pass the supported file object, then validate the serialized attachment argument before sending. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-gmail) |
| gmail-file-048 | temporary file reference expired | Upload a fresh file shortly before execution and use its current reference; verify send status before any retry. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-gmail) |
| session-policy-049 | session tool policy block | Keep least privilege: use an explicitly authorized narrow tool exception only if the workflow should write, then verify the effective policy. | [Composio guide](https://docs.composio.dev/kb/guide/platform-session-tool-policies) |
| log-gap-050 | Inconclusive | Collect a fresh permitted reproduction, request IDs and diagnostic metadata; missing stored payloads cannot establish the execution failure cause. | [Composio guide](https://docs.composio.dev/kb/guide/dashboard-log-storage) |
| delivery-dedupe-051 | webhook receiver not idempotent | Deduplicate receiver processing using a stable event/log identifier and verify retry behavior without assuming duplicate provider ingress. | [Composio guide](https://docs.composio.dev/kb/guide/platform-triggers) |
| slack-schedule-052 | scheduled attachment semantics | Upload the file separately and include its supported link in the scheduled message body, then verify the scheduled result. | [Composio guide](https://docs.composio.dev/kb/guide/toolkits-slack) |

New cohort: `prospective_comparison` in `evaluation/splits.json`. The previous development and held-out memberships are unchanged. New cases have no authored deterministic diagnosis policy; simulation remains useful for mechanics but its result on these cases is not a model accuracy score.

Global finding definitions are supplied equally to both approaches. Expected evidence requirements and cause mappings remain evaluator-only. Configuration is frozen in `runs/composio-v3/manifest.json` before the first live request.
