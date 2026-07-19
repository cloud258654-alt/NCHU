# MVP-B Gate B2 PTT Staging Ingestion Report

Date: 2026-07-19
Branch: `feature/mvp-b-b2-ptt-staging`
Baseline commit: `0e7aa49c10d089016bdd4bc985e713f6c1fd90ce`
Supabase project: `BI-RMP-V2-STAGING`
Supabase project ref: `qlhykeeyjaoikczoambe`

## Scope

Gate B2 executed only the PTT staging ingestion path.

No B3 work was started. Google Maps, Threads, n8n, LINE, Ollama, post-crawl AI execution, migrations, schema changes, RLS changes, production, old Supabase projects, `main` merge, and `main` push were not executed.

## Preflight

PASS with one branch-ref warning.

- Local branch: `feature/mvp-b-b2-ptt-staging`
- Local HEAD: `0e7aa49c10d089016bdd4bc985e713f6c1fd90ce`
- Worktree before B2: clean
- Recent history included B1 merge commit `0e7aa49` and B1 commit `6b9f4a3`
- `origin/feature/mvp-b-b2-ptt-staging`: not present before or after `git fetch origin`
- `.env.staging`: present and gitignored
- `APP_ENV=staging`
- `SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe`
- `SUPABASE_URL`: present and matched `qlhykeeyjaoikczoambe`
- `DATABASE_URL`: present and matched `qlhykeeyjaoikczoambe`
- `ALLOW_DATABASE_WRITES=false` in `.env.staging`; B2 overrode it to `true` only for the ingestion process
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

Supabase documentation/changelog check:

- Supabase changelog was checked before the staging database operation.
- Relevant current note: 2026 Data/GraphQL API default table exposure changes are not blocking for this existing service-role PostgreSQL ingestion, but remain relevant for future public API/grant work.

## Tests Before Ingestion

PASS.

```text
.\.venv\Scripts\python.exe -m pytest Backend\tests\adapters\test_ptt_parser.py Backend\tests\core\test_runtime_staging_guard.py
```

Result:

- `34 passed`

## Ingestion Command

PASS.

Command shape:

```powershell
$env:APP_ENV = 'staging'
$env:SUPABASE_PROJECT_REF = 'qlhykeeyjaoikczoambe'
$env:ALLOW_DATABASE_WRITES = 'true'
$env:ALLOW_PRODUCTION_DB = 'false'
$env:SEARCH_ENGINE = 'duckduckgo'
.\.venv\Scripts\python.exe Backend\runner.py `
  --platform ptt `
  --business-name coffee `
  --keyword review `
  --max-results 1 `
  --ptt-max-posts 1 `
  --ptt-max-pages 1 `
  --max-minutes 0.5 `
  --ptt-max-minutes 0.5 `
  --browser-concurrency 1 `
  --persistence-grace-seconds 5 `
  --skip-ai `
  --json-summary
```

Result:

| Check | Result |
| --- | --- |
| Selected platforms | `["ptt"]` |
| Search query | `coffee review` |
| Search engine attempted | `duckduckgo` |
| PTT board fallback used | `Food` |
| URL discovery | 1 |
| Cards found | 1 |
| Comments found | 0 |
| Existing records loaded | 0 |
| Delta posts | 1 |
| Status | `success` |
| Outcome | `success_with_data` |
| Canonical posts written | 1 |
| Canonical comments written | 0 |
| Post metric snapshots written | 1 |
| Comment metric snapshots written | 0 |
| Failed persistence stages | `[]` |
| Service task ID | `7` |
| Crawl job ID | `15` |
| Elapsed | 24.86 seconds |

The PTT adapter wrote a local buffer during preservation and the runner cleaned it up at shutdown. No local PTT buffer or debug HTML directory remained after the command.

`--skip-ai` was set. The adapter summary included `ai_items_enqueued: 1` as a delta-count field, but runner-level post-crawl AI execution was skipped and `analysis_results` row count remained unchanged.

## Database Row Count Delta

PASS.

