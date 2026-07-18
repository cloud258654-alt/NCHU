# MVP-A Gate A7 Staging Data Consistency And Error State Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`
Supabase project ref: `qlhykeeyjaoikczoambe`
Baseline commit: `6d6afe7 fix: complete gate a6 dashboard staging readback`

## Scope

Gate A7 verified the BI-RMP-V2-STAGING fixture data, Dashboard readback consistency, and Dashboard error states. This gate was read-only for the staging database.

No crawler, n8n, LINE, Ollama, migration, deployment, schema change, RLS change, main merge, or main push was executed.

## Preflight

PASS.

- Branch: `integration/bi-rmp-v2-staging-v2`
- Branch sync before A7: `0 0` against `origin/integration/bi-rmp-v2-staging-v2`
- Worktree before A7: clean
- `.env.staging`: present and gitignored
- `SUPABASE_PROJECT_REF`: `qlhykeeyjaoikczoambe`
- `ALLOW_DATABASE_WRITES=false`

Project handoff note:

- `docs/database_execution_runbook.md` exists and was reviewed.
- `docs/AGENT_HANDOFF.md` was not present.
- `docs/architecture_review.md` was not present.

## Staging Data Consistency

PASS.

| Check | Result |
| --- | --- |
| Fixture business count | 1 |
| Fixture business ID | 6 |
| Fixture business name | `MVP 測試咖啡館` |
| Dashboard-readable review count | 3 |
| Dashboard-readable review IDs | `12`, `13`, `14` |
| Analysis result count for fixture reviews | 3 |
| Analysis target IDs | `12`, `13`, `14` |
| Duplicate source/external IDs | 0 |
| Duplicate dedupe keys | 0 |
| Duplicate analysis target groups | 0 |
| Orphan reviews | 0 |
| Orphan comments | 0 |
| Orphan analysis rows | 0 |
| Cross-business fixture records | 0 |
| ML contract rows valid | PASS |

Review 14 latest analysis:

- `critical=true`
- `critical_signals` non-empty
- `escalation_level=critical`
- `human_review_required=true`
- `risk_level=high`
- `sentiment=neutral`

Security consistency:

- Runtime tables with RLS enabled: `13 / 13`
- `anon` / `authenticated` CRUD grants on runtime tables: `0`

## Row Count Stability

PASS. Counts before and after browser validation were identical.

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

## Normal Dashboard State

PASS.

Playwright validated the real Dashboard on port `8010` against the real Core API on port `8000`; no fake Core API was used.

| Viewport | Business visible | Review rows | Reviews metric | Analysis metric | Risk metric | Review 14 warning | Console errors | Page errors | Direct Supabase requests |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |
| Desktop 1440x900 | PASS | 3 | 3 | 3 | `high` | PASS | 0 | 0 | 0 |
| Mobile 390x844 | PASS | 3 | 3 | 3 | `high` | PASS | 0 | 0 | 0 |

Network guard tokens checked:

- `supabase.co`
- `/rest/v1`
- `DATABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `postgres://`
- `postgresql://`
- `qlhykeeyjaoikczoambe`

## Error States

PASS.

Real Core API missing review:

- Request: `GET /api/dashboard/reviews/999999`
- HTTP status: `404`
- Response body: `{"detail":"Dashboard review was not found"}`
- Secret leak check: PASS

Dashboard detail 404 state:

- Error UI displayed: PASS
- Message contained: `selected review no longer exists`
- Page exceptions: 0
- Direct Supabase requests: 0
- Browser console contained one expected Chromium network entry for the handled 404 response.

Dashboard Core unavailable state:

| Viewport | Error UI displayed | Error text non-empty | Page errors | Direct Supabase requests | Request failures |
| --- | --- | --- | ---: | ---: | ---: |
| Desktop 1440x900 | PASS | PASS | 0 | 0 | 3 |
| Mobile 390x844 | PASS | PASS | 0 | 0 | 3 |

Browser console contained expected failed-fetch network entries while Core was intentionally stopped. The frontend displayed the controlled error state and did not expose database credentials or call Supabase directly.

## Tests

PASS.

- Dashboard tests: `26 passed, 1 warning`
- ML focused tests: `15 passed, 1 warning`
- Core regression: `298 passed, 1 warning`

## Shutdown

PASS.

- Port `8000` stopped.
- Port `8010` stopped.

## Conclusion

Gate A7 passed. Staging data remained consistent, row counts were unchanged, Dashboard normal readback matched the fixture and analysis rows, and expected error states were handled without direct Supabase access or secret exposure.
