# Incident scenarios for Uday’s review

No model weights have been trained. These are authored synthetic incident environments, not a list of facts fed to agents as answers. Expected causes and remedies below are for reviewer/evaluator use only. Only gmail-001 has been investigated in live Codex development runs so far. The added scenarios have deterministic simulation checks, not live-agent performance results.

The scenarios use fictional telemetry and infrastructure. Selected troubleshooting patterns were inspired by public Composio documentation; they are not reconstructions of private customer tickets.

| ID | Customer complaint | Expected explanation | Evidence that should distinguish it | Expected next step |
| --- | --- | --- | --- | --- |
| gmail-001 | Gmail sends began failing across customers around a release. | Recipient mapping regression in executor version 20261112. | Input contains a recipient; validation fails before provider execution; scopes exist; identical input differs across versions. | Roll back affected executor or repair mapping, then verify with regression checks. |
| auth-002 | Gmail sends fail for Atlas while other customers can send. | Connection has gmail.readonly but lacks required gmail.send grant. | Actual granted scopes differ from action requirements; another tenant succeeds; controlled grant change succeeds. | Reconnect with the required approved scope, then verify the affected action. |
| provider-003 | Slack actions return 503 across tenants after an executor release. | Upstream provider failure. | Provider returns 503 under both old and new executor versions; other provider traffic is healthy. | Back off, monitor upstream recovery, and verify; do not blindly roll back or patch the integration. |
| quota-004 | A Notion import causes 429 errors and rising latency. | Provider rate limit exceeded by tenant-specific concurrency. | Retry-After header, burst above quota, growing queue, unaffected low-volume tenant. | Respect Retry-After and lower concurrency. |
| webhook-005 | Trigger events appear internally but Atlas receives no callbacks. | Customer webhook endpoint is unavailable. | Provider ingress succeeds; outbound delivery gets 503 and retries; tenant backlog grows. | Restore endpoint, then replay pending deliveries with duplicate-handling checks. |
| signature-006 | Webhooks are rejected after a signing-secret rotation. | Sender and receiver use different keys. | Handler 401 signature mismatch; sender key-2 vs receiver key-1; matching-key control succeeds. | Synchronize secret configuration and verify before replay. |
| refresh-007 | Previously active connections fail across multiple toolkits. | Credential-store degradation prevents refresh. | Active badge coexists with refresh 503; expired credential cache; store latency/errors; dependency relationship. | Recover the credential store, then retry refresh and verify execution. |
| pool-008 | Tool discovery becomes slow, but DB CPU is low. | Catalog DB connection pool is exhausted after a capacity change. | Most latency is waiting for a pool slot, not SQL; pool is saturated; capacity changed from 100 to 20. | Restore appropriate capacity, check DB headroom, verify latency. |
| tenant-009 | Connections disappear after a customer moves projects. | Request and connection belong to different projects. | Connection exists in project-a; request uses project-b; unaffected tenant stays in project-a. | Use the correctly scoped connection/project; do not bypass ownership boundaries. |
| cursor-010 | Sending works after reconnect, but Gmail trigger events stop. | Trigger remains attached to the old disabled connection. | New connected account is active; old trigger is disabled and still uses the old account; reconnect changed identity. | Create/enable the trigger against the intended current connection and test a new event. |
| duplicate-011 | Attachment sends time out, yet recipients receive duplicates. | Client blindly retries a non-idempotent send after provider acceptance. | Same operation has two request IDs and two accepted provider message IDs; timeout is below attachment latency. | Verify send status before retrying and remove unconditional retries. |
| unknown-012 | Sporadic 502 responses, but diagnostic data is missing. | Inconclusive; no supported cause can be established. | Partial logs, persistent metrics failures, no controlled reproduction, contradictory historical examples. | Request request IDs, timestamps, affected versions and reproduction; restore telemetry. |

## Useful feedback for each case

Please reference the incident ID and add any of these:

- What would you ask the customer first?
- Which internal logs, tables, tools, or identifiers would you inspect, and in what order?
- What alternative causes produce the same symptom?
- What observation would disprove the expected explanation?
- What fix/workaround would you actually recommend, and what verification would you require?
- What should remain internal versus appear in the customer response?

For example: `auth-002: Before recommending reconnect, inspect the actual connected account grants rather than only the auth config’s requested scopes. Also check whether the customer selected a different account.`

## Dataset version 2

There are now 32 cases: 16 development and 16 held-out. The new cases and expected remedies are listed in [scenario-expansion-v2.md](scenario-expansion-v2.md). The original twelve fixtures are unchanged. The split is for future model evaluation; authored simulation rules are not independent evaluation.