| Table | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `alerts` | 0 | 0 | 0 |
| `analysis_results` | 3 | 3 | 0 |
| `business` | 1 | 2 | +1 |
| `client_messages_log` | 1 | 1 | 0 |
| `clients` | 1 | 2 | +1 |
| `comment_metric_snapshots` | 3 | 3 | 0 |
| `crawl_comments` | 3 | 3 | 0 |
| `crawl_jobs` | 3 | 4 | +1 |
| `crawl_logs` | 1 | 26 | +25 |
| `crawl_posts` | 3 | 4 | +1 |
| `post_metric_snapshots` | 3 | 4 | +1 |
| `reputation_score_snapshots` | 0 | 0 | 0 |
| `service_tasks` | 1 | 2 | +1 |

## Staging Readback

PASS.

| Field | Value |
| --- | --- |
| `service_tasks.id` | `7` |
| `service_tasks.status` | `completed` |
| `service_tasks.service_type` | `reputation_monitoring` |
| `service_tasks.schedule_type` | `once` |
| `service_tasks.config.channel` | `cli` |
| Business | `coffee` |
| `crawl_jobs.id` | `15` |
| `crawl_jobs.platform` | `ptt` |
| `crawl_jobs.status` | `success` |
| `crawl_jobs.keyword` | `review` |
| `crawl_jobs.total_posts` | `1` |
| `crawl_jobs.total_comments` | `0` |
| `crawl_posts.id` | `15` |
| `crawl_posts.platform_post_id` | `M.1783265624.A.F68.html` |
| `crawl_posts.link` | `https://www.ptt.cc/bbs/Food/M.1783265624.A.F68.html` |
| `crawl_posts.title` | Stored in staging; not reproduced here because the terminal readback rendered non-ASCII text inconsistently |
| `crawl_posts.crawl_count` | `1` |
| Post metric snapshots for post | `1` |
| Crawl comments for post | `0` |

The canonical join path was verified:

```text
business -> service_tasks -> crawl_jobs -> crawl_posts -> post_metric_snapshots
```

## Supplemental Acceptance And Precise Rollback

PASS.

The supplemental acceptance was run on 2026-07-19 after the initial B2 ingestion. The Supabase target was checked again through the connector before SQL execution:

- Project: `BI-RMP-V2-STAGING`
- Project ref: `qlhykeeyjaoikczoambe`
- Status: `ACTIVE_HEALTHY`

Current staging row counts remained at the B2 post-ingestion state:

| Table | Row Count |
| --- | ---: |
| `alerts` | 0 |
| `analysis_results` | 3 |
| `business` | 2 |
| `client_messages_log` | 1 |
| `clients` | 2 |
| `comment_metric_snapshots` | 3 |
| `crawl_comments` | 3 |
| `crawl_jobs` | 4 |
| `crawl_logs` | 26 |
| `crawl_posts` | 4 |
| `post_metric_snapshots` | 4 |
| `reputation_score_snapshots` | 0 |
| `service_tasks` | 2 |

B2 join readback remained valid:

| Check | Result |
| --- | --- |
| `service_tasks.id` | `7` |
| `service_tasks.status` | `completed` |
| `crawl_jobs.id` | `15` |
| `crawl_jobs.platform` | `ptt` |
| `crawl_jobs.status` | `success` |
| `crawl_jobs.execution_config.result_summary.outcome` | `success_with_data` |
| `crawl_jobs.execution_config.result_summary.canonical_posts_written` | `1` |
| `crawl_posts.id` | `15` |
| `post_metric_snapshots` for B2 post | `1` |
| `crawl_comments` for B2 post | `0` |

The earlier marker-only rehearsal was superseded because it did not prove fixture removal inside the transaction. The final rollback rehearsal used a precise B2 selector and transaction-scoped deletes, with `ROLLBACK` as the final statement.

Rollback selector:

| Field | Value |
| --- | --- |
| `service_tasks.id` | `7` |
| `business.id` | `7` |
| `business.name` | `coffee` |
| `clients.id` | `8` |
| `clients.line_user_id` | `default-line-id` |
| `crawl_jobs.id` | `15` |
| `crawl_jobs.platform` | `ptt` |
| `crawl_posts.id` | `15` |
| `crawl_posts.platform_post_id` | `M.1783265624.A.F68.html` |
| `crawl_posts.link` | `https://www.ptt.cc/bbs/Food/M.1783265624.A.F68.html` |
| `crawl_posts.extra_data.platform` | `ptt` |
| `crawl_posts.dedupe_key` | `NULL` |

