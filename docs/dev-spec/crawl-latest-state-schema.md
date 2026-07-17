# Minimal Latest-State Crawl Schema

```mermaid
erDiagram
    CLIENTS ||--o{ BUSINESS : owns
    BUSINESS ||--o{ SERVICE_TASKS : configures
    SERVICE_TASKS ||--o{ CRAWL_JOBS : runs
    CRAWL_JOBS ||--o{ CRAWL_POSTS : produces
    CRAWL_POSTS ||--o{ CRAWL_COMMENTS : contains
    CRAWL_POSTS ||--o{ POST_METRIC_SNAPSHOTS : measures
    CRAWL_COMMENTS ||--o{ COMMENT_METRIC_SNAPSHOTS : measures
```

Only `crawl_posts` stores `crawl_job_id`. Comments and metrics resolve business context through their parent. No observation/event table and no context view is part of the runtime schema.

Metric history retains `collected_at`, not job lineage. This keeps the data model consistent with the latest-state decision.
