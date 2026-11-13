# Vercel deployment

Deployment changes live on the `vercel-deployment` branch; `main` remains the original local-review submission. Select this branch for the Vercel deployment. In an existing project, set **Settings → Environments → Production → Branch Tracking** to `vercel-deployment`, or deploy it as a preview with the matching preview environment variables. Do not change the GitHub repository's default branch.

This adapter is separate from the local `orange serve` process. It runs FastAPI as a Vercel Function, stores tickets/events/results/outbound state in Postgres and sends bounded jobs through native Vercel Queues. Docker is only an optional local Postgres testing tool; deployment does not use Docker.

## Import settings

| Vercel field | Value |
| --- | --- |
| Branch | `vercel-deployment` |
| Framework / Application Preset | **FastAPI** |
| Root Directory | `./` |
| Build Command | Default; do not override |
| Install Command | Default; do not override |
| Output Directory | Default; do not override |
| Python | **3.12**, selected by `.python-version` |

`app.py` exports the ASGI application. `pyproject.toml` declares the application entrypoint and two private queue subscribers. `vercel.json` sets a 300-second function limit, `iad1` region and required data/static artifacts. Static CDN promotion is explicitly disabled so assets pass through the reviewer-login guard. Do not set the output directory to `web/`: the portal calls the Python backend.

## Database and environment

Create a dedicated Neon Postgres database from **Project → Storage → Create Database**, connect it to this project, and use its **pooled** connection URL as `DATABASE_URL`. US East is close to the configured function/queue region. A different Postgres provider works if it exposes a standard Postgres connection URL. The adapter creates its own tables and indexes on first use; do not point it at an unrelated application's shared tables.

Set these in **Settings → Environment Variables** for the deployment environment:

| Name | Value |
| --- | --- |
| `DATABASE_URL` | Pooled Postgres connection URL supplied by the storage integration |
| `DEMO_USERNAME` | `reviewer` or your chosen login name |
| `DEMO_PASSWORD` | A strong random shared demo password, at least 16 characters |
| `INVESTIGATION_RUNTIME` | `openai` for the real team; `simulation` for offline-style fixture checks |
| `OPENAI_API_KEY` | Your funded API key; required in `openai` mode |
| `OPENAI_MODEL` | `gpt-4.1-mini` |
| `OPENAI_REASONING_MODEL` | `gpt-5.4` |
| `PLAIN_MODE` | `live` to connect Plain; otherwise `simulated` |
| `PLAIN_API_KEY` | Required only for live Plain |
| `LINEAR_ENABLED` | `true` to send Linear updates; otherwise `false` |
| `LINEAR_API_KEY`, `LINEAR_TEAM_ID` | Required when Linear is enabled |
| `SLACK_ENABLED` | `true` to send Slack updates; otherwise `false` |
| `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` | Required when Slack is enabled |

Do not configure `codex` runtime on Vercel. It depends on local CLI authentication. Queue credentials are supplied automatically by Vercel OIDC; do not add a separate queue-provider key. Keep production and preview databases/credentials separate if enabling both environments.

The locally prepared ignored `.env.vercel` file, if present, contains demo access credentials and the existing service configuration for convenient transfer into Vercel. It is never committed or packaged. It deliberately omits an unknown `DATABASE_URL` so it cannot overwrite the storage integration's URL with a blank value. Share the demo login privately with reviewers.

If the project does not exist yet, you may create the initial deployment before adding Storage. The entrypoint can import/build without secrets or a database. Until required values are present it responds with setup-required/503 and performs no inference. Add Storage/environment values and **redeploy** after changing them.

## Queue operation and reliability

The queue infrastructure invokes private subscribers for `orange-investigations` and `orange-deliveries`; there is no public worker callback. Each consumer group has concurrency one and bounded delivery attempts. No continuously running background process, cron or open browser is needed to keep a dispatched job running.

The ticket is committed before queue dispatch. Failed/unconfirmed publishing returns a generic 503 without deleting the ticket. Repeat submission with the same idempotency key or use **Resume queued work** in Operations. If the HTTP caller loses its key, locate the existing issue in Operations rather than create a second complaint. The resume action dispatches saved work; it does not approve a repair or silently retry failed paid inference.

Atomic database claims and queue deduplication keys prevent concurrent normal claims of the same run. Paid investigation execution uses a lease. A completed run is not repeated on message redelivery. A hard-killed invocation becomes an explicit failure after its lease expires; retry is a deliberate action. Cold starts do not mark other workers' active runs interrupted. Queue delivery itself is at least once, not an exactly-once guarantee.

The hosted model deadline is **240 seconds**. The worker has a 275-second outer bound and the function maximum is 300 seconds. Hosted runs can therefore terminate sooner than local runs, whose model deadline remains 360 seconds. A report can be inconclusive, or a runtime can fail; those are different outcomes. The frozen benchmark was not rerun on these new hosting limits.

Notification jobs run separately and are targeted to a ticket. Uncertain interrupted external writes become `attention_required`, not blind external-create retries. Pending dispatch after a crash may require the resume action; this is not a transactional guarantee between Postgres and the queue service. After queue delivery attempts are exhausted, inspect the failed message, ticket activity and saved state before resuming.

Canonical reports, evidence envelopes, role activity and provider usage events persist in Postgres. Local trace files are temporary scratch files on Vercel and are discarded after the job; the mounted filesystem is not treated as persistent storage. Existing local SQLite tickets are not automatically migrated to Postgres. Packaged benchmark results remain visible in a fresh deployment.

## Access and verification

All application pages, assets and API operations require the demo's HTTP Basic login over Vercel HTTPS. The only unauthenticated route is `/healthz`, which exposes minimal setup status and missing variable names. Authenticated `/api/health` reports actual runtime/integration configuration. Cross-origin writes are rejected and application responses are private/no-store. This is a private reviewer demo, not multi-user authentication or tenant isolation.

After deployment:

1. Open `/healthz` and confirm `status: ok`.
2. Open `/` in an incognito window. Confirm it asks for the demo login and rejects a wrong password.
3. Sign in. Confirm the 52 environments and packaged Evaluation results load.
4. Submit one fictional ticket. Confirm its correlated Plain read, private queue dispatch, agent activity and final report.
5. Confirm Linear/Slack acknowledgments in the ticket's delivery log. Customer responses remain drafts.
6. Refresh/reopen the app and verify the ticket remains present. A deployment is not end-to-end verified until these checks have been performed on its actual URL.

Local tests exercise real Postgres, duplicate claims, expired leases, no replay of completed inference, auth-before-storage, cross-origin rejection and fake queue dispatch. They do not prove production OIDC/queue routing or access to the selected cloud services.

Official references: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Python Queue SDK](https://vercel.com/docs/queues/python-sdk), [function limits](https://vercel.com/docs/functions/limitations), [Marketplace storage](https://vercel.com/docs/marketplace-storage).
