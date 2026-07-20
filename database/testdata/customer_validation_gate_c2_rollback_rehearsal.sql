-- Customer Validation Gate C2 rollback rehearsal.
-- This script verifies delete ordering for C2 test data and intentionally rolls back.
-- Replace the label value at execution time with the exact C2-E2E-TEST timestamp label.

BEGIN;

WITH target_business AS (
    SELECT b.id AS business_id, b.client_id
    FROM business b
    WHERE b.name LIKE 'C2-E2E-TEST-%'
),
target_tasks AS (
    SELECT st.id AS task_id
    FROM service_tasks st
    JOIN target_business tb ON tb.business_id = st.business_id
),
target_jobs AS (
    SELECT cj.id AS crawl_job_id
    FROM crawl_jobs cj
    JOIN target_tasks tt ON tt.task_id = cj.service_task_id
),
target_posts AS (
    SELECT cp.id AS crawl_post_id
    FROM crawl_posts cp
    JOIN target_jobs tj ON tj.crawl_job_id = cp.crawl_job_id
),
target_comments AS (
    SELECT cc.id AS crawl_comment_id
    FROM crawl_comments cc
    JOIN target_posts tp ON tp.crawl_post_id = cc.crawl_post_id
),
before_counts AS (
    SELECT 'clients' AS table_name, COUNT(*)::integer AS count
    FROM clients c
    WHERE c.id IN (SELECT client_id FROM target_business)
    UNION ALL
    SELECT 'business', COUNT(*)::integer FROM target_business
    UNION ALL
    SELECT 'service_tasks', COUNT(*)::integer FROM target_tasks
    UNION ALL
    SELECT 'crawl_jobs', COUNT(*)::integer FROM target_jobs
    UNION ALL
    SELECT 'crawl_posts', COUNT(*)::integer FROM target_posts
    UNION ALL
    SELECT 'crawl_comments', COUNT(*)::integer FROM target_comments
    UNION ALL
    SELECT 'analysis_results', COUNT(*)::integer
    FROM analysis_results ar
    WHERE (
        ar.target_type = 'crawl_post'
        AND ar.target_id IN (SELECT crawl_post_id FROM target_posts)
    ) OR (
        ar.target_type = 'crawl_comment'
        AND ar.target_id IN (SELECT crawl_comment_id FROM target_comments)
    )
)
SELECT 'before_delete' AS phase, table_name, count
FROM before_counts
ORDER BY table_name;

WITH target_business AS (
    SELECT b.id AS business_id, b.client_id
    FROM business b
    WHERE b.name LIKE 'C2-E2E-TEST-%'
),
target_tasks AS (
    SELECT st.id AS task_id
    FROM service_tasks st
    JOIN target_business tb ON tb.business_id = st.business_id
),
target_jobs AS (
    SELECT cj.id AS crawl_job_id
    FROM crawl_jobs cj
    JOIN target_tasks tt ON tt.task_id = cj.service_task_id
),
target_posts AS (
    SELECT cp.id AS crawl_post_id
    FROM crawl_posts cp
    JOIN target_jobs tj ON tj.crawl_job_id = cp.crawl_job_id
),
target_comments AS (
    SELECT cc.id AS crawl_comment_id
    FROM crawl_comments cc
    JOIN target_posts tp ON tp.crawl_post_id = cc.crawl_post_id
),
delete_comment_analysis AS (
    DELETE FROM analysis_results ar
    USING target_comments tc
    WHERE ar.target_type = 'crawl_comment'
      AND ar.target_id = tc.crawl_comment_id
    RETURNING ar.id
),
delete_post_analysis AS (
    DELETE FROM analysis_results ar
    USING target_posts tp
    WHERE ar.target_type = 'crawl_post'
      AND ar.target_id = tp.crawl_post_id
    RETURNING ar.id
),
delete_comment_metrics AS (
    DELETE FROM comment_metric_snapshots cms
    USING target_comments tc
    WHERE cms.crawl_comment_id = tc.crawl_comment_id
    RETURNING cms.id
),
delete_comments AS (
    DELETE FROM crawl_comments cc
    USING target_comments tc
    WHERE cc.id = tc.crawl_comment_id
    RETURNING cc.id
),
delete_post_metrics AS (
    DELETE FROM post_metric_snapshots pms
    USING target_posts tp
    WHERE pms.crawl_post_id = tp.crawl_post_id
    RETURNING pms.id
),
delete_posts AS (
    DELETE FROM crawl_posts cp
    USING target_posts tp
    WHERE cp.id = tp.crawl_post_id
    RETURNING cp.id
),
delete_jobs AS (
    DELETE FROM crawl_jobs cj
    USING target_jobs tj
    WHERE cj.id = tj.crawl_job_id
    RETURNING cj.id
),
delete_tasks AS (
    DELETE FROM service_tasks st
    USING target_tasks tt
    WHERE st.id = tt.task_id
    RETURNING st.id
),
delete_business AS (
    DELETE FROM business b
    USING target_business tb
    WHERE b.id = tb.business_id
    RETURNING b.id
)
SELECT 'after_delete' AS phase, table_name, count
FROM (
    SELECT 'analysis_results' AS table_name, COUNT(*)::integer AS count
    FROM delete_comment_analysis
    UNION ALL
    SELECT 'analysis_results', COUNT(*)::integer FROM delete_post_analysis
    UNION ALL
    SELECT 'comment_metric_snapshots', COUNT(*)::integer FROM delete_comment_metrics
    UNION ALL
    SELECT 'crawl_comments', COUNT(*)::integer FROM delete_comments
    UNION ALL
    SELECT 'post_metric_snapshots', COUNT(*)::integer FROM delete_post_metrics
    UNION ALL
    SELECT 'crawl_posts', COUNT(*)::integer FROM delete_posts
    UNION ALL
    SELECT 'crawl_jobs', COUNT(*)::integer FROM delete_jobs
    UNION ALL
    SELECT 'service_tasks', COUNT(*)::integer FROM delete_tasks
    UNION ALL
    SELECT 'business', COUNT(*)::integer FROM delete_business
) counts
ORDER BY table_name;

ROLLBACK;
