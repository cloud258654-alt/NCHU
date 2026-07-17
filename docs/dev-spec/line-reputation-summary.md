# LINE Reputation Quantitative Report

## Scope

The report reads all rows from `public.reviews_enriched` and returns one global quantitative summary to every LINE user.

This relation is maintained by another team. BI-RMP treats it as read-only and does not manage its structure.

## Flow

```text
LINE webhook
-> verify signature
-> if the event requests crawl status, verify LINE ownership and return progress or a ready report
-> call /api/line/client-recognition to upsert the LINE ID into clients
-> recognize the first active business for that client
-> if no business is found, prepare a LINE notice and use the demo/global fallback
-> if a business is found, create /api/line/reputation-crawler/jobs
-> use Reply API to acknowledge the task and include a status Quick Reply
-> after Reply, call /api/line/reputation-crawler/jobs/{task_id}/run without LINE Push
-> on a later status interaction, call /api/line/reputation-summary only when ready
-> read all reviews_enriched rows
-> group by platform and sentiment
-> calculate risk and coverage metrics
-> return the LINE Flex Message
```

The report itself does not require `business_id`, `business_name`, client recognition, or branch information. The n8n workflow still performs client registration and business recognition before creating a crawler job. For registered businesses, the crawler uses keyword `店家特色`, unlimited lookback, and bounded async PTT, Google Maps, and Threads platform pipelines. PTT and Threads start immediately, while Google Maps source discovery blocks only Google Maps. Google Maps and Threads each have a three-minute crawl budget and use isolated Chromium instances under a two-browser concurrency limit. The initial interaction only acknowledges the durable task. A later user-initiated status interaction supplies a fresh reply token and receives progress or the report. Any business parameters in a report request are ignored for the current report data scope.

The reputation crawler does not change the current quantitative report scope because the report still uses the rows already stored in `reviews_enriched`.

## Source contract

```env
BI_RMP_ENRICHED_REVIEW_TABLE=public.reviews_enriched
```

Required columns:

```text
review_id
platform
sentiment_label
```

Optional fields include `sentiment_score`, `risk_score`, `risk_level`, `rating`, `analyzed_at`, `review_time`, risk flags, emotion scores, and `reviews_tag`.

The response uses the display name `全體評論` and marks `data_contract.report_scope` as `all_rows`.
