# BI-RMP Schema Spec

Authoritative SQL: `database/schema.sql`.

## Core relationship

```text
clients -> business -> service_tasks -> crawl_jobs -> crawl_posts
                                               crawl_posts -> crawl_comments
                                               crawl_posts -> post_metric_snapshots
                                             crawl_comments -> comment_metric_snapshots
```

Only `crawl_posts` stores `crawl_job_id`. All child data follows its canonical parent:

```text
crawl_comments.crawl_post_id
-> crawl_posts.crawl_job_id
-> crawl_jobs.service_task_id
-> service_tasks.business_id
-> business.name
```

`crawl_posts` is latest-state and upserts by `link`. `crawl_comments` upserts by `dedupe_key`. Metric snapshots are append-only history ordered by `collected_at`; they do not store job IDs.

There are no observation tables or crawler context views. Reporting queries use explicit joins so Supabase exposes one obvious storage table for each entity.

Protected `review%` tables and `master_reviews_enriched` remain outside crawler runtime cleanup.
