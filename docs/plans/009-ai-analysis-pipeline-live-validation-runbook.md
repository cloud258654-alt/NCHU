# 009 AI Analysis Pipeline — Live Validation Runbook

## Purpose and current status

This is a planning-only runbook. It authorizes no database, worker, crawler, LINE, LIFF, n8n, Staging, Production, Git, or rollback action by itself.

```text
BASELINE_COMMIT: f56aa58 feat(analysis): add resilient queued analysis pipeline
LOCAL_VERIFICATION: PASS (357 passed, 1 warning)
LIVE_STAGING: NOT_VERIFIED
GATE_C2: NOT_PASS
PUSH: NOT_EXECUTED
```

## Hard safety boundaries

- The only possible future database target is `BI-RMP-V2-STAGING` (`qlhykeeyjaoikczoambe`). Verify the project ref before every approved operation; do not infer it from a URL or environment variable.
- Production is permanently out of scope. Do not connect to, query, alter, or validate Production.
- Do not print connection strings, credentials, tokens, claim tokens, real user identifiers, or fixture contents in command output, logs, Git, or evidence.
- No SQL, migration, worker launch, fixture creation, rollback rehearsal, push, or merge may occur without its separate human approval gate below.

## Migration preflight

Run this section only after approval to connect to Staging and approval to run read-only preflight SQL.

1. Confirm the connected project ref is exactly the approved Staging ref and record only a presence/match result.
2. Read migration history and confirm:
   - `20260722_analysis_queue_pipeline.sql` is already represented by the approved prior deployment.
   - `20260723_analysis_queue_lease_fencing.sql` is not yet represented and remains `CREATED_NOT_APPLIED` locally.
3. Read `analysis_results` schema and indexes. Record presence-only results for:
   - Existing queue fields: `idempotency_key`, `attempt_count`, `next_attempt_at`, `claimed_at`, `last_error`.
   - New lease/fencing fields: `worker_id`, `claim_token`, `locked_at`, `heartbeat_at`, `lease_expires_at`, `updated_at`.
   - Queue indexes: idempotency unique index, pending-queue index, and lease-recovery index.
4. Confirm there is no concurrent migration, active worker, or unresolved queue fixture that would make the change unsafe.
5. Review the forward migration text against the deployed schema. It must remain additive: no `DROP`, `TRUNCATE`, destructive data rewrite, or policy change.
6. Obtain a separate approval before applying the migration. The application process must remain stopped until the schema change is verified.

## Rollback and recovery strategy

`20260723_analysis_queue_lease_fencing.sql` is additive. Recovery should first be operational rather than destructive:

1. Stop approved workers and confirm no fixture queue row is `processing`, no unexpired lease exists, and no claim token is still owned.
2. Preserve migration history and evidence. Prefer disabling worker execution or rolling application code back to the previous compatible revision while the additive columns and index remain in place.
3. Column or index removal is a separate destructive rollback decision. The potentially removable objects are `worker_id`, `claim_token`, `locked_at`, `heartbeat_at`, `lease_expires_at`, `updated_at`, and `idx_analysis_results_lease`.
4. Do not generate or execute removal SQL in advance. A rollback requires separate human approval, a verified inactive queue, a backup/recovery plan, and a dedicated rehearsal.

## Minimal live validation dataset

Use only fictional data. Never select or modify a real client, business, task, crawl job, post, comment, or analysis result.

- Fixture selector: `fixture_run_id = 009-lv-<UTC timestamp>-<random suffix>`.
- Store the selector in the fictional service task `config` and fictional crawl job `execution_config`; record it in approved analysis queue metadata only if needed for readback.
- Maximum scope: one fictional client, one fictional business, one fictional task, one fictional crawl job, and at most four canonical targets/queue rows.
- Use synthetic post/comment text that contains no personal data and no operational secret.
- Capture pre- and post-validation row counts scoped exclusively by the fixture selector and target ids.
- Do not delete fixture data during validation. Any separately approved rollback rehearsal must run entirely inside an explicit transaction and finish with `ROLLBACK`; it must not persist fixture or schema changes. Otherwise retain the fixture as precisely identifiable test data for a separately approved cleanup.

