# Phase 7 Staging Data Auth ML Report

Date: 2026-07-17
Branch: integration/bi-rmp-v2-staging
Repository: cloud258654-alt/NCHU
Target project: BI-RMP-V2-STAGING
Allowed project ref: qlhykeeyjaoikczoambe

## Scope

This report records the Phase 7 attempt to validate staging data, ML idempotency, Auth, business scope, RLS, and advisors.

No Supabase link was executed.
No Supabase database connection was made.
No migration or database command was executed.
No staging data was inserted.
No staging data was deleted.
No ML model was executed.
No crawler run was executed.
No push to `main` was performed.
No real `.env` file was copied or committed.
No secret value was read, printed, committed, or documented.

## Supabase Documentation Check

Supabase RLS and API security documentation were checked before assessment.

Relevant notes for future implementation:

- Grants determine whether `anon`, `authenticated`, or `service_role` can reach an object through the Data API; RLS then controls rows.
- `auth.uid()` returns null for unauthenticated requests, so policies should explicitly handle authenticated scope.
- `raw_user_meta_data` / `user_metadata` is user-editable and must not be used for authorization decisions.
- Public Data API exposure should be paired with explicit grants and RLS.
- Views should use `security_invoker=true` when exposed, or remain unexposed.
- Functions are not protected by RLS; EXECUTE grants and `SECURITY DEFINER` usage require explicit review.

## Preflight

- Starting branch: `integration/bi-rmp-v2-staging`.
- Starting `git status --short --branch`: clean.
- Phase 6: FAIL / blocker.
- User approval for `npx supabase db push`: not present.
- `docs/integration/staging-rollback.sql`: present, but it is a no-op placeholder because Phase 6 created no migration.
- `supabase/.temp/project-ref`: absent.
- `.env.staging`: absent.
- `supabase/`: absent.
- `docs/AGENT_HANDOFF.md`: absent in this checkout.
- `docs/architecture_review.md`: absent in this checkout.
- `docs/database_execution_runbook.md`: present and reviewed.

## Precondition Result

FAIL

Phase 7 requires:

- Phase 6 PASS
- explicit user approval
- rollback SQL
- `supabase/.temp/project-ref = qlhykeeyjaoikczoambe`

Only a rollback placeholder exists. Phase 6 did not pass, approval was not provided, and the linked project ref is absent.

## Migration Application

Not executed.

The intended command:

```powershell
npx supabase db push
```

was not run because Phase 7 preconditions are not met.

## Schema / RLS Static Review

Static search found no local SQL definitions for:

- `ENABLE ROW LEVEL SECURITY`
- `CREATE POLICY`
- `SECURITY DEFINER`
- `SECURITY INVOKER`
- `auth.uid`
- `auth.jwt`
- `WITH CHECK`

Interpretation:

- No staging RLS policy can be verified from the current local SQL.
- No Auth/business-scope RLS enforcement is represented in local migrations.
- This is not a remote finding because no staging database was queried.

## Test Data

The required fictitious staging data was not inserted:

```text
client: staging-test-client
business: BI-RMP V2 test store
review: staging-review-001
```

Reason: no migration was applied and no staging database connection was made.

## ML Writeback

Not executed.

The required idempotency check by:

- `review_id`
- `model_version`
- `analysis_type`

could not be performed. `analysis_results` exists in the local schema, but no staging row was written or verified.

## Auth / Business Scope

Not executed against staging.

Created:

```text
docs/integration/authorization-matrix.md
```

The file records the intended 401/403/200 matrix, but it is not a staging-verified acceptance result.

## Advisors

Not executed.

Reason:

- No linked Supabase project is confirmed.
- Phase 6 did not pass.
- No migration was applied.

No claim is made about Security Advisor or Performance Advisor status.

## Tests

Full local test suite:

```powershell
$env:PYTHONPATH = "$PWD\Backend"
$env:DATABASE_URL = ""
.\.venv\Scripts\python.exe -m pytest -q -x
```

Result:

```text
293 passed, 1 warning in 2.72s
```

Warning:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

## PASS / FAIL

FAIL

Completed:

- Supabase Auth/RLS security constraints were reviewed.
- Local SQL was statically checked for RLS/policy/security-function definitions.
- Full local pytest passed.
- Authorization matrix draft was documented.
- No remote or destructive command was executed.

Blocking failures:

- Phase 6 is not PASS.
- No explicit approval to apply migration was provided.
- `supabase/.temp/project-ref` is absent.
- `.env.staging` is absent.
- `supabase/` project directory is absent.
- No staging migration has been applied.
- RLS, business isolation, ML idempotency, advisors, and cleanup cannot be verified without a staging database workflow.

## Required Follow-Up

Resolve Phase 3, Phase 5, and Phase 6 blockers. After Phase 6 passes and the linked project ref is confirmed as `qlhykeeyjaoikczoambe`, rerun Phase 7 with explicit approval before applying migration or inserting staging test data.

## Gate 4 Local ML AI Baseline Update

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

Gate 4 adds a local offline analysis baseline under `apps/dashboard-ml`.

This update does not change the Phase 7 staging result above. No Supabase connection was made, no staging data was inserted, and no ML writeback/idempotency validation against `analysis_results` was performed.

Implemented locally:

- `GET /api/ml/health`
- `GET /api/ml/info`
- `POST /api/ml/analyze-review`
- `POST /api/ml/analyze-batch`
- `POST /api/ai/suggest-response`

Scope limits:

- Not the original recovered model.
- Not production-grade trained ML.
- No trained-model accuracy is claimed.
- No fake pickle/joblib artifacts were created.
- Ollama and other LLM integrations are deferred.
- Gate 4.2 adds canonical analysis contract values, a 0-100 risk scale, deterministic bilingual response templates, and Traditional Chinese phrase support, still as deterministic rules only.

Canonical Gate 4.2 values:

- `model_name`: `bi-rmp-rules-baseline`
- `model_version`: `1.1.0`
- `analysis_method`: `rules_baseline`

Validation:

```text
Dashboard tests including ML baseline: 23 passed, 1 warning
Core regression: 298 passed, 1 warning
```
