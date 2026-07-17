# Phase 8 Final Staging E2E CI Rollback Report

Date: 2026-07-17
Branch: integration/bi-rmp-v2-staging
Repository: cloud258654-alt/NCHU
Target project: BI-RMP-V2-STAGING
Allowed project ref: qlhykeeyjaoikczoambe

## Scope

This report records the Phase 8 attempt to complete staging E2E, CI, deployment, rollback, and release candidate validation.

No Supabase link was executed.
No Supabase database connection was made.
No migration or database command was executed.
No staging deployment was performed.
No rollback exercise was performed.
No release candidate tag was created.
No crawler run was executed.
No push to `main` was performed.
No PR was created.
No real `.env` file was copied or committed.
No secret value was read, printed, committed, or documented.

## Supabase / Advisor Context

Supabase advisor documentation was checked. Security and Performance Advisors can detect issues such as missing indexes, disabled RLS in public schema, RLS policies referencing user metadata, security definer views/functions, and exposed objects.

Advisors were not executed because there is no confirmed linked staging project and Phase 7 did not pass.

## Preflight

- Starting branch: `integration/bi-rmp-v2-staging`.
- Starting `git status --short --branch`: clean.
- Phase 7: FAIL / blocker.
- `apps/dashboard-ml`: absent.
- `.env.staging`: absent.
- `supabase/`: absent.
- `supabase/.temp/project-ref`: absent.
- `docs/database_execution_runbook.md`: present and reviewed.

## Precondition Result

FAIL

Phase 8 requires:

- Phase 7 PASS
- clean Git status
- integration branch
- independent staging GCP/n8n/LINE test settings

Only the branch and clean Git status preconditions were satisfied.

## CI Review

Current `.github/workflows/ci.yml` includes:

- Backend pytest
- n8n Docker Compose config validation

Missing Phase 8 CI coverage:

- Dashboard frontend syntax/smoke
- `apps/dashboard-ml` Python compile
- secret scan
- migration validation
- explicit staging ref guard test job
- Python version matrix / strategy

No CI workflow changes were made in this phase because the required Dashboard application and Supabase migration workflow are still absent.

## Production Workflow Review

`.github/workflows/deploy-production.yml` triggers on:

```yaml
push:
  branches:
    - main
```

and manual `workflow_dispatch`.

Result:

- Integration branch does not itself match the production push trigger.
- No `git push origin main` was executed.
- No PR was created.
- No production tag was created.

## Local Tests

Full local test suite:

```powershell
$env:PYTHONPATH = "$PWD\Backend"
$env:DATABASE_URL = ""
.\.venv\Scripts\python.exe -m pytest -q -x
```

Result:

```text
293 passed, 1 warning in 2.94s
```

Warning:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

## Health Checks

Not executed against staging.

Required checks:

```text
GET /health
GET /api/health
GET /api/dashboard/summary
```

Reason:

- No staging deployment exists.
- `apps/dashboard-ml` is absent, so Dashboard ML `/api/health` cannot run.
- No staging database has been migrated.

## E2E

Not executed.

Required E2E path:

```text
LINE test message
-> n8n webhook
-> client recognition
-> crawler job
-> crawler
-> BI-RMP-V2-STAGING
-> ML analysis
-> Dashboard
-> LINE reply
```

Reason:

- Phase 7 is not PASS.
- No staging GCP/n8n/LINE settings were verified.
- No staging migration was applied.
- Dashboard ML app is absent.

## Data Consistency

Not verified.

No duplicate-job, orphan-review, cross-business, timezone, Dashboard/DB/LINE consistency, or cleanup verification was performed against staging.

## Rollback Exercise

Not executed.

Created:

```text
docs/integration/rollback-runbook.md
```

The rollback runbook is a draft because there is no applied staging migration or candidate deployment to roll back.

## Staging Deployment Documentation

Created:

```text
docs/integration/staging-deployment.md
```

The document records the intended staging acceptance sequence and current blockers.

## Release Candidate

No `v2.0.0-rc.1` tag was created.

Reason:

- Phase 8 did not pass.
- Creating a release candidate would falsely imply staging acceptance.

## PASS / FAIL

FAIL

Completed:

- Local pytest passed.
- CI coverage gaps were identified.
- Production workflow trigger was reviewed.
- Staging deployment runbook was documented.
- Rollback runbook was documented.
- No production or old Supabase change was made.

Blocking failures:

- Phase 7 is not PASS.
- `apps/dashboard-ml` is absent.
- `.env.staging` is absent.
- `supabase/` is absent.
- `supabase/.temp/project-ref` is absent.
- No staging migration has been applied.
- No staging health, E2E, advisors, rollback, or RC tag can be accepted.

## Required Follow-Up

Resolve Phase 3 through Phase 7 blockers, then rerun Phase 8 after staging services, database, n8n, LINE, ML, and Dashboard are independently available.
