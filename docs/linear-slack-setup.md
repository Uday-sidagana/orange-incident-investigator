# Linear and Slack setup

The standalone backend uses service API credentials. Chat plugins are optional conveniences, not the credential transport used by this local server. No model access is required for these integrations.

## Linear

1. Use a demo workspace/team.
2. Create a personal API key in Linear's Security & access settings. It needs access to the target team and permission to read, create, and update issues. Admin access is unnecessary for this flow.
3. Save it as `LINEAR_API_KEY` in the ignored local `.env` file.
4. Supply the team name/key to the setup check, or put its UUID, unique short key, or exact name in `LINEAR_TEAM_ID`; short keys/names are resolved before issue creation. The check can list accessible teams; it does not create an issue.

Personal keys use `Authorization: <key>`, whereas OAuth tokens use a Bearer header. The current adapter expects a personal key.

## Slack

1. Create a Slack app from `config/slack-app-manifest.json` at https://api.slack.com/apps.
2. Select the demo workspace and install the app. The manifest requests `chat:write` and `channels:read` for a public channel.
3. Save the **Bot User OAuth Token** as `SLACK_BOT_TOKEN` in `.env`. Do not use a signing secret, app-level token, client secret, or user token.
4. Create/select a public demo channel, such as `#orange-incidents`, and invite the bot to it.
5. Supply the channel name to the setup check, or put its channel ID in `SLACK_CHANNEL_ID`.

For a private channel, channel inspection/discovery needs appropriate private-channel read access (`groups:read`) and membership. The supplied manifest intentionally starts with a public-channel configuration. No Slack signing secret, incoming webhook, Socket Mode connection, or event subscription is needed: this version sends outbound messages only.

## Local configuration

```dotenv
LINEAR_API_KEY=
LINEAR_TEAM_ID=
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
LINEAR_ENABLED=false
SLACK_ENABLED=false
```

Never paste tokens in chat, screenshots, commit messages, or tracked files. The ignored `.env` already contains these entries and is readable only by the local account.

Read-only checks:

```sh
orange integrations-check
orange integrations-check --team-name "Your team name" --channel-name "orange-incidents"
```

The second command resolves and saves matched destination IDs to `.env`. Checks do not create issues, send messages, or change enable flags. Slack membership is verified when a destination is configured. Auth/read verification does not prove write scopes; a controlled demo send is still required to verify posting.

Once credentials/destinations are verified, set the corresponding enable flags to `true` and restart the server. The two services can be enabled independently. The simulation runtime remains independent of both integrations.

## Workflow

- When a ticket reaches investigation, the backend queues a Linear issue and a Slack root notification.
- On completion/failure, it queues updates. Linear updates the existing issue description. Slack posts a reply under the stored root message, using the original channel even if the global default changes.
- Human reviews queue another update. They do not automatically send a customer reply, execute a fix, or train a model.
- The initial external IDs are stored persistently. Completed/pending deliveries are deduplicated by ticket, provider, and stage.
- Existing tickets are not automatically broadcast just because an integration is enabled. Use **Sync to integrations** on a ticket to enqueue its intake/report explicitly.
- Optional notification failures remain separate from the investigation result. Operations shows delivery states and permits retry of definitively failed requests.

The outbound worker runs separately from investigation, so network delays do not block diagnosis. The simulation can finish before a notification arrives; this is a durable asynchronous integration, not a promise of strict notification-before-diagnosis timing.

## Uncertain delivery

There is no exactly-once guarantee across a process crash or network timeout. A timed-out issue/message creation may have succeeded remotely. Such jobs become `attention_required` and are not blindly retried. A restart treats in-flight deliveries the same way. Inspect the destination and reconcile the stored reference before continuing. Definite rejections can be explicitly retried, and dependent updates resume after the initial reference is stored.

Writes have no automatic HTTP retry. A rejected GraphQL mutation with partial/uncertain results is conservatively held for inspection. External updates do not replace local evidence traces or affect reported root-cause confidence.

## Current verification

Adapters, durable delivery jobs, root-reference reuse, failed/uncertain outcomes, restart handling, Slack mention escaping, independent investigation completion, and API wiring have mocked tests. Linear authentication, Sidagana team mapping, issue creation, and report update were verified in the explicitly authorized live test: SID-5. After the bot was invited, Slack intake posting and a report reply in the same thread succeeded. All four demo deliveries completed; the original Linear issue was reused. Both integrations are now enabled for new tickets. Channel metadata inspection additionally needs an optional read scope; this does not replace the posting/membership check.

## Primary references

- https://linear.app/developers/graphql
- https://docs.slack.dev/app-manifests/
- https://docs.slack.dev/reference/methods/auth.test/
- https://docs.slack.dev/reference/methods/chat.postMessage/
- https://docs.slack.dev/reference/methods/conversations.info/
