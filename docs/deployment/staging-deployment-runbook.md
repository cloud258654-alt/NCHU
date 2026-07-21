# Shared Staging Deployment Runbook

Status: Core profile prepared locally / waiting for staging runtime configuration

## Core profile (005A)

Use `STAGING_DEPLOY_PROFILE=core` to deploy backend, Supabase, staging n8n and
gateway prerequisites without LINE/LIFF credentials or workflow publication.
Core uses only local n8n callback settings (`N8N_HOST=localhost` and
`N8N_WEBHOOK_URL=http://127.0.0.1:5679/`) and reports LINE/LIFF/public HTTPS
as deferred. Use `full` only after the external LINE configuration is complete.

## Scope

This runbook covers the isolated Customer Validation Gate C2 staging topology.
It must not be used for production deployment.

## Staging Topology

```text
app directory: /home/harcker8119/BI-RMP-STAGING
environment file: /home/harcker8119/BI-RMP-STAGING/.env.staging.runtime
systemd service: bi-rmp-staging.service
backend listen: 127.0.0.1:8101
n8n host port: 127.0.0.1:5679
gateway port: 8180
compose project: bi-rmp-staging-n8n
n8n container: bi-rmp-staging-n8n
n8n postgres container: bi-rmp-staging-n8n-postgres
deployment lock: /tmp/bi-rmp-staging-deploy.lock
```

Known production values that must not be touched:

```text
app directory: /home/harcker8119/BI-RMP
systemd service: bi-rmp.service
backend port: 8001
n8n host port: 5678
gateway port: 8080
compose project: bi-rmp-n8n
containers: bi-rmp-n8n, bi-rmp-n8n-postgres
```

## Required Files

```text
.env.staging.example
scripts/deploy-staging.sh
scripts/verify-staging.sh
scripts/rollback-staging.sh
infra/systemd/bi-rmp-staging.service.example
infra/nginx/bi-rmp-staging-gateway.conf.example
infra/n8n/docker-compose.staging.yml
database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql
```

## Environment Contract

Copy `.env.staging.example` to the staging runtime env file and fill real
values only on the host. Do not commit the runtime file.

The staging database target must satisfy:

```text
APP_ENV=staging
SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe
ALLOW_DATABASE_WRITES=true
ALLOW_PRODUCTION_DB=false
```

Core profile requires the following keys; the scripts check only their presence
and never print their values:

```text
DATABASE_URL
BI_RMP_INTERNAL_API_KEY
N8N_ENCRYPTION_KEY
N8N_DB_PASSWORD
```

The core profile also requires these local n8n settings:

```text
N8N_HOST=localhost
N8N_WEBHOOK_URL=http://127.0.0.1:5679/
```

The following are full-profile-only and must not block a core deployment:

```text
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
LINE_LIFF_ID
LINE_LOGIN_CHANNEL_ID
BI_RMP_LINE_ALLOWED_USER_IDS
N8N_WORKFLOW_ID
```

The scripts must print only `PRESENT`, `MISSING`, or `INVALID_FORMAT` for these
keys. They must not print values.

## LINE Allowlist

Shared staging uses `BI_RMP_LINE_ALLOWED_USER_IDS`. The guard is active only
when `APP_ENV=staging` and the variable is non-empty.

Blocked users must not create:

```text
clients
business
service_tasks
crawl_jobs
crawl_posts
crawl_comments
analysis_results
client_messages_log
```

Blocked users receive a fixed staging restriction message. The allowlist value
must not be logged, returned by API, or written to docs.

## Reverse Proxy

Only these public paths are intended:

```text
GET  /health
GET  /register
GET  /api/liff/config
POST /api/liff/business/register
POST /webhook/line/events
```

Do not expose:

```text
n8n editor UI
n8n REST management API
Backend docs
Backend OpenAPI
PostgreSQL
Docker ports
internal-only Backend APIs
```

Use a normal HTTPS server block or a trusted tunnel in front of the staging
gateway. The n8n editor remains reachable only through local host access or an
SSH tunnel.

## Staging Deployment Flow

The required deployment sequence for initial installation and repeatable redeployment is:

```text
bootstrap host
→ 建立 runtime env
→ 確認 LINE／LIFF／HTTPS 外部設定
→ deploy staging
→ install/reload public gateway
→ verify staging
→ real LINE E2E
```

### 1. Host Bootstrap

On the staging host (executed once for initial setup, or re-run safely as an idempotent step):

```bash
cd /home/harcker8119/BI-RMP-STAGING
scripts/bootstrap-staging-host.sh --hostname staging.example.com
```

The bootstrap script:

- requires explicit Staging hostname
- creates `/home/harcker8119/BI-RMP-STAGING` and `.venv`
- copies `.env.staging.example` to `.env.staging.runtime` only if missing
- installs `bi-rmp-staging.service` to `/etc/systemd/system/bi-rmp-staging.service`
- runs `systemctl daemon-reload` and enables `bi-rmp-staging.service`
- does not start the Backend service prior to env configuration
- installs Staging Nginx gateway config to `/etc/nginx/sites-available/bi-rmp-staging-gateway.conf`
- validates Nginx config with `nginx -t`
- does not modify Production server blocks
- keeps n8n editor bound strictly to `127.0.0.1:5679`
- does not print or generate secrets
- is fully idempotent and does not run migrations

### 2. Deployment

On the staging host:

```bash
cd /home/harcker8119/BI-RMP-STAGING
STAGING_DEPLOY_PROFILE=core scripts/deploy-staging.sh <target-sha>
```

The deploy script:

- uses a staging-only lock file
- rejects known production path, service, port, compose, and container names
- validates target commit
- accepts the core-profile branch or an explicit target SHA when deploying core
- rejects database or Supabase diffs except the C2 rollback rehearsal SQL
- verifies listener ports (8101 owned by `bi-rmp-staging.service`, 5679 mapped by `bi-rmp-staging-n8n`, 8180 owned by Staging Nginx gateway) to allow repeatable deployments while blocking unknown process collisions
- creates a file backup before switching code
- installs Python requirements
- runs compile and focused tests
- restarts only `bi-rmp-staging.service`
- starts only the staging n8n compose project
- in core mode, defers LINE/LIFF workflow import and public HTTPS checks
- in full mode, imports the workflow with a fixed `N8N_WORKFLOW_ID`
- does not run migrations

## Verification

```bash
STAGING_DEPLOY_PROFILE=core scripts/verify-staging.sh
```

The core verification checks backend, gateway, Supabase, n8n, and n8n
PostgreSQL readiness; it expects `/api/liff/config` to return HTTP 503 and
reports LINE/LIFF, customer E2E, and public HTTPS as deferred.

## Rollback

```bash
STAGING_DEPLOY_PROFILE=core scripts/rollback-staging.sh <previous-sha>
```

If `<previous-sha>` is omitted, the script uses the latest recorded staging
backup metadata. It restarts only staging backend and staging n8n services. It
does not delete Supabase data and does not run rollback migrations.

## Rollback Rehearsal

Use `database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql` only
after creating a `C2-E2E-TEST-{UTC_TIMESTAMP}` test business. Review the
selector before execution. The script is transactional and ends with
`ROLLBACK;`.
