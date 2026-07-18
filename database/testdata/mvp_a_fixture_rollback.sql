-- Roll back only the MVP-A Gate A3 fictional staging fixture.
-- Target marker: fixture_id=mvp-a-fixture-001
-- This script is idempotent and leaves unrelated runtime data untouched.

with
fixture_clients as (
  select id from public.clients where line_user_id = 'mvp-a-fictional-line-user-001'
),
fixture_business as (
  select b.id
  from public.business b
  left join fixture_clients c on c.id = b.client_id
  where c.id is not null
     or b.config = 'fixture_id=mvp-a-fixture-001'
     or b.name in ('MVP 測試咖啡館', 'MVP-A Fictional Test Store')
),
fixture_tasks as (
  select id from public.service_tasks
  where config->>'fixture_id' = 'mvp-a-fixture-001'
     or business_id in (select id from fixture_business)
),
fixture_jobs as (
  select id from public.crawl_jobs
  where execution_config->>'fixture_id' = 'mvp-a-fixture-001'
     or service_task_id in (select id from fixture_tasks)
),
fixture_posts as (
  select id from public.crawl_posts
  where extra_data->>'fixture_id' = 'mvp-a-fixture-001'
     or dedupe_key like 'mvp-a-fixture-%'
     or link like 'https://example.test/mvp-a/fixture/%'
     or crawl_job_id in (select id from fixture_jobs)
),
fixture_comments as (
  select id from public.crawl_comments
  where extra_data->>'fixture_id' = 'mvp-a-fixture-001'
     or dedupe_key like 'mvp-a-fixture-%'
     or crawl_post_id in (select id from fixture_posts)
),
del_crawl_logs as (
  delete from public.crawl_logs
  where service_task_id in (select id from fixture_tasks)
     or message = 'MVP-A fixture inserted without crawler'
  returning id
),
del_client_messages as (
  delete from public.client_messages_log
  where line_user_id = 'mvp-a-fictional-line-user-001'
     or intent in ('mvp_a_fixture_request', 'mvp_a_fixture_alert', 'mvp_a_fixture')
     or session_state->>'fixture_id' = 'mvp-a-fixture-001'
  returning id
),
del_alerts as (
  delete from public.alerts
  where alert_type = 'mvp_a_fixture_high_risk'
     or business_id in (select id from fixture_business)
     or analysis_result_id in (
       select id from public.analysis_results where score_explanation->>'fixture_id' = 'mvp-a-fixture-001'
     )
  returning id
),
del_reputation as (
  delete from public.reputation_score_snapshots
  where details->>'fixture_id' = 'mvp-a-fixture-001'
     or business_id in (select id from fixture_business)
  returning id
),
del_analysis as (
  delete from public.analysis_results
  where score_explanation->>'fixture_id' = 'mvp-a-fixture-001'
     or (target_type = 'crawl_post' and target_id in (select id from fixture_posts))
     or (target_type = 'crawl_comment' and target_id in (select id from fixture_comments))
  returning id
),
del_comment_metrics as (
  delete from public.comment_metric_snapshots
  where crawl_comment_id in (select id from fixture_comments)
  returning id
),
del_post_metrics as (
  delete from public.post_metric_snapshots
  where crawl_post_id in (select id from fixture_posts)
  returning id
),
del_comments as (
  delete from public.crawl_comments where id in (select id from fixture_comments) returning id
),
del_posts as (
  delete from public.crawl_posts where id in (select id from fixture_posts) returning id
),
del_jobs as (
  delete from public.crawl_jobs where id in (select id from fixture_jobs) returning id
),
del_tasks as (
  delete from public.service_tasks where id in (select id from fixture_tasks) returning id
),
del_business as (
  delete from public.business where id in (select id from fixture_business) returning id
),
del_clients as (
  delete from public.clients where id in (select id from fixture_clients) returning id
)
select * from (
  select 'crawl_logs' as table_name, count(*)::int as deleted_rows from del_crawl_logs
  union all select 'client_messages_log', count(*)::int from del_client_messages
  union all select 'alerts', count(*)::int from del_alerts
  union all select 'reputation_score_snapshots', count(*)::int from del_reputation
  union all select 'analysis_results', count(*)::int from del_analysis
  union all select 'comment_metric_snapshots', count(*)::int from del_comment_metrics
  union all select 'post_metric_snapshots', count(*)::int from del_post_metrics
  union all select 'crawl_comments', count(*)::int from del_comments
  union all select 'crawl_posts', count(*)::int from del_posts
  union all select 'crawl_jobs', count(*)::int from del_jobs
  union all select 'service_tasks', count(*)::int from del_tasks
  union all select 'business', count(*)::int from del_business
  union all select 'clients', count(*)::int from del_clients
) s order by table_name;
