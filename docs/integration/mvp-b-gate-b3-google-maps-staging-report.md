# MVP-B Gate B3 Google Maps Staging Report

Date: 2026-07-19
Branch: `feature/mvp-b-b3-google-maps-staging`
Baseline commit: `b97cf8c16d9d1a212a068504f705f7304936e060`
Supabase project: `BI-RMP-V2-STAGING`
Supabase project ref: `qlhykeeyjaoikczoambe`

## Scope

Gate B3 verified only the existing Google Maps single-platform path.

No B4 work was started. PTT, Threads, n8n, LINE, Ollama, post-crawl AI execution, migrations, schema changes, RLS changes, grants, policies, production, old Supabase projects, `main` merge, and `main` push were not executed.

## Preflight

PASS with one branch-ref warning.

- Local branch: `feature/mvp-b-b3-google-maps-staging`
- Local HEAD before B3 changes: `b97cf8c16d9d1a212a068504f705f7304936e060`
- `origin/feature/mvp-b-b3-google-maps-staging`: not present at preflight
- Worktree before B3: clean
- `.env.staging`: present and gitignored
- `APP_ENV=staging`
- `SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe`
- `SUPABASE_URL`: present and matched `qlhykeeyjaoikczoambe`
- `DATABASE_URL`: present and matched `qlhykeeyjaoikczoambe`
- `ALLOW_DATABASE_WRITES=false` in `.env.staging`; B3 overrode it to `true` only for staging ingestion processes
- `ALLOW_PRODUCTION_DB=false`

Project handoff note:

- `docs/database_execution_runbook.md` exists and was reviewed.
- `docs/AGENT_HANDOFF.md` was not present.
- `docs/architecture_review.md` was not present.

Supabase target verification:

- Connector `get_project` returned `BI-RMP-V2-STAGING`.
- Project ref: `qlhykeeyjaoikczoambe`
- Status: `ACTIVE_HEALTHY`
- Region: `ap-northeast-2`
- PostgreSQL: `17.6.1.147`

## Focused Tests

PASS.

```text
.\.venv\Scripts\python.exe -m pytest Backend\tests\adapters\test_google_maps_crawler.py Backend\tests\adapters\test_google_maps_delta.py Backend\tests\core\test_source_discovery.py Backend\tests\test_runner_google_maps_deadline.py
```

Result:

- `49 passed`
- Warnings: `0`

## Dry-Run

PASS.

Command shape:

```powershell
$env:APP_ENV = 'staging'
$env:SUPABASE_PROJECT_REF = 'qlhykeeyjaoikczoambe'
$env:ALLOW_DATABASE_WRITES = 'false'
$env:ALLOW_PRODUCTION_DB = 'false'
$env:GOOGLE_MAPS_DISCOVERY_ENGINE = 'duckduckgo'
$env:GOOGLE_MAPS_DISCOVERY_MAX_RESULTS = '5'
.\.venv\Scripts\python.exe Backend\runner.py `
  --platform google_maps `
  --business-name "Starbucks Taipei 101" `
  --keyword coffee `
  --max-results 1 `
  --max-minutes 3 `
  --google-maps-max-minutes 3 `
  --google-maps-max-reviews 10 `
  --google-maps-max-scroll 2 `
  --max-scroll 2 `
  --browser-concurrency 1 `
  --persistence-grace-seconds 5 `
  --dry-run `
  --skip-ai `
  --json-summary
```

Result:

| Check | Result |
| --- | --- |
| Selected platform | `google_maps` |
| Source discovery engine attempted | `duckduckgo` |
| Search query 1 | `Starbucks Taipei 101 site:google.com/maps` |
| Search query 2 | `Starbucks Taipei 101 Google Maps` |
| Search candidates found | `0` |
| Fallback source URL | `https://www.google.com/maps/search/Starbucks+Taipei+101` |
| Google Maps place URLs discovered by crawler | `2` |
| Places with reviews | `2` |
| Reviews scanned | `10` |
| Delta reviews in dry-run | `10` |
| Status | `partial_success` |
| Partial reason | existing index unavailable because DB writes were disabled |
| Canonical posts written | `0` |
| Canonical comments written | `0` |
| DB rows written | `0` |
| Service task ID | `null` |
| Crawl job ID | `null` |

