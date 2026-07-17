# BI-RMP-V2 Rollback Runbook

Date: 2026-07-17
Status: Draft / blocked

## Scope

This runbook records the required rollback exercise for staging. It has not been executed.

## Current Blockers

- Phase 7 is not PASS.
- No staging deployment was performed.
- No release candidate tag was created.
- No staging migration was applied.
- `docs/integration/staging-rollback.sql` is currently a no-op placeholder because Phase 6 created no forward migration.

## Rollback Exercise Steps

The Phase 8 rollback exercise must validate the following in staging only:

1. Return Git checkout to the previous accepted tag.
2. Restore systemd service configuration.
3. Restore n8n workflow backup.
4. Restore Nginx route configuration.
5. Execute reviewed staging rollback SQL.
6. Run health checks until Core and Dashboard endpoints recover.

## Required Evidence

Record the following when the exercise is actually performed:

- Previous tag and candidate tag.
- Services stopped and restarted.
- n8n workflow backup identifier.
- Nginx config path and validation result.
- Rollback SQL file path and reviewed statements.
- Health check responses.
- Any data cleanup performed.

## Safety Rules

- Do not execute rollback SQL against production.
- Confirm `supabase/.temp/project-ref` equals `qlhykeeyjaoikczoambe` before any staging database action.
- Do not use `supabase db reset --linked`.
- Do not print or commit secrets.
- Stop if target project ref cannot be verified.

## Current Result

Rollback exercise not performed. The runbook is a draft acceptance checklist until Phase 6 and Phase 7 pass.
