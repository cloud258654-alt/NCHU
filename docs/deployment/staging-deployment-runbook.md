# Shared Staging Deployment Runbook

Status: Prepared / waiting for external configuration

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

Required secret or external configuration keys are checked by name only:

```text
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
LINE_LIFF_ID
LINE_LOGIN_CHANNEL_ID
N8N_WEBHOOK_URL
N8N_ENCRYPTION_KEY
N8N_DB_PASSWORD
BI_RMP_INTERNAL_API_KEY
DATABASE_URL
BI_RMP_LINE_ALLOWED_USER_IDS
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

## Deployment

On the staging host:

```bash
cd /home/harcker8119/BI-RMP-STAGING
scripts/deploy-staging.sh <target-sha>
```

The deploy script:

- uses a staging-only lock file
- rejects known production path, service, port, compose, and container names
- validates the target commit
- accepts the Gate C2 branch or an explicit target SHA
- does not require the target SHA to be on `main`
- rejects database or Supabase diffs except the C2 rollback rehearsal SQL
- creates a file backup before switching code
- installs Python requirements
- runs compile and focused tests
- restarts only `bi-rmp-staging.service`
- starts only the staging n8n compose project
- imports the workflow with a fixed `N8N_WORKFLOW_ID`
- does not run migrations

## Verification

```bash
scripts/verify-staging.sh
```

The verification script checks service state, local health, LIFF page/config,
n8n readiness, configured container names, and public HTTPS routes when
`STAGING_PUBLIC_BASE_URL` is set.

## Rollback

```bash
scripts/rollback-staging.sh <previous-sha>
```

If `<previous-sha>` is omitted, the script uses the latest recorded staging
backup metadata. It restarts only staging backend and staging n8n services. It
does not delete Supabase data and does not run rollback migrations.

## Rollback Rehearsal

Use `database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql` only
after creating a `C2-E2E-TEST-{UTC_TIMESTAMP}` test business. Review the
selector before execution. The script is transactional and ends with
`ROLLBACK;`.
