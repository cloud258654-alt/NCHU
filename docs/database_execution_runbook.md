# Database Execution Runbook

## Active SQL

- Clean rebuild: `database/schema.sql`
- Existing Supabase cutover: `database/migrations/20260713_refactor_crawl_relationships_latest_only.sql`

The cutover migration must be deployed with the matching backend change. Stop crawler writes during the transaction.

## Safety rules

- Back up Supabase first if runtime data must be kept.
- The migration does not delete unresolved rows or protected `review%` / `master_reviews_enriched` tables.
- Historical cutover note: A previous live preflight found `crawl_posts.id = 393` without a verifiable job. Migration preflight verifies that all orphan rows are resolved, exported/deleted, or cleanly rebuilt before cutover transaction completes.
- Do not grant context-view access before reviewing Supabase RLS policies.

## Expected runtime tables

`clients`, `business`, `service_tasks`, `crawl_jobs`, `crawl_posts`, `crawl_comments`, `post_metric_snapshots`, `comment_metric_snapshots`, `analysis_results`, `reputation_score_snapshots`, `alerts`, and `client_messages_log`.

Observation tables and first/last crawl-job columns must not exist after cutover.

## Clean rebuild

```powershell
python Backend/scripts/reset_supabase_schema.py
```

## Smoke test

```powershell
python Backend/runner.py `
  --business-name "文章牛肉湯" `
  --keyword "服務態度" `
  --max-results 1 `
  --dry-run

python Backend/runner.py `
  --business-name "文章牛肉湯" `
  --keyword "服務態度" `
  --max-results 1

python Backend/scripts/verify_supabase_ingestion.py
```

## Join verification

```sql
select
  cp.id as crawl_post_id,
  cp.crawl_job_id,
  cj.service_task_id,
  st.business_id,
  b.name as business_name,
  cj.platform,
  cj.keyword,
  cp.link,
  cp.updated_at
from crawl_posts cp
join crawl_jobs cj on cj.id = cp.crawl_job_id
join service_tasks st on st.id = cj.service_task_id
join business b on b.id = st.business_id
order by cp.updated_at desc
limit 20;
```

Expected: every canonical post/comment resolves to one current crawl job and business.
