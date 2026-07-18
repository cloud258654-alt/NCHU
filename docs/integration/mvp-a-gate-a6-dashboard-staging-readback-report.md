# MVP-A Gate A6 Dashboard Staging Readback Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`
Supabase project ref: `qlhykeeyjaoikczoambe`

## Scope

Gate A6 verified the Dashboard frontend against the real Core API and the BI-RMP-V2-STAGING database fixture. No crawler, n8n, LINE, Ollama, migration, deployment, main merge, or main push was executed during this gate.

## A5 Commit And Push Status

PASS.

- Pre-A6 staging branch was aligned with `origin/integration/bi-rmp-v2-staging-v2`.
- Pre-A6 worktree was clean.
- Gate A5 was a database writeback verification gate and introduced no tracked program or documentation delta before Gate A6.
- Baseline commit before Gate A6 changes: `b72d1a4 testdata: add mvp a3 fictional fixture`.

## Read-Only Runtime Configuration

PASS.

- `.env.staging` existed and was gitignored.
- `SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe`.
- `ALLOW_DATABASE_WRITES=false`.
- Core API was started on `127.0.0.1:8000`.
- Dashboard was started on `127.0.0.1:8010`.
- Dashboard config exposed only the Core API URL and `/api/dashboard` prefix. No database credential was exposed.

## Real Staging Data Readback

PASS.

- Fixture business found: PASS.
- Fixture business ID: `6`.
- Fixture business name: `MVP 測試咖啡館`.
- Dashboard-readable review IDs: `12`, `13`, `14`.
- Review count displayed: `3`.
- Analysis count displayed: `3`.
- Review 14 warning displayed: PASS.

Review 14 latest analysis:

- `critical=true`
- `critical_signals` non-empty
- `escalation_level=critical`
- `human_review_required=true`
- `risk_level=high`
- `sentiment=neutral`

## Browser Validation

PASS.

Playwright used the real Dashboard on port `8010` and real Core API on port `8000`; no fake Core API was used.

| Viewport | Business visible | Review rows | Analysis count | Review 14 warning | Console errors | Page errors | Direct Supabase requests |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| Desktop 1440x900 | PASS | 3 | 3 | PASS | 0 | 0 | 0 |
| Mobile 390x844 | PASS | 3 | 3 | PASS | 0 | 0 | 0 |

Network guard tokens checked:

- `supabase.co`
- `/rest/v1`
- `DATABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `postgres://`
- `postgresql://`

## Database Row Count Stability

PASS. Counts before and after UI verification were identical.

| Table | Before | After |
| --- | ---: | ---: |
| `alerts` | 0 | 0 |
| `analysis_results` | 3 | 3 |
| `business` | 1 | 1 |
| `client_messages_log` | 1 | 1 |
| `clients` | 1 | 1 |
| `comment_metric_snapshots` | 3 | 3 |
| `crawl_comments` | 3 | 3 |
| `crawl_jobs` | 3 | 3 |
| `crawl_logs` | 1 | 1 |
| `crawl_posts` | 3 | 3 |
| `post_metric_snapshots` | 3 | 3 |
| `reputation_score_snapshots` | 0 | 0 |
| `service_tasks` | 1 | 1 |

## Tests

PASS.

- Dashboard tests: `26 passed, 1 warning`
- ML focused tests: `15 passed, 1 warning`
- Core regression: `298 passed, 1 warning`

## A6 Minimal Fixes

The following P1-scoped fixes were required for the gate:

- Core Dashboard API now exposes existing critical escalation fields from `analysis_results.score_explanation`.
- Core API now allows local Dashboard dev origins on port `8010` for GET/OPTIONS browser reads.
- Dashboard frontend now displays high risk and critical/manual review warnings from the existing ML result contract.

No ML contract, model version, database schema, RLS policy, or analysis ID format was changed.

## Shutdown

PASS.

- Port `8000` stopped.
- Port `8010` stopped.
