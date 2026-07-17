# Phase 6 Staging Migration Dry-Run Report

Date: 2026-07-17
Branch: integration/bi-rmp-v2-staging
Repository: cloud258654-alt/NCHU
Target project: BI-RMP-V2-STAGING
Allowed project ref: qlhykeeyjaoikczoambe

## Scope

This report records the Phase 6 attempt to prepare and dry-run a staging migration.

No Supabase link was executed.
No Supabase database connection was made.
No local database reset was executed.
No migration or database command was executed.
No crawler run was executed.
No push to `main` was performed.
No real `.env` file was copied or committed.
No secret value was read, printed, committed, or documented.

## Supabase Documentation Check

Supabase changelog and CLI documentation were checked before migration planning.

Relevant current notes:

- Supabase CLI `db push` supports `--dry-run`, but it requires a linked project or explicit database URL.
- Recent Supabase breaking changes include default Data API exposure behavior changes for newly created tables. Any future public-schema table migration should explicitly review grants and RLS.

## Preflight

- Starting branch: `integration/bi-rmp-v2-staging`.
- Starting `git status --short --branch`: clean.
- Phase 5: FAIL / blocker.
- `apps/dashboard-ml`: absent.
- `.env.staging`: absent.
- `supabase/`: absent.
- `supabase/.temp/project-ref`: absent.
- `docs/AGENT_HANDOFF.md`: absent in this checkout.
- `docs/architecture_review.md`: absent in this checkout.
- `docs/database_execution_runbook.md`: present and reviewed.

## Precondition Result

FAIL

Phase 6 requires Phase 5 PASS, integration branch, clean Git status, and an untracked `.env.staging`.

Only the branch and clean Git status preconditions were satisfied. Phase 5 is not PASS and `.env.staging` is absent.

## Supabase CLI And Link

Not executed.

Reason:

- Phase 6 preconditions are not met.
- Linking a remote project requires explicit human approval after showing the plan.
- No `supabase/` project directory exists in this checkout.

No `npx supabase link --project-ref qlhykeeyjaoikczoambe` command was run.

## Dangerous SQL Inventory

Command:

```powershell
git grep -n -E "DROP |TRUNCATE |DELETE FROM|ALTER TABLE|CREATE TABLE|CREATE VIEW|CREATE FUNCTION" -- database supabase
```

Result summary:

- `supabase` path is absent.
- `database/schema.sql` contains clean-rebuild destructive SQL, including `DROP TABLE IF EXISTS ... CASCADE`.
- `database/truncate_runtime_tables.sql` contains `TRUNCATE TABLE`.
- Existing migrations contain `CREATE TABLE`, `ALTER TABLE`, `DROP VIEW`, `DROP COLUMN`, and `DROP TABLE` statements.
- `database/migrations/20260713_refactor_crawl_relationships_latest_only.sql` is the current cutover migration referenced by the runbook, but the runbook states it rolls back until the known unresolved row condition is explicitly resolved.

Interpretation:

Existing SQL must not be blindly pushed to staging. `database/schema.sql` is not a remote migration candidate.

## Migration Creation

No migration was created.

Reason:

- Phase 6 preconditions are not met.
- No approved migration scope exists.
- No local `supabase/migrations` directory exists.
- `supabase migration new` was not run.

## RLS / View / Function Review

No new migration SQL was produced, so there were no new RLS policies, views, or functions to review.

Known future review requirements:

- Enable RLS for public tables exposed through Supabase APIs.
- Use explicit role grants when Data API exposure is required.
- Use `security_invoker=true` for exposed views or keep views unexposed.
- Avoid `SECURITY DEFINER`; if it is unavoidable, keep it outside public, restrict `search_path`, and revoke PUBLIC execute.
- For UPDATE policies, require both `USING` and `WITH CHECK`.

## Local Validation

Not executed.

The allowed command:

```powershell
npx supabase db reset --local
```

was not run because no migration was created and the preconditions are not met.

No `--linked` reset was run.

## Rollback

Created:

```text
docs/integration/staging-rollback.sql
```

This is a no-op placeholder because no forward migration was created.

## Remote Dry-Run

Not executed.

The intended command:

```powershell
npx supabase db push --dry-run
```

was not run because:

- The repository is not linked.
- The project ref could not be confirmed through `supabase/.temp/project-ref`.
- Phase 5 is not PASS.
- `.env.staging` is absent.

## Plans Created

Created:

```text
docs/integration/staging-migration-plan.md
docs/integration/staging-recheck/phase-6-migration-dry-run.md
docs/integration/staging-rollback.sql
```

## PASS / FAIL

FAIL

Completed:

- Supabase migration constraints were reviewed.
- Local SQL inventory was performed without executing SQL.
- Blocked staging migration plan was documented.
- No-op rollback placeholder was documented.
- No remote or destructive command was executed.

Blocking failures:

- Phase 5 is not PASS.
- `.env.staging` is absent.
- `supabase/` project directory is absent.
- No approved migration scope exists.
- No local reset or remote dry-run could be safely performed.

## Required Follow-Up

Resolve Phase 3 and Phase 5 blockers, create the local untracked `.env.staging`, restore or initialize the Supabase project directory, then rerun Phase 6 from the beginning.
