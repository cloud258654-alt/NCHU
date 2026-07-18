# MVP-A Gate A2.1 RLS Public Data API Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

## Scope

Gate A2.1 closes public Data API access for the BI-RMP-V2-STAGING runtime
tables by enabling RLS and removing direct `anon` / `authenticated` DML grants.

No crawler, staging test-data insert, n8n, LINE, Ollama, external AI,
deployment, `main` merge, or `main` push was executed.

## Target Verification

- Supabase project: `BI-RMP-V2-STAGING`
- Project ref: `qlhykeeyjaoikczoambe`
- Project status: `ACTIVE_HEALTHY`
- PostgreSQL: `17.6.1.147`, engine `17`, region `ap-northeast-2`
- Local `supabase/.temp/project-ref`: absent
- Remote target was verified through the Supabase connector before DDL.

Supabase documentation/changelog notes checked:

- RLS should be enabled on tables in exposed schemas such as `public`.
- With RLS enabled and no policies, Data API access using publishable/anon
  credentials is blocked.
- Supabase's 2026 Data API change makes explicit grants important for newly
  created public tables.

## Applied Migration

Remote migration history after execution:

```text
20260718065943 mvp_a2_initial_staging_schema
20260718071100 mvp_a2_1_enable_rls_close_public_data_api
```

Local replay SQL was added at:

```text
database/migrations/20260718_mvp_a2_1_enable_rls_close_public_data_api.sql
```

The migration:

- Enabled RLS on all 13 runtime tables.
- Revoked `SELECT`, `INSERT`, `UPDATE`, and `DELETE` from `anon`.
- Revoked `SELECT`, `INSERT`, `UPDATE`, and `DELETE` from `authenticated`.
- Created no `anon` policies.
- Created no `authenticated` policies.
- Created no `using (true)` or `with check (true)` policies.

## Runtime Tables

RLS is enabled on:

- `clients`
- `business`
- `service_tasks`
- `crawl_jobs`
- `crawl_posts`
- `crawl_comments`
- `post_metric_snapshots`
- `comment_metric_snapshots`
- `analysis_results`
- `reputation_score_snapshots`
- `alerts`
- `client_messages_log`
- `crawl_logs`

Verification queries showed:

```text
RLS enabled tables: 13 / 13
Policies on runtime tables: 0
anon/authenticated SELECT/INSERT/UPDATE/DELETE grants: 0
Checked runtime row counts: 0
```

## Advisors

Security Advisor:

- `rls_disabled_in_public`: cleared.
- `rls_enabled_no_policy`: INFO on all 13 runtime tables.

The remaining INFO result is expected for this gate because the approved
security decision is to keep the Public Data API closed and create no
`anon` / `authenticated` policies.

Performance Advisor:

- INFO findings remain for unused indexes on the empty staging database.
- INFO findings remain for unindexed foreign keys:
  - `alerts.analysis_result_id`
  - `client_messages_log.client_id`

These are not blockers for Gate A2.1 because this gate is limited to closing
Public Data API access and no runtime data exists yet.

## Result

PASS for Gate A2.1 public Data API closure.

Residual risks:

- Server-side services must use direct PostgreSQL credentials such as
  `DATABASE_URL`; no frontend secret exposure is allowed.
- Future Dashboard browser access must continue to go through Core API.
- Any future Data API access requires explicit policies and grants reviewed in
  a separate gate.
