# LINE Reputation Summary

## Scope

`POST /api/line/reputation-summary` returns a LINE-ready reputation report for
one registered business. The runtime path reads the BI-RMP canonical tables:

```text
clients.line_user_id
-> business.client_id
-> service_tasks.business_id
-> crawl_jobs.service_task_id
-> crawl_posts.crawl_job_id
-> crawl_comments.crawl_post_id
-> analysis_results.target_type + analysis_results.target_id
```

The endpoint no longer reads `public.reviews_enriched`,
`public.master_reviews_enriched`, or any all-row enriched review relation for
customer reports.

Shared staging can additionally restrict LINE users through
`BI_RMP_LINE_ALLOWED_USER_IDS`. When `APP_ENV=staging` and the allowlist is
non-empty, blocked users receive a fixed public staging message before customer
recognition, task creation, status lookup, or summary generation. The response
does not include the requested LINE user ID, allowlist entries, SQL,
connection strings, Supabase refs, tokens, stack traces, or local paths.

## Flow

```text
LINE webhook
-> verify signature
-> client recognition
-> business ownership
-> reputation crawler task ownership
-> canonical crawl data
-> business-scoped analysis
-> LINE Flex Message
```

The n8n workflow first calls `/api/line/client-recognition`. If no active
business is registered for the LINE user, the backend returns a registration
Flex Message and does not fall back to global report data.

For a registered business, n8n creates a durable crawler job with
`/api/line/reputation-crawler/jobs`, acknowledges the request through LINE
Reply API, and later checks `/api/line/reputation-crawler/jobs/{task_id}/status`
or `/api/line/reputation-crawler/jobs/status/latest`. When the task is completed
or partially completed, n8n calls `/api/line/reputation-summary` with the same
`line_user_id` and the owned `task_id`.

## Request

The path remains:

```http
POST /api/line/reputation-summary
```

Supported request fields are additive to the existing contract:

```json
{
  "line_user_id": "U...",
  "message_text": "查詢進度",
  "business_name": "optional explicit business name",
  "business_id": 123,
  "task_id": 456,
  "webhook_event_id": "optional event id",
  "refresh": false
}
```

`line_user_id` is required. `task_id` is preferred for completed status
reports. When present, it must resolve through `service_tasks.business_id` to a
business owned by the same `clients.line_user_id`; otherwise the API returns a
generic not-found error.

## Response

The response keeps the existing top-level report shape used by LINE Flex
Message generation:

```text
ok
status
business
overview
overall
platforms
data_contract
request
refresh
line_messages
```

`data_contract.report_scope` is now `task` when `task_id` is supplied, or
`business` when the report uses the LINE user's active business. It must not be
`all_rows` on the customer summary runtime path.

Task scope and business scope are intentionally different:

```text
task      Uses service_tasks.id = requested task_id, then crawl_jobs.service_task_id.
business  Uses st.business_id for the verified active business.
```

Task scope is the status-report path used after a crawler job completes or
partially completes. It does not read prior tasks for the same business.

`status` and `overall.data_status` are:

```text
complete     Canonical data exists and no task-level platform failure is known.
partial      Canonical data exists, but one or more task platforms failed.
no_data      The business is valid but has no canonical crawl posts/comments.
no_business  The LINE user has no active business mapping.
```

No-data and no-business responses do not read fixture rows or other businesses.

## Aggregation

Canonical targets are collected separately for posts and comments, then joined
to the latest analysis per `(target_type, target_id)`:

```text
crawl_posts      -> analysis_results.target_type = 'crawl_post'
crawl_comments   -> analysis_results.target_type = 'crawl_comment'
```

Post and comment rows are counted as separate canonical targets. Joins must keep
`target_type` in the analysis key so a post id and comment id with the same
numeric value cannot collide or duplicate counts.

The report groups by `crawl_jobs.platform`, counts positive/neutral/negative
sentiment, tracks unclassified records when no analysis exists, and preserves
available risk metrics. Missing analysis does not become neutral sentiment.

Latest analysis selection uses the newest valid row per
`(target_type, target_id)`, ordered by `analyzed_at DESC, id DESC`. Valid rows
are:

```text
analysis_status = 'completed'
OR legacy rows with analysis_status IS NULL and at least one usable analysis
field such as sentiment, risk_level, summary, risk_score, or risk_points
```

`pending`, `running`, `failed`, `cancelled`, and unknown non-null statuses do
not override a valid older analysis.

Partial status comes from the owned task's `crawl_jobs.status` values. Completed
platform data can still be shown, but the report is marked partial if another
platform failed.

## Legacy Enriched Review Tooling

`BI_RMP_ENRICHED_REVIEW_TABLE` remains only for legacy inspection scripts and
tests around protected enriched review relations. It is not part of the LINE
customer summary runtime path.