## Live worker validation cases

Run only approved cases against the minimal fixture scope. Record state transitions and sanitized diagnostics, not source content or tokens.

| Case | Expected evidence |
| --- | --- |
| Enqueue idempotency | Repeating enqueue for unchanged target/content/version produces no duplicate queue row. |
| Concurrent claim | Two approved worker identities claim distinct rows; `FOR UPDATE SKIP LOCKED` prevents duplicate ownership. |
| Heartbeat | A processing job refreshes `heartbeat_at` and extends `lease_expires_at` while its worker remains active. |
| Claim-token fencing | An old worker cannot heartbeat, complete, retry, or fail after a replacement claim owns the row. |
| Retry attempts 1 and 2 | The row becomes pending with sanitized error code and deferred next attempt. |
| Attempt 3 | An exhausted or stale third attempt becomes failed and cannot be claimed again. |
| Completed result | A valid rules-baseline result becomes completed and clears claim/lease ownership. |
| Dashboard latest valid | Pending, processing, and failed newer rows do not hide the latest completed result. |
| Sanitized error | Logs and result diagnostics contain only approved error classes/codes, never source text or claim token. |
| Tenant/task isolation | Task-scoped readback resolves only the fictional task and does not return other tenant/task data. |

## RLS decision required

`HUMAN_DECISION_REQUIRED`

The access model for `analysis_results` and queue operations must be approved before live validation:

- **Backend service role:** may need narrowly scoped insert/update/select for queue enqueue, claim, heartbeat, completion, failure, and readback. It bypasses RLS, so application-level tenant/task scoping and operational access controls remain mandatory.
- **Authenticated dashboard user:** should receive only task/business-scoped completed-result reads through approved API or RLS policy. A broad table policy risks cross-tenant data exposure.
- **Anonymous user:** should receive no direct access to `analysis_results` or queue state.

Possible models are service-role-only database access behind the backend API, or explicit authenticated read policies tied to a verified ownership relation. Do not create a policy until the product owner confirms the intended dashboard identity and tenant/task authorization model.

## Human approval gates

Each item requires an explicit, separate approval. Approval for one item does not imply approval for the next item.

1. Connect to the Staging project.
2. Execute read-only preflight SQL.
3. Apply `20260723_analysis_queue_lease_fencing.sql`.
4. Perform schema column/index readback after the migration.
5. Start an isolated worker.
6. Create the fictional fixture dataset.
7. Run a transaction rollback rehearsal.
8. Push this branch.
9. Merge to `main`.

## Expected evidence

- Staging project-ref presence/match result only.
- Migration-history status and schema column/index readback.
- Fixture-scoped row counts before and after each validation case.
- Queue transitions: pending, processing, retry, failed, completed, lease recovery, and fenced-write rejection.
- `analysis_results` and Dashboard task-scoped readback for the fictional fixture only.
- RLS decision record and approved role model.
- Production unchanged confirmation.
- Secret scan result with no secret values emitted.
- Rollback rehearsal result, if separately approved.

## Final status template

```text
RESULT: PASS | FAIL | BLOCKED | HUMAN_ACTION_REQUIRED
BRANCH:
TARGET_DATABASE:
MIGRATION_STATUS:
FIXTURE_SCOPE:
QUEUE_TEST_RESULTS:
WORKER_TEST_RESULTS:
DASHBOARD_READBACK:
RLS_STATUS:
ROLLBACK_STATUS:
PRODUCTION_CHANGED:
SECRETS_EXPOSED:
GATE_C2_STATUS:
NEXT_ACTION:
```

Do not mark 009 or Gate C2 as final PASS until every approved live-validation case, RLS decision, migration evidence, and rollback decision is complete.
