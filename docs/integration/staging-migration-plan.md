# BI-RMP-V2 Staging Migration Plan

Date: 2026-07-17
Branch: integration/bi-rmp-v2-staging
Target project: BI-RMP-V2-STAGING
Allowed project ref: qlhykeeyjaoikczoambe

## Status

Blocked. No staging migration was created and no remote dry-run was executed.

## Blocking Conditions

- Phase 5 is not PASS. The latest Phase 5 recheck is `FAIL / blocker` because `apps/dashboard-ml` is absent.
- `.env.staging` is absent. Phase 6 requires the user to create an untracked `.env.staging` before migration work.
- `supabase/` is absent. The repository has no local Supabase project directory to hold `supabase/migrations`.
- The repository is not linked to a Supabase project. `supabase/.temp/project-ref` is absent.

## Safety Decisions

- `supabase link` was not executed.
- `supabase db reset --local` was not executed.
- `supabase db push --dry-run` was not executed.
- No migration file was created.
- No remote Supabase connection was made.
- No destructive SQL was executed.
- No real `.env` content or secret was read, printed, committed, or documented.

## SQL Inventory

`database/schema.sql` is a clean rebuild script and must not be pushed to staging directly.

Existing SQL includes destructive or schema-changing statements:

- `database/schema.sql`: contains many `DROP TABLE IF EXISTS ... CASCADE`, `DROP VIEW IF EXISTS ... CASCADE`, and `CREATE TABLE` statements.
- `database/truncate_runtime_tables.sql`: contains `TRUNCATE TABLE`.
- `database/migrations/20260710_crawl_observation_schema.sql`: contains `DROP INDEX`, `ALTER TABLE ... DROP COLUMN`, and observation table creation.
- `database/migrations/20260713_refactor_crawl_relationships_latest_only.sql`: contains `ALTER TABLE`, `DROP VIEW`, `DROP COLUMN`, and `DROP TABLE` statements. It is explicitly guarded by preflight checks and must only run after the unresolved row condition is addressed.

## Candidate Migration Scope

No new candidate migration was selected in this phase.

Before creating a staging migration, decide whether the target is:

- a clean rebuild using `database/schema.sql` after an explicit backup and human approval, or
- the cutover migration `database/migrations/20260713_refactor_crawl_relationships_latest_only.sql` after resolving the known `crawl_posts.id = 393` blocker, or
- a new incremental migration containing only reviewed new objects.

## Required Next Steps

1. Resolve Phase 3 and Phase 5 blockers by restoring `apps/dashboard-ml` from an approved source.
2. Create an untracked `.env.staging` locally with the staging target and real secrets. Do not commit it.
3. Initialize or restore a proper local Supabase project directory if migration CLI workflow is required.
4. Confirm `supabase/.temp/project-ref`, if present, is exactly `qlhykeeyjaoikczoambe`.
5. Use `npx supabase --version`, `npx supabase link --help`, and `npx supabase db push --help` to confirm CLI behavior before linking.
6. Wait for explicit human approval before running `npx supabase link --project-ref qlhykeeyjaoikczoambe`.
7. Use `supabase migration new` to create a formal migration file only after the migration scope is approved.
8. Run local validation only with `supabase db reset --local`.
9. Run remote dry-run only after confirming the linked ref is `qlhykeeyjaoikczoambe`.

## Current Result

FAIL / blocked. Migration preparation cannot proceed safely until the preconditions are satisfied.
