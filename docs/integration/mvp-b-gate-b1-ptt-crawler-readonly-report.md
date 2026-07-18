# MVP-B Gate B1 PTT Crawler Read-Only Validation Report

Date: 2026-07-18
Branch: `feature/mvp-b-external-integrations`
Repository: `cloud258654-alt/NCHU`
MVP-A A8 baseline commit: `7fd12088a8013cbd9914fae9501ebce098e9775c`
Staging project ref checked for row-count safety: `qlhykeeyjaoikczoambe`

## Scope

Gate B1 validated only the PTT crawler path. Google Maps, Threads, n8n, LINE, Ollama, deployment, production, and later MVP-B gates were not executed.

The live crawler checks were executed with:

- `--platform ptt`
- `--dry-run`
- `--skip-ai`
- `DATABASE_URL` cleared in the crawler process
- `ALLOW_DATABASE_WRITES=false`

## Preflight

PASS.

- Initial branch before switch: `integration/bi-rmp-v2-staging-v2`
- Target branch after switch: `feature/mvp-b-external-integrations`
- Target branch was up to date with `origin/feature/mvp-b-external-integrations`
- Baseline HEAD before B1 changes: `7fd12088a8013cbd9914fae9501ebce098e9775c`
- `.env.staging` remained gitignored
- Staging row-count checks used read-only database sessions only

Project handoff note:

- `docs/database_execution_runbook.md` exists and was reviewed.
- `docs/AGENT_HANDOFF.md` was not present.
- `docs/architecture_review.md` was not present.

## CLI Entry

PASS.

Command:

```powershell
$env:DATABASE_URL = ""
.\.venv\Scripts\python.exe Backend\runner.py --help
```

Verified CLI options include:

- `--business-name`
- `--keyword`
- `--platform {ptt,google_maps,threads,all}`
- `--json-summary`
- `--dry-run`
- `--skip-ai`
- `--ptt-max-minutes`
- `--ptt-max-posts`
- `--ptt-max-pages`

## Live PTT Dry-Run With Data

PASS.

Command shape:

```powershell
$env:DATABASE_URL = ""
$env:ALLOW_DATABASE_WRITES = "false"
$env:SEARCH_ENGINE = "duckduckgo"
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
  --persistence-grace-seconds 2 `
  --dry-run `
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
| Article fetch attempted | 1 |
| Article fetch success | 1 |
| Parser success | 1 |
| Filter kept posts | 1 |
| Cards found | 1 |
| Comments found | 0 |
| Status | `success` |
| Outcome | `success_no_changes` |
| Inserted | 0 |
| Canonical posts written | 0 |
| Canonical comments written | 0 |
| DB rows written | 0 |
| Elapsed | 5.47 seconds |

The run wrote a local PTT buffer as part of the dry-run preservation path and then cleaned it up. No tracked file remained from the buffer.

## Empty Result Handling

PASS.

The empty-result check used the PTT adapter CLI path with a single board filter to avoid cross-board timeout ambiguity.

Result:

| Check | Result |
| --- | --- |
| Query | `gateb1-no-such-term-zzzxxyy noresult-zzzxxyy` |
| Board | `Food` |
| URL discovery | 0 |
| Article fetch attempted | 0 |
| Parser success | 0 |
| Cards found | 0 |
| Comments found | 0 |
| Status | `success` |
| Outcome | `success_no_results` |
| Inserted | 0 |
| Buffer written | false |
| Elapsed | 1.48 seconds |

## Error Handling

PASS.

Command:

```powershell
$env:DATABASE_URL = ""
$env:ALLOW_DATABASE_WRITES = "false"
.\.venv\Scripts\python.exe Backend\runner.py `
  --platform ptt `
  --business-name coffee `
  --max-minutes 0 `
  --dry-run `
  --skip-ai `
  --json-summary
```

Result:

- Exit code: `1`
- Error: `--max-minutes must be > 0.`
- No HTTP crawl started.
- No DB connection was made.

## B1 Fix

PASS.

During B1, an all-default-board empty query showed that PTT discovery could continue until the outer hard timeout before returning. The minimal fix was to propagate the existing crawl deadline into PTT discovery and constrain board fallback fetch timeout/attempts by the remaining time.

Changed files:

- `Backend/adapters/ptt/crawler.py`
- `Backend/tests/adapters/test_ptt_parser.py`

The fix does not modify database schema, ML contract, non-PTT crawler behavior, n8n, LINE, Ollama, or deployment code.

## Database Safety

PASS.

Staging row counts before and after live PTT dry-run were identical.

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

- PTT and runner focused tests: `39 passed`
- Core regression: `299 passed, 1 warning`

## Conclusion

Gate B1 passed after one PTT-only deadline handling fix. The PTT crawler CLI, keyword input, search flow, HTTP/page fetch, parsing/normalization, empty-result handling, error handling, execution time, and no-DB-write boundary were verified. No later MVP-B integration was started.
