begin;

alter table public.clients enable row level security;
alter table public.business enable row level security;
alter table public.service_tasks enable row level security;
alter table public.crawl_jobs enable row level security;
alter table public.crawl_posts enable row level security;
alter table public.crawl_comments enable row level security;
alter table public.post_metric_snapshots enable row level security;
alter table public.comment_metric_snapshots enable row level security;
alter table public.analysis_results enable row level security;
alter table public.reputation_score_snapshots enable row level security;
alter table public.alerts enable row level security;
alter table public.client_messages_log enable row level security;
alter table public.crawl_logs enable row level security;

revoke select, insert, update, delete on table public.clients from anon, authenticated;
revoke select, insert, update, delete on table public.business from anon, authenticated;
revoke select, insert, update, delete on table public.service_tasks from anon, authenticated;
revoke select, insert, update, delete on table public.crawl_jobs from anon, authenticated;
revoke select, insert, update, delete on table public.crawl_posts from anon, authenticated;
revoke select, insert, update, delete on table public.crawl_comments from anon, authenticated;
revoke select, insert, update, delete on table public.post_metric_snapshots from anon, authenticated;
revoke select, insert, update, delete on table public.comment_metric_snapshots from anon, authenticated;
revoke select, insert, update, delete on table public.analysis_results from anon, authenticated;
revoke select, insert, update, delete on table public.reputation_score_snapshots from anon, authenticated;
revoke select, insert, update, delete on table public.alerts from anon, authenticated;
revoke select, insert, update, delete on table public.client_messages_log from anon, authenticated;
revoke select, insert, update, delete on table public.crawl_logs from anon, authenticated;

commit;
