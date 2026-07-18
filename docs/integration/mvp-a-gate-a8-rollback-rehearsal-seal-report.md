# MVP-A Gate A8 Rollback Rehearsal And Staging Seal Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`
Supabase project ref: `qlhykeeyjaoikczoambe`
Archived staging commit: `987882de6cea81dd68dc62fd0dd833117fc7a7f1`

## Scope

Gate A8 verified that the MVP-A staging fixture can be precisely identified and safely rolled back, without leaving permanent STAGING database changes. It also created the MVP-A release manifest, rollback runbook, and branch archive document.

No crawler, n8n, LINE, Ollama, migration, deployment, schema change, RLS change, main merge, or main push was executed.

## Preflight

PASS.

- Branch: `integration/bi-rmp-v2-staging-v2`
- Branch sync before A8: `0 0` against `origin/integration/bi-rmp-v2-staging-v2`
- Worktree before A8: clean
- `.env.staging`: present and gitignored
- `SUPABASE_PROJECT_REF`: `qlhykeeyjaoikczoambe`
- `ALLOW_DATABASE_WRITES=false`
- Port `8000`: not listening
- Port `8010`: not listening

Project handoff note:

- `docs/database_execution_runbook.md` exists and was reviewed.
- `docs/AGENT_HANDOFF.md` was not present.
- `docs/architecture_review.md` was not present.

## Rollback Rehearsal

PASS.

Method:

- SQL file: `database/testdata/mvp_a_fixture_rollback.sql`
- Execution mode: single database transaction
- Verification inside transaction: fixture rows deleted
- Final transaction action: `ROLLBACK`
- Permanent STAGING database changes: none

Expected deletion counts matched the rollback SQL output:

| Table | Deleted rows inside transaction |
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

Fixture state inside the transaction after rollback SQL:

| Object | Count |
| --- | ---: |
| Fixture business | 0 |
| Fixture service tasks | 0 |
| Fixture crawl jobs | 0 |
| Fixture crawl posts | 0 |
| Fixture crawl comments | 0 |
| Fixture analysis results | 0 |
| Fixture clients | 0 |
| Fixture client messages | 0 |
| Fixture post metric snapshots | 0 |
| Fixture comment metric snapshots | 0 |
| Fixture crawl logs | 0 |

## Post-Rehearsal Database State

PASS. Transaction rollback restored the pre-rehearsal state exactly.

| Table | Before rehearsal | After transaction rollback |
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

Fixture state after transaction rollback:

| Object | Count |
| --- | ---: |
| Fixture business | 1 |
| Fixture service tasks | 1 |
| Fixture crawl jobs | 3 |
| Fixture crawl posts | 3 |
| Fixture crawl comments | 3 |
| Fixture analysis results | 3 |
| Fixture clients | 1 |
| Fixture client messages | 1 |
| Fixture post metric snapshots | 3 |
| Fixture comment metric snapshots | 3 |
| Fixture crawl logs | 1 |

## Seal Artifacts

PASS.

- Release manifest: `docs/integration/mvp-a-release-manifest.md`
- Rollback runbook: `docs/integration/mvp-a-rollback-runbook.md`
- Branch archive: `docs/integration/mvp-a-staging-branch-archive.md`

## Tests

PASS.

- Dashboard tests: `26 passed, 1 warning`
- ML focused tests: `15 passed, 1 warning`
- Core regression: `298 passed, 1 warning`

## Shutdown

PASS.

- Port `8000`: stopped
- Port `8010`: stopped

## Conclusion

Gate A8 passed. The MVP-A staging baseline can be safely inspected, the fixture rollback method is precise and reversible when rehearsed inside a transaction, no permanent STAGING database change remained after the rehearsal, and the staging branch state is archived in release documentation.
