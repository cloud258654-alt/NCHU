# n8n and LINE Integration Plan

## Purpose

BI-RMP will use n8n as the automation layer between LINE user events and the backend reputation monitoring workflow.

The repository should store infrastructure definitions and sanitized workflow exports, not live Docker containers. Each developer recreates the local n8n runtime from `infra/n8n/docker-compose.yml`. Runtime variables are consolidated in the root `.env.example` / `.env` pair to avoid scattered environment templates.

## Responsibility boundary

```text
GitHub Actions CI
- Runs backend tests on push and pull request.
- Validates that the n8n Docker Compose file is syntactically valid.
- Does not host n8n.
- Does not keep runtime workflow state.

Docker Compose n8n runtime
- Runs local n8n and PostgreSQL containers.
- Receives LINE webhook events during local or deployed testing.
- Calls BI-RMP backend services.
- Stores n8n workflows, credentials, and execution history in Docker volumes/PostgreSQL.
```

These two are not duplicated work. CI checks whether the project is healthy. Docker Compose creates the local automation runtime.

If the team does not rely on GitHub Actions checks, `.github/workflows/ci.yml` can be removed later. For now, keeping it gives the team a low-cost guardrail: backend tests plus Docker Compose config validation before changes enter `main`.

## Local development architecture

```text
LINE Official Account
-> LINE Messaging API webhook
-> public HTTPS tunnel or deployed reverse proxy
-> n8n Webhook node
-> n8n normalization / decision workflow
-> BI-RMP backend API or runner endpoint
-> database tables: clients / business / service_tasks / crawl_jobs / alerts
-> n8n sends a Reply API message through LINE Messaging API
```

## Zero-Push asynchronous workflow

```text
1. Webhook node
   Path: line/events
   Method: POST

2. Code / IF nodes
   Verify the LINE signature.
   Extract `line_user_id`, message text, `reply_token`, `webhook_event_id`, and
   route a `crawl_status:<task_id>` postback or the text `查詢進度` to the
   status branch.

3. HTTP Request node
   Register or update the LINE user in `clients`, then recognize the first
   active business owned by that client:
   POST ${BI_RMP_BACKEND_BASE_URL}/api/line/client-recognition

4. Code / IF nodes
   If client registration or business recognition fails because the backend or
   database is unavailable, prepare a short LINE maintenance message.
   If a business is found, continue through the registered-business path.
   If no business is found, prepare a LINE notice that includes the user's LINE
   ID and says the store data is not registered yet. Do not continue to a
   global or demo report path for a registered-customer request.

5. HTTP Request and Reply nodes
   For a registered business, create a durable task first:

   ```text
   POST ${BI_RMP_BACKEND_BASE_URL}/api/line/reputation-crawler/jobs
   ```

   Reply immediately with the accepted message and a `查詢進度` Quick Reply.
   This Reply node must execute before the Run Job node.

6. HTTP Request node
   After the accepted Reply finishes, start the idempotent crawler run:

   ```text
   POST ${BI_RMP_BACKEND_BASE_URL}/api/line/reputation-crawler/jobs/{task_id}/run
   ```

   This node can wait for the background work inside the same n8n execution.
   It does not send a result message and the workflow contains no LINE Push
   node. The backend admits one full business job at a time per instance, then
   runs the platform pipelines with bounded async concurrency. PTT and Threads
   start immediately; Google Maps source discovery blocks only its own crawler.
   Google Maps and Threads use isolated Chromium instances with a configurable
   browser concurrency limit of two.

7. Status interaction branch
   Every Quick Reply click creates a new LINE webhook event and reply token.
   The workflow calls one of:

   ```text
   POST ${BI_RMP_BACKEND_BASE_URL}/api/line/reputation-crawler/jobs/{task_id}/status
   POST ${BI_RMP_BACKEND_BASE_URL}/api/line/reputation-crawler/jobs/status/latest
   ```

   The request includes `line_user_id`; a task owned by another LINE user is
   returned as not found. Pending or running tasks receive a progress Reply and
   another Quick Reply. Completed or partial tasks continue to the report API.
   Failed, timed-out, or cancelled tasks receive an error Reply selected from
   public status/error-type mapping. The customer-facing formatter must not
   include backend `error_message`, SQL, connection strings, Supabase refs,
   tokens, credentials, stack traces, or local paths.

8. HTTP Request node
   Return the quantitative report only for a completed or partial owned job:
   POST ${BI_RMP_BACKEND_BASE_URL}/api/line/reputation-summary

   The request includes `line_user_id` and, for status-triggered reports,
   `task_id`. The backend validates that the task resolves through
   `service_tasks.business_id -> business.client_id -> clients.line_user_id`
   before reading canonical crawl data.

9. Code node
   If the report API returns `line_messages`, pass them to LINE.
   If the report API fails, prepare a short maintenance message.

10. HTTP Request node
    Reply through LINE Messaging API using the reply token from the current
    interaction.
```

