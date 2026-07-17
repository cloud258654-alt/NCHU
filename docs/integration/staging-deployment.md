# BI-RMP-V2 Staging Deployment Runbook

Date: 2026-07-17
Status: Draft / blocked

## Scope

This runbook defines the intended staging deployment checks for BI-RMP-V2. It is not a completed deployment record.

## Current Blockers

- Phase 7 is not PASS.
- `apps/dashboard-ml` is absent.
- `.env.staging` is absent.
- `supabase/` is absent.
- `supabase/.temp/project-ref` is absent.
- No staging migration has been applied.
- No staging GCP, n8n, LINE, ML, or Dashboard E2E validation has been completed.

## Required Target

- Supabase project: `BI-RMP-V2-STAGING`
- Supabase project ref: `qlhykeeyjaoikczoambe`
- Core API: `http://127.0.0.1:8000`
- Dashboard ML API: `http://127.0.0.1:8010`
- n8n: `5678`
- SearXNG: `8080`
- Ollama: `11434`

## Required Preconditions

1. Phase 3 PASS: `apps/dashboard-ml` restored from an approved source.
2. Phase 5 PASS: Dashboard frontend uses Core Dashboard read API and browser network has no direct Supabase REST calls.
3. Phase 6 PASS: migration dry-run completed against `qlhykeeyjaoikczoambe`.
4. Phase 7 PASS: migration applied to staging, RLS/business scope/ML/advisors verified.
5. `supabase/.temp/project-ref` equals `qlhykeeyjaoikczoambe`.
6. `.env.staging` exists locally and remains untracked.
7. Production workflow protection reviewed.

## Health Checks

Expected after staging services are running:

```text
GET /health
GET /api/health
GET /api/dashboard/summary
```

All must return HTTP 200 before E2E validation.

## E2E Flow

Expected staging-only flow:

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

Acceptance notes:

- PTT `success_no_results` can count as flow success with no data.
- Google Maps must use bounded timeout and max-results.
- Threads missing staging session is a known external limitation and should not block Core E2E if documented.

## Production Protection

Do not push `main` during staging validation. `.github/workflows/deploy-production.yml` deploys on push to `main` and manual `workflow_dispatch`.

Integration branch work must not create an auto-merge PR or production tag.

## Release Candidate

Only create `v2.0.0-rc.1` after Phase 8 PASS.

Do not create `v2.0.0` during staging validation.

## Current Result

Blocked. This runbook is ready for future execution, but no staging deployment acceptance has been completed.
