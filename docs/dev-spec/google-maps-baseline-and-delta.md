# Google Maps Baseline and Delta

Google Maps uses per-place baseline detection.

## Baseline mode

A place is in baseline mode when the existing Google review index is available and contains no canonical reviews for that normalized place URL.

Baseline mode imports parsed reviews without applying `--lookback-days`. This prevents a first crawl from parsing old reviews and then writing no usable data.

Tracked diagnostics include:

- `baseline_places`
- `baseline_reviews`
- `reviews_scanned`
- `duplicate_reviews`
- `delta_reviews`

## Incremental mode

A place is in incremental mode when canonical reviews already exist for that normalized place URL.

Incremental mode applies the rolling lookback window and writes only new or changed reviews. Unchanged reviews are counted but not rewritten as comments.

Tracked diagnostics include:

- `incremental_places`
- `reviews_in_window`
- `new_reviews`
- `changed_reviews`
- `changed_content_reviews`
- `changed_metric_reviews`
- `unchanged_reviews`
- `older_reviews_skipped`

## Place persistence

Every fetched place with parsed reviews is eligible for canonical `crawl_posts` persistence, even when there are no delta reviews. The latest producing job is stored in `crawl_posts.crawl_job_id`.

Review comments are written only for baseline, new, changed, or unknown-delta reviews.