Dry-run row counts before and after were identical.

## First Staging Ingestion

PASS.

The same single-platform command was run without `--dry-run` and with `ALLOW_DATABASE_WRITES=true` only in the process environment. `--skip-ai` remained set.

Result:

| Check | Result |
| --- | --- |
| Service task ID | `8` |
| Crawl job ID | `16` |
| Status | `success` |
| Outcome | `success_with_data` |
| Source discovery selected source | `generated_fallback` |
| Source URL | `https://www.google.com/maps/search/Starbucks+Taipei+101` |
| Google Maps place URLs discovered | `2` |
| Places scanned | `2` |
| Reviews scanned | `10` |
| Baseline reviews | `10` |
| Delta reviews | `10` |
| Existing records loaded | `0` |
| Canonical posts written | `2` |
| Canonical comments written | `10` |
| Post metric snapshots written | `2` |
| Comment metric snapshots written | `10` |
| Failed persistence stages | `[]` |

Row count delta from B3 baseline:

| Table | Before | After First Ingestion | Delta |
| --- | ---: | ---: | ---: |
| `alerts` | 0 | 0 | 0 |
| `analysis_results` | 3 | 3 | 0 |
| `business` | 2 | 3 | +1 |
| `client_messages_log` | 1 | 1 | 0 |
| `clients` | 2 | 2 | 0 |
| `comment_metric_snapshots` | 3 | 13 | +10 |
| `crawl_comments` | 3 | 13 | +10 |
| `crawl_jobs` | 4 | 5 | +1 |
| `crawl_logs` | 26 | 54 | +28 |
| `crawl_posts` | 4 | 6 | +2 |
| `post_metric_snapshots` | 4 | 6 | +2 |
| `reputation_score_snapshots` | 0 | 0 | 0 |
| `service_tasks` | 2 | 3 | +1 |

Readback:

| Field | Value |
| --- | --- |
| `business.id` | `8` |
| `business.name` | `Starbucks Taipei 101` |
| `service_tasks.id` | `8` |
| `service_tasks.status` | `completed` |
| `crawl_jobs.id` | `16` |
| `crawl_jobs.platform` | `google_maps` |
| `crawl_jobs.status` | `success` |
| `crawl_jobs.total_posts` | `2` |
| `crawl_jobs.total_comments` | `10` |
| `crawl_posts.id` | `16`, `17` |
| `crawl_posts.extra_data.platform` | `google_maps` |
| `crawl_comments` for B3 posts | `10` |
| `post_metric_snapshots` for B3 posts | `2` |
| `comment_metric_snapshots` for B3 comments | `10` |

Data normalization was verified through canonical storage:

- Places were persisted in `crawl_posts`.
- Reviews were persisted in `crawl_comments`.
- Review identity/dedupe fields were generated by the Google Maps delta/normalization path.
- Post and comment metrics were persisted in snapshot tables.
- No Google-Maps-specific tables were created.

## Idempotency

PASS.

The same command was run a second time.

Result:

| Check | Result |
| --- | --- |
| Service task ID | `9` |
| Crawl job ID | `17` |
| Existing records loaded | `10` |
| Reviews scanned | `10` |
| Unchanged reviews | `10` |
| Delta reviews | `0` |
| Canonical posts written | `2` |
| Canonical comments written | `0` |
| Post metric snapshots written | `2` |
| Comment metric snapshots written | `0` |
| Failed persistence stages | `[]` |

Idempotency row count delta from first ingestion to second ingestion:

| Table | After First | After Second | Delta |
| --- | ---: | ---: | ---: |
| `alerts` | 0 | 0 | 0 |
| `analysis_results` | 3 | 3 | 0 |
| `business` | 3 | 3 | 0 |
| `client_messages_log` | 1 | 1 | 0 |
| `clients` | 2 | 2 | 0 |
| `comment_metric_snapshots` | 13 | 13 | 0 |
| `crawl_comments` | 13 | 13 | 0 |
| `crawl_jobs` | 5 | 6 | +1 |
| `crawl_logs` | 54 | 82 | +28 |
| `crawl_posts` | 6 | 6 | 0 |
| `post_metric_snapshots` | 6 | 8 | +2 |
| `reputation_score_snapshots` | 0 | 0 | 0 |
| `service_tasks` | 3 | 4 | +1 |

