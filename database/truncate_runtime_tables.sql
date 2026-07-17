-- Script to clear all runtime tables while preserving schema, indexes, and constraints.
-- Restarts identity/ID sequences back to 1.
BEGIN;

TRUNCATE TABLE 
  client_messages_log,
  alerts,
  reputation_score_snapshots,
  analysis_results,
  comment_metric_snapshots,
  post_metric_snapshots,
  crawl_logs,
  crawl_comments,
  crawl_posts,
  crawl_jobs,
  service_tasks,
  business,
  clients
RESTART IDENTITY CASCADE;

COMMIT;
