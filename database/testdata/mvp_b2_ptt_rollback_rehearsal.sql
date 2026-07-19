-- MVP-B Gate B2 PTT staging rollback rehearsal.
-- Target project: BI-RMP-V2-STAGING (qlhykeeyjaoikczoambe)
--
-- This script is intentionally transaction-scoped. It proves the B2 fixture can
-- be precisely removed inside the transaction and restored by the final
-- ROLLBACK. Do not replace the final ROLLBACK with COMMIT.

begin;

create temporary table gate_b2_ptt_target on commit drop as
select
  st.id as service_task_id,
  b.id as business_id,
  c.id as client_id,
  cj.id as crawl_job_id,
  cp.id as crawl_post_id
from public.service_tasks st
join public.business b
  on b.id = st.business_id
join public.clients c
  on c.id = b.client_id
join public.crawl_jobs cj
  on cj.service_task_id = st.id
join public.crawl_posts cp
  on cp.crawl_job_id = cj.id
where st.id = 7
  and b.id = 7
  and c.id = 8
  and c.line_user_id = 'default-line-id'
  and lower(b.name) = lower('coffee')
  and cj.id = 15
  and cj.platform = 'ptt'
  and cp.id = 15
  and cp.platform_post_id = 'M.1783265624.A.F68.html'
  and cp.link = 'https://www.ptt.cc/bbs/Food/M.1783265624.A.F68.html'
  and cp.extra_data->>'platform' = 'ptt'
  and cp.dedupe_key is null;

create temporary table gate_b2_ptt_rehearsal_counts (
  phase text not null,
  table_name text not null,
  row_count int not null
) on commit drop;

insert into gate_b2_ptt_rehearsal_counts (phase, table_name, row_count)
select 'before', 'service_tasks', count(*)::int
from public.service_tasks where id in (select service_task_id from gate_b2_ptt_target)
union all
select 'before', 'business', count(*)::int
from public.business where id in (select business_id from gate_b2_ptt_target)
union all
select 'before', 'clients', count(*)::int
from public.clients where id in (select client_id from gate_b2_ptt_target)
union all
select 'before', 'crawl_jobs', count(*)::int
from public.crawl_jobs where id in (select crawl_job_id from gate_b2_ptt_target)
union all
select 'before', 'crawl_posts', count(*)::int
from public.crawl_posts where id in (select crawl_post_id from gate_b2_ptt_target)
union all
select 'before', 'post_metric_snapshots', count(*)::int
from public.post_metric_snapshots where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
union all
select 'before', 'crawl_comments', count(*)::int
from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
union all
select 'before', 'comment_metric_snapshots', count(*)::int
from public.comment_metric_snapshots
where crawl_comment_id in (
  select id from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
)
union all
select 'before', 'crawl_logs', count(*)::int
from public.crawl_logs where service_task_id in (select service_task_id from gate_b2_ptt_target);

with deleted as (
  delete from public.comment_metric_snapshots
  where crawl_comment_id in (
    select id from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
  )
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'comment_metric_snapshots', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_comments
  where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'crawl_comments', count(*)::int from deleted;

with deleted as (
  delete from public.post_metric_snapshots
  where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'post_metric_snapshots', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_posts
  where id in (select crawl_post_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'crawl_posts', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_logs
  where service_task_id in (select service_task_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'crawl_logs', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_jobs
  where id in (select crawl_job_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'crawl_jobs', count(*)::int from deleted;

with deleted as (
  delete from public.service_tasks
  where id in (select service_task_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'service_tasks', count(*)::int from deleted;

with deleted as (
  delete from public.business
  where id in (select business_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'business', count(*)::int from deleted;

with deleted as (
  delete from public.clients
  where id in (select client_id from gate_b2_ptt_target)
  returning id
)
insert into gate_b2_ptt_rehearsal_counts
select 'deleted', 'clients', count(*)::int from deleted;

insert into gate_b2_ptt_rehearsal_counts (phase, table_name, row_count)
select 'after_delete', 'service_tasks', count(*)::int
from public.service_tasks where id in (select service_task_id from gate_b2_ptt_target)
union all
select 'after_delete', 'business', count(*)::int
from public.business where id in (select business_id from gate_b2_ptt_target)
union all
select 'after_delete', 'clients', count(*)::int
from public.clients where id in (select client_id from gate_b2_ptt_target)
union all
select 'after_delete', 'crawl_jobs', count(*)::int
from public.crawl_jobs where id in (select crawl_job_id from gate_b2_ptt_target)
union all
select 'after_delete', 'crawl_posts', count(*)::int
from public.crawl_posts where id in (select crawl_post_id from gate_b2_ptt_target)
union all
select 'after_delete', 'post_metric_snapshots', count(*)::int
from public.post_metric_snapshots where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
union all
select 'after_delete', 'crawl_comments', count(*)::int
from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
union all
select 'after_delete', 'comment_metric_snapshots', count(*)::int
from public.comment_metric_snapshots
where crawl_comment_id in (
  select id from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b2_ptt_target)
)
union all
select 'after_delete', 'crawl_logs', count(*)::int
from public.crawl_logs where service_task_id in (select service_task_id from gate_b2_ptt_target);

select phase, table_name, row_count
from gate_b2_ptt_rehearsal_counts
order by
  case phase when 'before' then 1 when 'deleted' then 2 when 'after_delete' then 3 else 4 end,
  table_name;

rollback;
