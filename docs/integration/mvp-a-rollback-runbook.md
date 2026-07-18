# MVP-A Rollback Runbook

Date: 2026-07-18
Target: BI-RMP-V2-STAGING
Supabase project ref: `qlhykeeyjaoikczoambe`
Fixture marker: `mvp-a-fixture-001`
Rollback SQL: `database/testdata/mvp_a_fixture_rollback.sql`

## Purpose

This runbook defines how to remove only the MVP-A fictional fixture data from STAGING and how to verify that unrelated runtime data remains untouched.

The rollback target is the fixture data created for MVP-A Gates A3 through A5:

- Fixture business
- Fixture service task
- Fixture crawl jobs
- Fixture crawl posts and comments
- Fixture metric snapshots
- Fixture analysis results
- Fixture client message log
- Fixture crawl log
- Related fixture alerts or reputation score snapshots if they exist

## Safety Preconditions

Before an actual rollback:

1. Confirm the active branch is `integration/bi-rmp-v2-staging-v2`.
2. Confirm the target Supabase project ref is `qlhykeeyjaoikczoambe`.
3. Confirm `.env.staging` is gitignored and not committed.
4. Confirm the operator is intentionally targeting STAGING, not production.
5. Stop crawler, n8n, LINE workflow triggers, and any writeback workers.
6. Confirm no production deployment is in progress.
7. Take a row-count snapshot for all 13 runtime tables.

Do not paste or print `DATABASE_URL`, service role keys, database passwords, or connection credentials into logs, reports, commits, or chat.

## Dry-Run Rehearsal Pattern

Use this pattern to rehearse rollback without leaving permanent database changes:

```sql
begin;

-- Execute database/testdata/mvp_a_fixture_rollback.sql here.

-- Verify marker rows are zero inside the transaction.

rollback;
```

Expected rehearsal result:

| Table | Expected rows deleted inside transaction |
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

After `ROLLBACK`, the row-count snapshot must match the pre-rehearsal snapshot exactly.

## Actual Rollback Procedure

Only perform actual rollback after explicit operator approval.

1. Confirm project target:

```powershell
Get-Content supabase\.temp\project-ref
```

Expected value:

```text
qlhykeeyjaoikczoambe
```

2. Confirm `.env.staging` safety without printing credentials:

```powershell
git check-ignore -v .env.staging
```

3. Confirm writes are intentionally disabled for the application runtime:

```powershell
Get-Content .env.staging | Where-Object { $_ -eq 'ALLOW_DATABASE_WRITES=false' }
```

4. Stop application services and writers:

```powershell
$ports = 8000,8010
foreach ($port in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($conn in $conns) {
    Stop-Process -Id $conn.OwningProcess -Force
  }
}
```

5. Take a runtime table row-count snapshot.

6. Execute `database/testdata/mvp_a_fixture_rollback.sql` against BI-RMP-V2-STAGING.

7. Verify all `mvp-a-fixture-001` marker rows are removed.

8. Verify unrelated data counts are unchanged except for the expected fixture rows.

9. Run Dashboard and Core tests before continuing with any later gate.

## Verification Queries

Use marker-based checks instead of relying only on raw table counts.

```sql
select count(*) as fixture_businesses
from public.business
where config = 'fixture_id=mvp-a-fixture-001';
```

```sql
select count(*) as fixture_reviews
from public.crawl_posts
where extra_data->>'fixture_id' = 'mvp-a-fixture-001'
   or dedupe_key like 'mvp-a-fixture-%'
   or link like 'https://example.test/mvp-a/fixture/%';
```

```sql
select count(*) as fixture_analysis_results
from public.analysis_results ar
where ar.score_explanation->>'fixture_id' = 'mvp-a-fixture-001'
   or (
     ar.target_type = 'crawl_post'
     and ar.target_id in (
       select cp.id
       from public.crawl_posts cp
       where cp.extra_data->>'fixture_id' = 'mvp-a-fixture-001'
          or cp.dedupe_key like 'mvp-a-fixture-%'
          or cp.link like 'https://example.test/mvp-a/fixture/%'
     )
   );
```

Expected result after actual rollback:

- Fixture business count: 0
- Fixture review count: 0
- Fixture analysis result count: 0
- Orphan rows: 0

## Recovery

If the fixture must be restored after an actual rollback, use the committed fixture apply script:

```text
database/testdata/mvp_a_fixture.sql
```

Then rerun the MVP-A A3 to A7 verification sequence before treating STAGING as sealed again.

## A8 Rehearsal Result

The Gate A8 rehearsal executed the rollback SQL inside one database transaction and rolled the transaction back. It left no permanent STAGING database changes.
