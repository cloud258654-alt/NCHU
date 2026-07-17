# BI-RMP Database Design

## Rule

Store each relationship once.

- `crawl_posts.crawl_job_id` connects canonical content to the current crawl, task, and business.
- `crawl_comments.crawl_post_id` connects comments to their post.
- `post_metric_snapshots.crawl_post_id` connects post history to its post.
- `comment_metric_snapshots.crawl_comment_id` connects comment history to its comment.

The schema does not duplicate `crawl_job_id` in comments or metric snapshots and does not expose `*_with_context` views. Business context is retrieved with explicit joins.

## Business relevance

Crawler discovery may use the business name plus an optional keyword, but persistence requires the normalized business identity to match the selected source or content. A generic keyword match alone is not sufficient.

## Retention

Canonical post/comment rows store the latest state. Metric snapshots preserve time-series values through `collected_at`. Full per-job observation lineage is intentionally out of scope.
