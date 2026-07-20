# Customer Validation Gate C2 Report

Date: 2026-07-20
Branch: `main`
Baseline commit: `10e0ec6`
Deployed commit: Host bootstrapped via `scripts/bootstrap-staging-host.sh`; live deployment pending external runtime config

## RESULT

```text
RESULT: WAITING_EXTERNAL_CONFIGURATION
```

Program files and local staging deployment artifacts were prepared. A real
shared staging deployment, LINE/LIFF E2E, public HTTPS smoke test, Supabase
readback, and rollback rehearsal were not executed from this local workspace
because SSH context, staging public host, LINE staging channel settings, and
runtime secrets were not available.

## Staging Topology

```text
STAGING_APP_DIR=/home/harcker8119/BI-RMP-STAGING
STAGING_BACKEND_SERVICE=bi-rmp-staging.service
STAGING_BACKEND_PORT=8101
STAGING_N8N_HOST_PORT=5679
STAGING_GATEWAY_PORT=8180
STAGING_COMPOSE_PROJECT_NAME=bi-rmp-staging-n8n
STAGING_N8N_CONTAINER=bi-rmp-staging-n8n
STAGING_N8N_POSTGRES_CONTAINER=bi-rmp-staging-n8n-postgres
STAGING_ENV_FILE=/home/harcker8119/BI-RMP-STAGING/.env.staging.runtime
STAGING_LOCK_FILE=/tmp/bi-rmp-staging-deploy.lock
```

## Production Isolation Evidence

The C2 scripts and examples use staging-only names and ports. They contain
guards that block known production values:

```text
/home/harcker8119/BI-RMP
bi-rmp.service
8001
5678
8080
bi-rmp-n8n
bi-rmp-n8n-postgres
```

No production deployment script was executed or modified.

## Supabase Target

Allowed staging target:

```text
Project: BI-RMP-V2-STAGING
Project ref: qlhykeeyjaoikczoambe
```

The existing runtime guard already requires `APP_ENV=staging`,
`SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe`, and
`ALLOW_PRODUCTION_DB=false`. C2 added `.env.staging.example` with the same
contract.

## Environment Configuration Presence

Local template status:

```text
APP_ENV=PRESENT
SUPABASE_PROJECT_REF=PRESENT
SUPABASE_URL=PRESENT
DATABASE_URL=PLACEHOLDER_EMPTY
ALLOW_DATABASE_WRITES=PRESENT
ALLOW_PRODUCTION_DB=PRESENT
BI_RMP_INTERNAL_API_KEY=PLACEHOLDER_EMPTY
BI_RMP_LINE_ALLOWED_USER_IDS=PLACEHOLDER_EMPTY
LINE_CHANNEL_ACCESS_TOKEN=PLACEHOLDER_EMPTY
LINE_CHANNEL_SECRET=PLACEHOLDER_EMPTY
LINE_LIFF_ID=PLACEHOLDER_EMPTY
LINE_LOGIN_CHANNEL_ID=PLACEHOLDER_EMPTY
N8N_WEBHOOK_URL=PLACEHOLDER_EMPTY
N8N_ENCRYPTION_KEY=PLACEHOLDER_EMPTY
N8N_DB_PASSWORD=PLACEHOLDER_EMPTY
N8N_WORKFLOW_ID=PLACEHOLDER_EMPTY
```

Runtime staging values must be provided on the staging host. Values were not
printed or committed.

## Backend Health

Not executed against shared staging. Local compile passed.

## n8n Health

Not executed against shared staging. Local workflow JSON validation passed.
Docker compose staging config validation exited 0; Docker emitted local
`config.json` access warnings only.

## HTTPS/TLS Result

Not executed. Required public routes:

```text
GET  https://{STAGING_HOST}/health
GET  https://{STAGING_HOST}/register
GET  https://{STAGING_HOST}/api/liff/config
POST https://{STAGING_HOST}/webhook/line/events
```

## LINE Configuration

Waiting for external configuration:

```text
Messaging API Webhook URL: https://{STAGING_HOST}/webhook/line/events
LIFF Endpoint URL: https://{STAGING_HOST}/register
```

The staging LINE Login channel, LIFF app, Messaging API channel, and
allowlisted test account must be configured outside the repository.

## E2E Results

```text
LIFF E2E: NOT_EXECUTED
LINE webhook: NOT_EXECUTED
task creation: NOT_EXECUTED
crawler: NOT_EXECUTED
status Quick Reply: NOT_EXECUTED
canonical report: NOT_EXECUTED
tenant/task isolation: covered by Gate C1 local tests; not re-read from live staging in C2 local run
raw error leakage: local n8n/backend tests prepared; live staging not executed
Supabase readback: NOT_EXECUTED
rollback rehearsal: SQL prepared, NOT_EXECUTED
```

## Local Validation

```text
python -m compileall -q Backend: PASS
python -m pytest -q Backend/tests/api/test_staging_line_allowlist.py Backend/tests/test_n8n_zero_push_workflow.py Backend/tests/test_deploy_staging.py: PASS
python -m pytest -q: 343 passed, 1 warning (14.28s)
python -c json.load(...reputation-optimization-flow.json...): PASS
docker compose --env-file .env.staging.example -f infra/n8n/docker-compose.yml -f infra/n8n/docker-compose.staging.yml config --quiet: PASS with Docker config access warnings
Git Bash bash -n scripts/deploy-staging.sh scripts/rollback-staging.sh scripts/verify-staging.sh: PASS
git diff --check: PASS with LF/CRLF working-copy warnings
secret scan: PASS
skip/xfail scan on changed tests: PASS
database-change scan: only database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql
```

## Local Changes Prepared

```text
.env.staging.example
Backend/api/main.py
Backend/api/staging_allowlist.py
Backend/tests/api/test_staging_line_allowlist.py
Backend/tests/test_n8n_zero_push_workflow.py
database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql
docs/deployment/staging-deployment-runbook.md
docs/dev-spec/line-reputation-summary.md
docs/dev-spec/n8n-line-integration.md
docs/integration/customer-validation-gate-c2-report.md
infra/nginx/bi-rmp-staging-gateway.conf.example
infra/n8n/docker-compose.staging.yml
infra/n8n/workflows/reputation-optimization-flow.json
infra/systemd/bi-rmp-staging.service.example
scripts/deploy-staging.sh
scripts/rollback-staging.sh
scripts/verify-staging.sh
```

## Remaining Risks

- No SSH or remote staging runtime context was available in this local session.
- No runtime staging secrets were available, so deployment and E2E are blocked.
- LINE Developers Console changes must be performed manually against a staging
  channel, not production.
- Public HTTPS hostname or trusted tunnel must be configured before LINE can
  call the webhook.
- Supabase readback and rollback rehearsal require live staging credentials and
  must not print customer content or secret values.

## Suggested Commit Message

```text
feat: prepare customer validation gate c2 staging
```
