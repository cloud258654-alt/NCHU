-- BI-RMP Supabase relationship refactor: minimal latest-state model
-- Generated: 2026-07-13
--
-- Final relationship:
--   business -> service_tasks -> crawl_jobs -> crawl_posts
--   crawl_posts -> crawl_comments
--   crawl_posts -> post_metric_snapshots
--   crawl_comments -> comment_metric_snapshots
--
-- Only crawl_posts stores crawl_job_id. Comments and metric snapshots reach
-- business context through their canonical parent. Metric history uses
-- collected_at and does not retain per-job lineage.
--
-- Deploy the matching Backend/core/supabase.py in the same maintenance window.
-- Stop crawler writes before running this transaction.
--
-- SAFE DEFAULT:
--   This migration never deletes an unresolved canonical post. It rolls back
--   if a post cannot be assigned to a verified crawl_job. The 2026-07-13
--   preflight found crawl_posts.id = 393 unresolved; resolve or export/delete
--   that row before execution.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

LOCK TABLE public.crawl_jobs IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.crawl_posts IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.crawl_comments IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.crawl_post_observations IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.crawl_comment_observations IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.post_metric_snapshots IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.comment_metric_snapshots IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE public.crawl_posts
  ADD COLUMN IF NOT EXISTS crawl_job_id BIGINT;

-- Backfill the post's current producing job from the strongest available
-- latest-state source. Metric crawl_job_id is used only during cutover and is
-- removed later in this transaction.
WITH latest_post_observation AS (
  SELECT DISTINCT ON (observation.crawl_post_id)
    observation.crawl_post_id,
    observation.crawl_job_id
  FROM public.crawl_post_observations AS observation
  ORDER BY observation.crawl_post_id, observation.observed_at DESC, observation.id DESC
)
UPDATE public.crawl_posts AS post
SET crawl_job_id = observation.crawl_job_id
FROM latest_post_observation AS observation
WHERE post.id = observation.crawl_post_id
  AND post.crawl_job_id IS NULL;

WITH latest_post_metric AS (
  SELECT DISTINCT ON (metric.crawl_post_id)
    metric.crawl_post_id,
    metric.crawl_job_id
  FROM public.post_metric_snapshots AS metric
  WHERE metric.crawl_job_id IS NOT NULL
  ORDER BY metric.crawl_post_id, metric.collected_at DESC, metric.id DESC
)
UPDATE public.crawl_posts AS post
SET crawl_job_id = metric.crawl_job_id
FROM latest_post_metric AS metric
WHERE post.id = metric.crawl_post_id
  AND post.crawl_job_id IS NULL;

UPDATE public.crawl_posts
SET crawl_job_id = COALESCE(last_crawl_job_id, first_crawl_job_id)
WHERE crawl_job_id IS NULL;

DO $migration_check$
DECLARE
  unresolved_post_ids TEXT;
  invalid_post_chain_ids TEXT;
BEGIN
  SELECT string_agg(id::TEXT, ', ' ORDER BY id)
  INTO unresolved_post_ids
  FROM public.crawl_posts
  WHERE crawl_job_id IS NULL;

  IF unresolved_post_ids IS NOT NULL THEN
    RAISE EXCEPTION
      'Cannot complete crawl relationship migration. Unresolved crawl_posts ids: %',
      unresolved_post_ids
      USING HINT = 'Export/delete these legacy rows or assign a verified crawl_job_id, then rerun the migration.';
  END IF;

  SELECT string_agg(post.id::TEXT, ', ' ORDER BY post.id)
  INTO invalid_post_chain_ids
  FROM public.crawl_posts AS post
  LEFT JOIN public.crawl_jobs AS job ON job.id = post.crawl_job_id
  LEFT JOIN public.service_tasks AS task ON task.id = job.service_task_id
  LEFT JOIN public.business AS business_row ON business_row.id = task.business_id
  WHERE business_row.id IS NULL;

  IF invalid_post_chain_ids IS NOT NULL THEN
    RAISE EXCEPTION
      'crawl_posts rows do not resolve to a business through job/task: %',
      invalid_post_chain_ids;
  END IF;
END
$migration_check$;

ALTER TABLE public.crawl_posts
  ALTER COLUMN crawl_job_id SET NOT NULL;

ALTER TABLE public.crawl_posts
  ADD CONSTRAINT fk_crawl_posts_crawl_job
  FOREIGN KEY (crawl_job_id)
  REFERENCES public.crawl_jobs(id)
  ON DELETE RESTRICT
  NOT VALID;

ALTER TABLE public.crawl_posts
  VALIDATE CONSTRAINT fk_crawl_posts_crawl_job;

CREATE INDEX idx_crawl_posts_crawl_job_id
  ON public.crawl_posts(crawl_job_id);

DROP VIEW IF EXISTS public.crawl_comments_with_context;
DROP VIEW IF EXISTS public.crawl_posts_with_context;

-- Remove retired endpoint pointers and duplicate job relationships.
ALTER TABLE public.crawl_posts
  DROP COLUMN IF EXISTS first_crawl_job_id,
  DROP COLUMN IF EXISTS last_crawl_job_id;

ALTER TABLE public.crawl_comments
  DROP COLUMN IF EXISTS first_crawl_job_id,
  DROP COLUMN IF EXISTS last_crawl_job_id,
  DROP COLUMN IF EXISTS crawl_job_id;

ALTER TABLE public.post_metric_snapshots
  DROP COLUMN IF EXISTS crawl_job_id;

ALTER TABLE public.comment_metric_snapshots
  DROP COLUMN IF EXISTS crawl_job_id;

DROP TABLE public.crawl_comment_observations;
DROP TABLE public.crawl_post_observations;

COMMENT ON COLUMN public.crawl_posts.crawl_job_id IS
  'The crawl job that produced the current latest state of this canonical post.';

COMMIT;

-- Read-only verification.
SELECT
  COUNT(*) AS total_posts,
  COUNT(*) FILTER (WHERE post.crawl_job_id IS NULL) AS posts_without_job,
  COUNT(*) FILTER (WHERE business_row.id IS NULL) AS posts_without_business
FROM public.crawl_posts AS post
LEFT JOIN public.crawl_jobs AS job ON job.id = post.crawl_job_id
LEFT JOIN public.service_tasks AS task ON task.id = job.service_task_id
LEFT JOIN public.business AS business_row ON business_row.id = task.business_id;

SELECT
  COUNT(*) AS total_comments,
  COUNT(*) FILTER (WHERE post.id IS NULL) AS comments_without_post,
  COUNT(*) FILTER (WHERE business_row.id IS NULL) AS comments_without_business
FROM public.crawl_comments AS comment_row
LEFT JOIN public.crawl_posts AS post ON post.id = comment_row.crawl_post_id
LEFT JOIN public.crawl_jobs AS job ON job.id = post.crawl_job_id
LEFT JOIN public.service_tasks AS task ON task.id = job.service_task_id
LEFT JOIN public.business AS business_row ON business_row.id = task.business_id;

SELECT
  post.id AS crawl_post_id,
  post.crawl_job_id,
  job.service_task_id,
  task.business_id,
  business_row.name AS business_name,
  job.platform,
  job.keyword,
  post.link,
  post.updated_at
FROM public.crawl_posts AS post
JOIN public.crawl_jobs AS job ON job.id = post.crawl_job_id
JOIN public.service_tasks AS task ON task.id = job.service_task_id
JOIN public.business AS business_row ON business_row.id = task.business_id
ORDER BY post.updated_at DESC
LIMIT 20;