Rollback artifact:

- `database/testdata/mvp_b2_ptt_rollback_rehearsal.sql`

Command shape:

```sql
begin;
create temporary table gate_b2_ptt_target on commit drop as ...
delete from public.comment_metric_snapshots where ...;
delete from public.crawl_comments where ...;
delete from public.post_metric_snapshots where ...;
delete from public.crawl_posts where ...;
delete from public.crawl_logs where ...;
delete from public.crawl_jobs where ...;
delete from public.service_tasks where ...;
delete from public.business where ...;
delete from public.clients where ...;
select phase, table_name, row_count
from gate_b2_ptt_rehearsal_counts
order by ...;
rollback;
```

Transaction readback:

| Phase | Table | Row Count |
| --- | --- | ---: |
| `before` | `business` | 1 |
| `before` | `clients` | 1 |
| `before` | `comment_metric_snapshots` | 0 |
| `before` | `crawl_comments` | 0 |
| `before` | `crawl_jobs` | 1 |
| `before` | `crawl_logs` | 25 |
| `before` | `crawl_posts` | 1 |
| `before` | `post_metric_snapshots` | 1 |
| `before` | `service_tasks` | 1 |
| `deleted` | `business` | 1 |
| `deleted` | `clients` | 1 |
| `deleted` | `comment_metric_snapshots` | 0 |
| `deleted` | `crawl_comments` | 0 |
| `deleted` | `crawl_jobs` | 1 |
| `deleted` | `crawl_logs` | 25 |
| `deleted` | `crawl_posts` | 1 |
| `deleted` | `post_metric_snapshots` | 1 |
| `deleted` | `service_tasks` | 1 |
| `after_delete` | `business` | 0 |
| `after_delete` | `clients` | 0 |
| `after_delete` | `comment_metric_snapshots` | 0 |
| `after_delete` | `crawl_comments` | 0 |
| `after_delete` | `crawl_jobs` | 0 |
| `after_delete` | `crawl_logs` | 0 |
| `after_delete` | `crawl_posts` | 0 |
| `after_delete` | `post_metric_snapshots` | 0 |
| `after_delete` | `service_tasks` | 0 |

Post-rollback verification:

| Check | Result |
| --- | --- |
| `service_tasks.id = 7` | `1` |
| `business.id = 7` | `1` |
| `clients.id = 8` | `1` |
| `crawl_jobs.id = 15` | `1` |
| `crawl_posts.id = 15` | `1` |
| `post_metric_snapshots` for B2 post | `1` |
| `crawl_comments` for B2 post | `0` |
| `comment_metric_snapshots` for B2 post | `0` |
| `crawl_logs` for B2 task | `25` |
| `service_tasks` count | `2` |
| `business` count | `2` |
| `clients` count | `2` |
| `crawl_jobs` count | `4` |
| `crawl_posts` count | `4` |
| `post_metric_snapshots` count | `4` |
| `crawl_logs` count | `26` |
| `analysis_results` count | `3` |

This proves the transaction-internal B2 fixture count reached zero and the final `ROLLBACK` restored the fixture and core row counts.

## Final Regression

PASS.

Focused tests:

```text
.\.venv\Scripts\python.exe -m pytest Backend\tests\adapters\test_ptt_parser.py Backend\tests\core\test_runtime_staging_guard.py
```

Result:

- `34 passed`
- Warnings: `0`

Full regression:

```text
.\.venv\Scripts\python.exe -m pytest -q
```

Result:

- `299 passed`
- Warnings: `1`
- Warning: `StarletteDeprecationWarning` from `.venv\Lib\site-packages\fastapi\testclient.py`

Supplemental acceptance did not run Google Maps, Threads, n8n, LINE, Ollama, post-crawl AI, migration, schema, RLS, grant, policy, production, old Supabase, `main` merge, or `main` push operations.

## Conclusion

Gate B2 passed. The PTT-only runner path performed one bounded live crawl and wrote the expected staging records to `BI-RMP-V2-STAGING` only. B3 and all non-PTT integrations were not started.
