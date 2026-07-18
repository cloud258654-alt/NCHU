# MVP-A Release Manifest

Release name: `MVP-A STAGING Baseline`
Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`
Archived staging commit: `987882de6cea81dd68dc62fd0dd833117fc7a7f1`
Archived tree: `b3a2553af3bc0df855679c49e4a540d4d86b931b`
Remote: `origin`
Supabase project ref: `qlhykeeyjaoikczoambe`

## Release Scope

This manifest freezes the MVP-A staging baseline after Gates A2.1 through A7 and the Gate A8 rollback rehearsal.

This release includes:

- Staging database schema established for the MVP-A runtime tables.
- Public Data API closure with RLS enabled on the 13 runtime tables.
- Fictional MVP-A fixture data.
- Deterministic ML baseline writeback for the three fixture reviews.
- Core Dashboard API readback from BI-RMP-V2-STAGING.
- Dashboard frontend display of the fixture reviews and ML analysis state.
- Dashboard error-state validation.
- Rollback rehearsal proving fixture data can be precisely removed and restored by transaction rollback.

This release does not include:

- Production deployment.
- Live crawler execution.
- n8n workflow execution.
- LINE platform execution.
- Ollama or external AI execution.
- Schema migration after the MVP-A staging schema.
- ML contract changes after Gate 4.3.

## Frozen ML Contract

- `model_version`: `1.2.0`
- `analysis_type`: `review_risk_sentiment`
- `contract_version`: `gate-4.3`
- `risk_level`: `low`, `medium`, `high`
- `critical`: boolean
- `critical_signals`: string array
- `escalation_level`: `none`, `review`, `urgent`, `critical`
- `analysis_id`: `rules-v1-2-0-{sha256_32}`

## Staging Data Baseline

Fixture marker: `mvp-a-fixture-001`

| Object | Count / Value |
| --- | ---: |
| Fixture business | 1 |
| Fixture business ID | 6 |
| Dashboard-readable reviews | 3 |
| Review IDs | `12`, `13`, `14` |
| Analysis results | 3 |
| Analysis target IDs | `12`, `13`, `14` |
| Duplicate external IDs | 0 |
| Duplicate dedupe keys | 0 |
| Duplicate analysis targets | 0 |
| Orphan reviews | 0 |
| Orphan comments | 0 |
| Orphan analysis rows | 0 |
| Cross-business records | 0 |

Runtime table row counts at seal:

| Table | Count |
| --- | ---: |
| `alerts` | 0 |
| `analysis_results` | 3 |
| `business` | 1 |
| `client_messages_log` | 1 |
| `clients` | 1 |
| `comment_metric_snapshots` | 3 |
| `crawl_comments` | 3 |
| `crawl_jobs` | 3 |
| `crawl_logs` | 1 |
| `crawl_posts` | 3 |
| `post_metric_snapshots` | 3 |
| `reputation_score_snapshots` | 0 |
| `service_tasks` | 1 |

Security state:

- Runtime tables with RLS enabled: `13 / 13`
- `anon` / `authenticated` CRUD grants on runtime tables: `0`
- Dashboard frontend access path: Dashboard frontend to Core API only.
- Service role keys and database credentials are not stored in frontend files, committed files, reports, or command output.

## Gate Results

| Gate | Status | Evidence |
| --- | --- | --- |
| A2.1 RLS / Public Data API closure | PASS | `docs/integration/mvp-a-gate-a2-1-rls-public-data-api-report.md` |
| A3 fictional fixture data | PASS | `docs/integration/mvp-a-gate-a3-fictional-test-data-report.md` |
| A4 Core Dashboard API staging readback | PASS | Verified before A5/A6; Core API read-only path established |
| A5 ML analysis writeback | PASS | 3 analysis results for reviews `12`, `13`, `14` |
| A6 Dashboard staging readback | PASS | `docs/integration/mvp-a-gate-a6-dashboard-staging-readback-report.md` |
| A7 data consistency / error states | PASS | `docs/integration/mvp-a-gate-a7-staging-data-consistency-error-state-report.md` |
| A8 rollback rehearsal / seal | PASS | `docs/integration/mvp-a-gate-a8-rollback-rehearsal-seal-report.md` |

## A8 Verification Summary

Rollback rehearsal method:

- Existing rollback SQL: `database/testdata/mvp_a_fixture_rollback.sql`
- Execution mode: single database transaction
- Final transaction action: `ROLLBACK`
- Permanent database changes: none

Rollback rehearsal result:

- Expected deletion counts matched: PASS
- Fixture rows were zero inside the rehearsal transaction: PASS
- Row counts after transaction rollback matched pre-rehearsal counts: PASS
- Fixture state after transaction rollback matched pre-rehearsal state: PASS

Tests at seal:

- Dashboard tests: `26 passed, 1 warning`
- ML focused tests: `15 passed, 1 warning`
- Core regression: `298 passed, 1 warning`

## Operational Status

- Port `8000`: stopped
- Port `8010`: stopped
- Crawler: not executed
- n8n: not executed
- LINE: not executed
- Ollama / external AI: not executed
- Production deployment: not executed
- Main merge / main push: not executed during Gate A8

## Release Decision

MVP-A STAGING Baseline is sealed at archived staging commit `987882de6cea81dd68dc62fd0dd833117fc7a7f1`.