The workflow intentionally does not notify users proactively. They must click
`查詢進度` or send that text later. This keeps crawler progress and completed
results on Reply API messages while retaining tenant-scoped report delivery.
Users without registered store data receive a registration Flex Message through
the current Reply API interaction. The registration button is included only
when `LINE_LIFF_ID` or the fallback `BI_RMP_REGISTRATION_URL` is configured.

## Environment variables

All non-secret example values are kept in the root `.env.example` file. Copy it to `.env` and keep real local values out of Git.

```text
N8N_WEBHOOK_URL              Public base URL used by n8n webhook URLs.
N8N_ENCRYPTION_KEY           Fixed key used to encrypt n8n credentials.
N8N_DB_PASSWORD              Local PostgreSQL password for n8n metadata.
BI_RMP_BACKEND_BASE_URL      Backend URL reachable from the n8n container.
BI_RMP_REGISTRATION_URL      Optional public HTTPS non-LIFF registration page.
LINE_LIFF_ID               LIFF app ID used by the registration button and frontend initialization.
LINE_LOGIN_CHANNEL_ID        LINE Login channel ID used to verify LIFF ID tokens.
LINE_CHANNEL_ACCESS_TOKEN    LINE Messaging API access token.
LINE_CHANNEL_SECRET          LINE channel secret used for request validation.
BI_RMP_REPUTATION_CRAWL_MAX_ACTIVE_JOBS  Full business jobs admitted per backend instance (default 1).
BI_RMP_REPUTATION_CRAWL_PTT_MAX_MINUTES  PTT time budget (default 2 minutes).
BI_RMP_REPUTATION_CRAWL_GOOGLE_MAPS_MAX_MINUTES  Google Maps budget including source discovery (default 3 minutes).
BI_RMP_REPUTATION_CRAWL_THREADS_MAX_MINUTES  Threads time budget (default 3 minutes).
BI_RMP_REPUTATION_CRAWL_BROWSER_CONCURRENCY  Concurrent Chromium-backed platforms (default 2).
BI_RMP_REPUTATION_CRAWL_PERSISTENCE_GRACE_SECONDS  Cleanup and persistence grace after crawl budget (default 30 seconds).
```

Production deployment reads `.env` from
`/home/harcker8119/BI-RMP/.env` on the GCP server. In addition to the common
variables above, it reads these deployment values:

```text
N8N_WORKFLOW_ID       Existing production n8n workflow ID to overwrite.
N8N_PROJECT_ID        Optional n8n project owner for imports.
N8N_USER_ID           Optional n8n user owner for imports.
```

Set only one of `N8N_PROJECT_ID` or `N8N_USER_ID`. Every
production deployment syncs `infra/n8n/workflows/reputation-optimization-flow.json`
into n8n, then publishes or activates it and restarts n8n so webhook changes
take effect. Prefer setting `N8N_WORKFLOW_ID` on GCP. If it is omitted,
the deploy script exports existing n8n workflows and only proceeds when it can
find exactly one workflow matching the repository workflow name or webhook path.

Real secrets must stay in `.env`, n8n credentials, or a deployment secret manager. Do not commit real secret values.

## Registration URL

LIFF is the preferred registration flow. Set the LIFF Endpoint URL in LINE
Developers Console to the public backend route `https://{public-host}/register`,
then configure the LIFF app ID and its LINE Login channel ID:

```text
LINE_LIFF_ID=1234567890-AbcdEfgh
LINE_LOGIN_CHANNEL_ID=1234567890
BI_RMP_REGISTRATION_URL=
```

Get the values from the LINE Developers Console under the same provider as the
Messaging API channel:

1. Open the LINE Login channel, select **Basic settings**, and copy **Channel
   ID** to `LINE_LOGIN_CHANNEL_ID`.
2. Select the **LIFF** tab, add or open the registration app, and copy **LIFF
   ID** to `LINE_LIFF_ID`.
3. Configure the LIFF app with endpoint URL
   `https://{public-host}/register`, size `Full`, and scopes `openid` and
   `profile`.
4. Publish the LINE Login channel before opening registration to users who are
   not channel Admins or Testers.

`BI_RMP_REGISTRATION_URL` should remain empty for this LIFF flow. It is not the
LIFF Endpoint URL and it does not need to be copied from LINE Developers
Console.

### Registration completion notification

After the database registration succeeds, the backend sends one best-effort
Flex push message through the Messaging API. It confirms the registered store,
explains how to start an analysis, and provides a **開始分析** button that sends
the store name back to the existing LINE workflow.

This uses the existing `LINE_CHANNEL_ACCESS_TOKEN`; no additional environment
variable is required. Put that token in the backend service environment as
well as n8n's credential/configuration. The LINE Login channel, LIFF app, and
Messaging API channel must be under the same provider so their LINE user IDs
match.

The user must have added the LINE Official Account as a friend, or have sent it
a one-to-one message within the preceding seven days, for the push to be
delivered. LINE can return a successful API response even when a user who has
not added the account as a friend does not receive the message. A missing token
or a LINE delivery failure does not roll back the completed store registration;
the LIFF page still confirms registration and asks the user to return to LINE.

