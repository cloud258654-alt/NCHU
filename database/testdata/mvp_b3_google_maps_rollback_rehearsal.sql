-- MVP-B Gate B3 Google Maps staging rollback rehearsal.
-- Target project: BI-RMP-V2-STAGING (qlhykeeyjaoikczoambe)
--
-- This script is intentionally transaction-scoped. It proves the B3 Google Maps
-- staging data can be precisely removed inside the transaction and restored by
-- the final ROLLBACK. Do not replace the final ROLLBACK with COMMIT.

begin;

create temporary table gate_b3_google_maps_target on commit drop as
select
  b.id as business_id,
  st.id as service_task_id,
  cj.id as crawl_job_id,
  cp.id as crawl_post_id
from public.business b
join public.service_tasks st
  on st.business_id = b.id
join public.crawl_jobs cj
  on cj.service_task_id = st.id
left join public.crawl_posts cp
  on cp.id in (16, 17)
where b.id = 8
  and b.name = 'Starbucks Taipei 101'
  and st.id in (8, 9)
  and cj.id in (16, 17)
  and cj.platform = 'google_maps'
  and (
    cp.id is null
    or (
      cp.crawl_job_id = 17
      and cp.extra_data->>'platform' = 'google_maps'
      and cp.platform_post_id in (
        '0x3442abb6c60c3a53:0xe2139b5525073efd',
        '0x3442abb6da80a7ad:0x8836d2cc0215c472'
      )
      and cp.link in (
        'https://www.google.com/maps/place/Starbucks%E6%98%9F%E5%B7%B4%E5%85%8B+101%E5%85%B8%E8%97%8F%E9%96%80%E5%B8%82/data=!4m7!3m6!1s0x3442abb6c60c3a53:0xe2139b5525073efd!8m2!3d25.0335181!4d121.564232!16s%2Fg%2F11f2w6rh2l!19sChIJUzoMxrarQjQR_T4HJVWbE-I?hl=zh-TW&rclk=1',
        'https://www.google.com/maps/place/STARBUCKS+%E6%98%9F%E5%B7%B4%E5%85%8B+%28101+35F%E9%96%80%E5%B8%82%29/data=!4m7!3m6!1s0x3442abb6da80a7ad:0x8836d2cc0215c472!8m2!3d25.0337009!4d121.5648422!16s%2Fg%2F12hrfl5gt!19sChIJraeA2rarQjQRcsQVAszSNog?hl=zh-TW&rclk=1'
      )
    )
  );

create temporary table gate_b3_google_maps_rehearsal_counts (
  phase text not null,
  table_name text not null,
  row_count int not null
) on commit drop;

insert into gate_b3_google_maps_rehearsal_counts (phase, table_name, row_count)
select 'before', 'business', count(distinct id)::int
from public.business where id in (select business_id from gate_b3_google_maps_target)
union all
select 'before', 'service_tasks', count(distinct id)::int
from public.service_tasks where id in (select service_task_id from gate_b3_google_maps_target)
union all
select 'before', 'crawl_jobs', count(distinct id)::int
from public.crawl_jobs where id in (select crawl_job_id from gate_b3_google_maps_target)
union all
select 'before', 'crawl_posts', count(distinct id)::int
from public.crawl_posts where id in (select crawl_post_id from gate_b3_google_maps_target)
union all
select 'before', 'post_metric_snapshots', count(*)::int
from public.post_metric_snapshots where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
union all
select 'before', 'crawl_comments', count(*)::int
from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
union all
select 'before', 'comment_metric_snapshots', count(*)::int
from public.comment_metric_snapshots
where crawl_comment_id in (
  select id from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
)
union all
select 'before', 'crawl_logs', count(*)::int
from public.crawl_logs where service_task_id in (select service_task_id from gate_b3_google_maps_target);

with deleted as (
  delete from public.comment_metric_snapshots
  where crawl_comment_id in (
    select id from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
  )
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'comment_metric_snapshots', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_comments
  where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'crawl_comments', count(*)::int from deleted;

with deleted as (
  delete from public.post_metric_snapshots
  where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'post_metric_snapshots', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_posts
  where id in (select crawl_post_id from gate_b3_google_maps_target)
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'crawl_posts', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_logs
  where service_task_id in (select service_task_id from gate_b3_google_maps_target)
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'crawl_logs', count(*)::int from deleted;

with deleted as (
  delete from public.crawl_jobs
  where id in (select crawl_job_id from gate_b3_google_maps_target)
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'crawl_jobs', count(*)::int from deleted;

with deleted as (
  delete from public.service_tasks
  where id in (select service_task_id from gate_b3_google_maps_target)
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'service_tasks', count(*)::int from deleted;

with deleted as (
  delete from public.business
  where id in (select business_id from gate_b3_google_maps_target)
  returning id
)
insert into gate_b3_google_maps_rehearsal_counts
select 'deleted', 'business', count(*)::int from deleted;

insert into gate_b3_google_maps_rehearsal_counts (phase, table_name, row_count)
select 'after_delete', 'business', count(distinct id)::int
from public.business where id in (select business_id from gate_b3_google_maps_target)
union all
select 'after_delete', 'service_tasks', count(distinct id)::int
from public.service_tasks where id in (select service_task_id from gate_b3_google_maps_target)
union all
select 'after_delete', 'crawl_jobs', count(distinct id)::int
from public.crawl_jobs where id in (select crawl_job_id from gate_b3_google_maps_target)
union all
select 'after_delete', 'crawl_posts', count(distinct id)::int
from public.crawl_posts where id in (select crawl_post_id from gate_b3_google_maps_target)
union all
select 'after_delete', 'post_metric_snapshots', count(*)::int
from public.post_metric_snapshots where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
union all
select 'after_delete', 'crawl_comments', count(*)::int
from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
union all
select 'after_delete', 'comment_metric_snapshots', count(*)::int
from public.comment_metric_snapshots
where crawl_comment_id in (
  select id from public.crawl_comments where crawl_post_id in (select crawl_post_id from gate_b3_google_maps_target)
)
union all
select 'after_delete', 'crawl_logs', count(*)::int
from public.crawl_logs where service_task_id in (select service_task_id from gate_b3_google_maps_target);

select phase, table_name, row_count
from gate_b3_google_maps_rehearsal_counts
order by
  case phase when 'before' then 1 when 'deleted' then 2 when 'after_delete' then 3 else 4 end,
  table_name;

rollback;
