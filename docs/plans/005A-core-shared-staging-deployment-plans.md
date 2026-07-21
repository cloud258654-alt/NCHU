# 005A — Core Shared Staging Deployment

## Repository correction

The active Git repository root is the `NCHU` directory. The parent directory
is not a Git repository and must not be used as the deployment source.

## Scope

`STAGING_DEPLOY_PROFILE=core` deploys only the isolated FastAPI backend,
Supabase runtime connection, staging n8n/PostgreSQL, gateway readiness,
backup/redeploy/rollback, and production-isolation guards.

It does not require or enable LINE/LIFF configuration, LINE workflow import,
LINE webhook routing, LIFF registration, or customer E2E.

## Dedicated host topology

`STAGING_HOST_MODE=shared` remains the default for the historical shared-host
workflow. `STAGING_HOST_MODE=dedicated` supports a Staging-only VM with a
configurable user, home directory, application directory, and backup root.
Dedicated mode must find no Production directory, service, containers, or
ports. Core bootstrap does not require a public hostname and binds the gateway
only to `127.0.0.1:8180`.

## Core environment contract

Core requires the database, backend, and n8n keys only. It must use:

```text
N8N_HOST=localhost
N8N_WEBHOOK_URL=http://127.0.0.1:5679/
```

The following keys are full-profile-only and must not block core deployment:

```text
BI_RMP_LINE_ALLOWED_USER_IDS
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
LINE_LIFF_ID
LINE_LOGIN_CHANNEL_ID
N8N_WORKFLOW_ID
```

## Core verification

Core verification requires backend health, a staging Supabase connection, n8n
PostgreSQL/container/readiness, and production-isolation checks. It expects
`/api/liff/config` to return HTTP 503 and reports LINE, LIFF, customer E2E,
and public HTTPS as deferred.

## Rollback

Run `STAGING_DEPLOY_PROFILE=core scripts/rollback-staging.sh <sha>`.
Rollback restores only staging code/backend/n8n readiness. It does not import,
publish, or modify LINE workflows; it does not run database migrations or
touch production.

## Status

```text
004 LINE/LIFF = DEFERRED_BY_USER
005A Core Shared Staging = READY_FOR_CORE_STAGING_DEPLOYMENT
005B LINE Integrated Staging = BLOCKED_BY_EXTERNAL_CONFIGURATION
006 LINE E2E = BLOCKED_BY_EXTERNAL_CONFIGURATION
Gate C2 final = NOT PASSED
```