Canonical idempotency result:

- `crawl_posts` stayed at `6` total rows.
- `crawl_comments` stayed at `13` total rows.
- B3 canonical posts stayed at `2`.
- B3 canonical comments stayed at `10`.
- Second run updated latest-state posts to `crawl_job_id=17`; the first B3 crawl job `16` remains as execution history.
- Snapshot tables record the second observation; this is expected historical metric behavior.

## Precise Rollback Rehearsal

PASS.

Rollback artifact:

- `database/testdata/mvp_b3_google_maps_rollback_rehearsal.sql`

Selector:

| Field | Value |
| --- | --- |
| `business.id` | `8` |
| `business.name` | `Starbucks Taipei 101` |
| `service_tasks.id` | `8`, `9` |
| `crawl_jobs.id` | `16`, `17` |
| `crawl_jobs.platform` | `google_maps` |
| `crawl_posts.id` | `16`, `17` |
| `crawl_posts.platform_post_id` | `0x3442abb6c60c3a53:0xe2139b5525073efd`, `0x3442abb6da80a7ad:0x8836d2cc0215c472` |
| `crawl_posts.extra_data.platform` | `google_maps` |

The shared `clients.id = 8` row was not deleted by the B3 rollback selector because it predates B3 and is shared by earlier gates.

Transaction readback:

| Phase | Table | Row Count |
| --- | --- | ---: |
| `before` | `business` | 1 |
| `before` | `comment_metric_snapshots` | 10 |
| `before` | `crawl_comments` | 10 |
| `before` | `crawl_jobs` | 2 |
| `before` | `crawl_logs` | 56 |
| `before` | `crawl_posts` | 2 |
| `before` | `post_metric_snapshots` | 4 |
| `before` | `service_tasks` | 2 |
| `deleted` | `business` | 1 |
| `deleted` | `comment_metric_snapshots` | 10 |
| `deleted` | `crawl_comments` | 10 |
| `deleted` | `crawl_jobs` | 2 |
| `deleted` | `crawl_logs` | 56 |
| `deleted` | `crawl_posts` | 2 |
| `deleted` | `post_metric_snapshots` | 4 |
| `deleted` | `service_tasks` | 2 |
| `after_delete` | `business` | 0 |
| `after_delete` | `comment_metric_snapshots` | 0 |
| `after_delete` | `crawl_comments` | 0 |
| `after_delete` | `crawl_jobs` | 0 |
| `after_delete` | `crawl_logs` | 0 |
| `after_delete` | `crawl_posts` | 0 |
| `after_delete` | `post_metric_snapshots` | 0 |
| `after_delete` | `service_tasks` | 0 |

The final statement was `ROLLBACK`.

Post-rollback verification:

| Check | Result |
| --- | ---: |
| B3 business restored | 1 |
| B3 service tasks restored | 2 |
| B3 crawl jobs restored | 2 |
| B3 crawl posts restored | 2 |
| B3 crawl comments restored | 10 |
| B3 post metric snapshots restored | 4 |
| B3 comment metric snapshots restored | 10 |
| B3 crawl logs restored | 56 |
| `analysis_results` count | 3 |
| `business` total | 3 |
| `clients` total | 2 |
| `service_tasks` total | 4 |
| `crawl_jobs` total | 6 |
| `crawl_posts` total | 6 |
| `crawl_comments` total | 13 |
| `post_metric_snapshots` total | 8 |
| `comment_metric_snapshots` total | 13 |
| `crawl_logs` total | 82 |

## Full Regression

PASS.

```text
.\.venv\Scripts\python.exe -m pytest -q
```

Result:

- `299 passed`
- Warnings: `1`
- Warning: `StarletteDeprecationWarning` from `.venv\Lib\site-packages\fastapi\testclient.py`

## Conclusion

Gate B3 passed. The existing Google Maps single-platform path completed dry-run, source URL fallback discovery, place URL discovery, review parsing, canonical normalization, bounded staging ingestion, canonical idempotency, precise rollback rehearsal, and full regression. B4 and all non-Google-Maps integrations were not started.
