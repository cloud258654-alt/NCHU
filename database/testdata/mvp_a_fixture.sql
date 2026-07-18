-- MVP-A Gate A3 fictional staging fixture.
-- Target project: BI-RMP-V2-STAGING (qlhykeeyjaoikczoambe)
--
-- This script is idempotent for fixture_id=mvp-a-fixture-001.
-- A3 creates raw Dashboard-readable reviews only. ML analysis_results are
-- intentionally left empty for Gate A5.

begin;

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

with
review_fixture as (
  select *
  from (values
    (
      'positive',
      'google_maps',
      'mvp-a-fixture-source-positive-001',
      'mvp-a-fixture-review-positive-001',
      'https://example.test/mvp-a/fixture/reviews/positive-001',
      'A3 正面測試評論',
      'mvp-a-fixture-author-positive',
      'A3 正面測試顧客',
      '服務人員很親切，咖啡很好喝，環境也很乾淨。',
      5.0::numeric,
      12,
      1,
      0,
      40,
      13
    ),
    (
      'general_negative',
      'ptt',
      'mvp-a-fixture-source-negative-001',
      'mvp-a-fixture-review-negative-001',
      'https://example.test/mvp-a/fixture/reviews/negative-001',
      'A3 一般負面測試評論',
      'mvp-a-fixture-author-negative',
      'A3 一般負面測試顧客',
      '等候時間太久，價格有點太貴，希望改善服務速度。',
      2.0::numeric,
      3,
      2,
      0,
      25,
      5
    ),
    (
      'high_risk',
      'threads',
      'mvp-a-fixture-source-high-risk-001',
      'mvp-a-fixture-review-high-risk-001',
      'https://example.test/mvp-a/fixture/reviews/high-risk-001',
      'A3 高風險測試評論',
      'mvp-a-fixture-author-high-risk',
      'A3 高風險測試顧客',
      '多人飲用後身體不適並送醫，請立即安排人工調查。',
      1.0::numeric,
      18,
      4,
      6,
      80,
      28
    )
  ) as rf(
    review_kind, platform, source_external_id, dedupe_key, link, title,
    author_id, author_name, content, rating_value, like_count, comment_count,
    share_count, view_count, reaction_count
  )
),
ins_client as (
  insert into public.clients (
    line_user_id, name, gender, birth_date, phone, email, status
  ) values (
    'mvp-a-fictional-line-user-001',
    'MVP-A Fictional Client',
    'unspecified',
    date '1990-01-01',
    '+886-900-000-001',
    'mvp-a-fixture@example.test',
    'active'
  )
  returning id
),
ins_business as (
  insert into public.business (
    client_id, name, branch_name, industry, address, config, status
  )
  select
    id,
    'MVP 測試咖啡館',
    'A3 Fixture',
    'Fictional Cafe',
    'No. 1, Fixture Road, Staging District, Test City',
    'fixture_id=mvp-a-fixture-001',
    'active'
  from ins_client
  returning id, client_id
),
ins_task as (
  insert into public.service_tasks (
    business_id, service_type, schedule_type, status, config
  )
  select
    id,
    'reputation_monitoring',
    'once',
    'completed',
    '{
      "fixture_id": "mvp-a-fixture-001",
      "mvp_gate": "A3",
      "source": "manual_sql_fixture",
      "channel": "line_bot_fixture",
      "created_by": "n8n_fixture",
      "source_message_id": "mvp-a-fictional-line-message-001",
      "external_crawler_executed": false,
      "external_n8n_executed": false,
      "external_line_call_executed": false
    }'::jsonb
  from ins_business
  returning id, business_id
),
ins_jobs as (
  insert into public.crawl_jobs (
    service_task_id, platform, keyword, status, trigger_source, run_mode,
    execution_config, start_time, end_time, total_posts, total_comments
  )
  select
    st.id,
    rf.platform,
    'mvp-a-fixture-keyword',
    'success',
    'n8n_fixture',
    'manual',
    jsonb_build_object(
      'fixture_id', 'mvp-a-fixture-001',
      'mvp_gate', 'A3',
      'review_kind', rf.review_kind,
      'source_external_id', rf.source_external_id,
      'external_crawler_executed', false,
      'result_summary', jsonb_build_object(
        'outcome', 'fixture_success',
        'data_yield_success', true,
        'cards_found', 1,
        'comments_found', 1,
        'canonical_posts_written', 1,
        'canonical_comments_written', 1,
        'post_metric_snapshots_written', 1,
        'comment_metric_snapshots_written', 1
      )
    ),
    timestamptz '2026-07-18 08:30:00+00',
    timestamptz '2026-07-18 08:31:00+00',
    1,
    1
  from ins_task st
  cross join review_fixture rf
  returning id, service_task_id, platform, execution_config
),
ins_posts as (
  insert into public.crawl_posts (
    crawl_job_id, platform_post_id, link, title, author_id, author_name,
    content, published_at, first_seen_at, last_seen_at, like_count,
    comment_count, share_count, view_count, reaction_count, crawl_count,
    dedupe_key, extra_data
  )
  select
    j.id,
    rf.source_external_id,
    rf.link,
    rf.title,
    rf.author_id,
    rf.author_name,
    rf.content,
    timestamptz '2026-07-18 08:00:00+00',
    timestamptz '2026-07-18 08:30:00+00',
    timestamptz '2026-07-18 08:30:00+00',
    rf.like_count,
    rf.comment_count,
    rf.share_count,
    rf.view_count,
    rf.reaction_count,
    1,
    rf.dedupe_key,
    jsonb_build_object(
      'fixture_id', 'mvp-a-fixture-001',
      'mvp_gate', 'A3',
      'review_kind', rf.review_kind,
      'source_external_id', rf.source_external_id,
      'is_fictional', true
    )
  from ins_jobs j
  join review_fixture rf on rf.review_kind = j.execution_config->>'review_kind'
  returning id, crawl_job_id, dedupe_key
),
ins_comments as (
  insert into public.crawl_comments (
    crawl_post_id, platform_comment_id, author_id, author_name, content,
    published_at, first_seen_at, last_seen_at, like_count, reply_count,
    reaction_count, crawl_count, dedupe_key, extra_data
  )
  select
    p.id,
    rf.source_external_id || '-comment',
    rf.author_id || '-comment',
    rf.author_name || ' comment',
    'A3 fixture supporting comment for ' || rf.review_kind || '.',
    timestamptz '2026-07-18 08:05:00+00',
    timestamptz '2026-07-18 08:30:00+00',
    timestamptz '2026-07-18 08:30:00+00',
    1,
    0,
    1,
    1,
    rf.dedupe_key || '-comment',
    jsonb_build_object(
      'fixture_id', 'mvp-a-fixture-001',
      'mvp_gate', 'A3',
      'review_kind', rf.review_kind,
      'source_external_id', rf.source_external_id || '-comment',
      'is_fictional', true
    )
  from ins_posts p
  join review_fixture rf on rf.dedupe_key = p.dedupe_key
  returning id, crawl_post_id, dedupe_key
),
ins_post_metrics as (
  insert into public.post_metric_snapshots (
    crawl_post_id, like_count, comment_count, share_count, view_count,
    reaction_count, average_rating, rating_count, extra_data, collected_at
  )
  select
    p.id,
    rf.like_count,
    rf.comment_count,
    rf.share_count,
    rf.view_count,
    rf.reaction_count,
    rf.rating_value,
    1,
    jsonb_build_object('fixture_id', 'mvp-a-fixture-001', 'mvp_gate', 'A3', 'review_kind', rf.review_kind),
    timestamptz '2026-07-18 08:31:00+00'
  from ins_posts p
  join review_fixture rf on rf.dedupe_key = p.dedupe_key
  returning id
),
ins_comment_metrics as (
  insert into public.comment_metric_snapshots (
    crawl_comment_id, like_count, reply_count, reaction_count,
    rating_value, collected_at
  )
  select
    c.id,
    1,
    0,
    1,
    rf.rating_value,
    timestamptz '2026-07-18 08:31:00+00'
  from ins_comments c
  join review_fixture rf on rf.dedupe_key || '-comment' = c.dedupe_key
  returning id
),
ins_messages as (
  insert into public.client_messages_log (
    client_id, line_user_id, message_text, direction, intent, session_state
  )
  select
    c.id,
    'mvp-a-fictional-line-user-001',
    'A3 fixture request for MVP 測試咖啡館; no LINE platform call was made.',
    'incoming',
    'mvp_a_fixture_request',
    '{"fixture_id":"mvp-a-fixture-001","mvp_gate":"A3","source":"line_bot_fixture","external_line_call_executed":false}'::jsonb
  from ins_client c
  returning id
),
ins_log as (
  insert into public.crawl_logs (service_task_id, level, message)
  select
    id,
    'INFO',
    'MVP-A fixture inserted without crawler'
  from ins_task
  returning id
)
select
  (select id from ins_client) as client_id,
  (select id from ins_business) as business_id,
  (select id from ins_task) as service_task_id,
  (select count(*) from ins_jobs)::int as crawl_jobs_inserted,
  (select count(*) from ins_posts)::int as dashboard_readable_reviews_inserted,
  (select count(*) from ins_comments)::int as crawl_comments_inserted,
  (select count(*) from ins_post_metrics)::int as post_metric_snapshots_inserted,
  (select count(*) from ins_comment_metrics)::int as comment_metric_snapshots_inserted,
  0::int as analysis_results_inserted,
  (select count(*) from ins_messages)::int as client_messages_inserted,
  (select count(*) from ins_log)::int as crawl_logs_inserted;

commit;