The production deploy script requires both LIFF values and verifies the backend,
registration page, and LIFF configuration at `http://127.0.0.1:8001`. Before
configuring the LIFF Endpoint URL, the deployed HTTPS reverse proxy must route
these public paths to that backend service:

```text
GET  /register
GET  /api/liff/config
POST /api/liff/business/register
```

Do not expose port `8001` directly without HTTPS. Use the existing production
reverse proxy or a dedicated public application hostname.

If the LIFF URL opens a 404 page, the LIFF URL itself is usually valid but its
configured Endpoint URL is not reaching the FastAPI service. Copy the location
rules from `infra/nginx/bi-rmp-liff-locations.conf.example` into the active
HTTPS Nginx `server` block, then validate and reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
curl --fail https://{public-host}/register
curl --fail https://{public-host}/api/liff/config
```

The HTTPS hostname must resolve to the GCP ingress or VM and present a publicly
trusted certificate. After both requests succeed, set the LIFF Endpoint URL to
the same `https://{public-host}/register` value. The example Nginx file is not
installed automatically by the deployment script because the production TLS
server block and hostname are managed outside this repository.

### Shared ngrok endpoint for n8n and LIFF

An ngrok free account has one assigned development domain. Do not use
`--pooling-enabled` to combine the n8n and backend ports because pooling would
load-balance requests between different applications. Instead, route both
applications through one local Nginx gateway and expose that gateway through the
existing ngrok domain.

On the GCP VM, install Nginx if it is not already present, then enable the
repository gateway:

```bash
sudo cp \
  /home/harcker8119/BI-RMP/infra/nginx/bi-rmp-ngrok-gateway.conf.example \
  /etc/nginx/conf.d/bi-rmp-ngrok-gateway.conf
sudo nginx -t
sudo systemctl reload nginx

curl --fail http://127.0.0.1:8080/register
curl --fail http://127.0.0.1:8080/api/liff/config
curl --fail http://127.0.0.1:8080/ >/dev/null
```

Find and stop the existing ngrok process or service that currently forwards the
assigned domain directly to n8n, then start the domain against the gateway:

```bash
pgrep -af ngrok
sudo ngrok service stop
ngrok http 8080
```

The assigned ngrok hostname remains the n8n webhook base URL. Set the LIFF
Endpoint URL to `https://{assigned-ngrok-host}/register`. Verify both routes
through ngrok before updating LINE Developers Console:

```bash
curl --fail \
  -H 'ngrok-skip-browser-warning: 1' \
  https://{assigned-ngrok-host}/api/liff/config
curl --fail \
  -H 'ngrok-skip-browser-warning: 1' \
  https://{assigned-ngrok-host}/register
```

The free plan injects an interstitial warning page for first-time browser HTML
traffic. It is acceptable for controlled testing, but a paid ngrok plan or a
normal HTTPS hostname is required for a registration flow without that warning.

The Flex button automatically uses `https://liff.line.me/{LIFF_ID}` when
`LINE_LIFF_ID` is configured. The LIFF page sends only the raw ID token to
`POST /api/liff/business/register`. The backend verifies that token with LINE,
derives the LINE user ID from the verified `sub` claim, and then calls the
existing business registration repository. The user enters a required contact
name and store name; these are stored as `clients.name` and `business.name`.
Client-supplied LINE user IDs are rejected. The legacy public n8n
`register-business` webhook has been removed so it cannot bypass LIFF identity
verification.

`BI_RMP_REGISTRATION_URL` remains available only for a non-LIFF fallback. It
must point to a public HTTPS page that displays and submits the registration
form. It must not point directly to an n8n webhook.

Use one of these fallback deployment shapes:

```text
BI_RMP_REGISTRATION_URL=https://register.example.com/register
```

Leave the value empty until the registration page exists. In that state, the
Flex Message explains that registration is not yet available and omits the
button instead of sending users to a placeholder domain. A non-LIFF fallback
may receive `line_user_id` for form prefill only; it must never treat that query
parameter as authenticated identity.

## Local LINE webhook note

LINE requires a public HTTPS webhook endpoint. A local n8n UI at `http://localhost:5678` is not enough for LINE to send events. During local testing, expose n8n through a trusted HTTPS tunnel or deploy n8n to a cloud/VPS environment.

For local tunnel testing, set these values in the root `.env` file:

```text
N8N_WEBHOOK_URL=https://your-public-tunnel.example.com/
N8N_PROTOCOL=https
N8N_PROXY_HOPS=1
N8N_SECURE_COOKIE=true
```

Then restart n8n:

```powershell
docker compose --env-file .env -f infra/n8n/docker-compose.yml down
docker compose --env-file .env -f infra/n8n/docker-compose.yml up -d
```

## Cross-computer development rule

When switching computers, run the Docker Compose stack again. The containers will be recreated on the new computer.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infra/n8n/docker-compose.yml up -d
```

If you only need workflow design, export sanitized workflow JSON and place it under `infra/n8n/workflows/`.

If you need credentials and execution history, backup and restore the n8n PostgreSQL/volume data and keep the same `N8N_ENCRYPTION_KEY`.

For a team or production environment, prefer a shared hosted n8n instance rather than each developer's local Docker Desktop.
