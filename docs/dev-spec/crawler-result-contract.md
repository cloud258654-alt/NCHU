# Crawler Result Contract

Crawler adapters return technical status and data-yield fields separately.

## Adapter fields

- `status`: execution state for runner compatibility: `success`, `partial_success`, or `failed`.
- `outcome`: data-aware result: `success_with_data`, `success_no_changes`, `success_no_results`, `blocked`, `partial_success`, or `failed`.
- `technical_success`: true when the adapter completed enough work to classify the crawl result.
- `data_yield_success`: true only when canonical posts or comments were written.
- `cards_found` / `comments_found`: parsed or discovered source-side counts.
- `canonical_posts_written` / `canonical_comments_written`: actual canonical rows written.
- `post_metric_snapshots_written` / `comment_metric_snapshots_written`: metric snapshot rows written.
- `diagnostics`: platform-specific discovery, fetch, parse, filter, delta, and persistence details.

## Runner behavior

`crawl_jobs.total_posts` and `crawl_jobs.total_comments` are actual canonical write counts, not parsed source-side counts.

The runner stores the full adapter summary under:

```text
crawl_jobs.execution_config.result_summary
```

Existing `execution_config` keys such as `query` and `target_url` are preserved by JSONB merge.

Example:

```json
{
  "query": "Example Shop beef soup",
  "target_url": "https://www.google.com/maps/search/Example%20Shop",
  "result_summary": {
    "outcome": "success_no_changes",
    "technical_success": true,
    "data_yield_success": false,
    "discovered_count": 1,
    "fetched_count": 1,
    "parsed_count": 110,
    "matched_count": 0,
    "filtered_count": 110,
    "cards_found": 1,
    "comments_found": 0,
    "canonical_posts_written": 0,
    "canonical_comments_written": 0,
    "post_metric_snapshots_written": 0,
    "comment_metric_snapshots_written": 0,
    "filter_reasons": {
      "outside_lookback": 110
    },
    "error_type": null,
    "error_message": null
  }
}
```

## Outcome definitions

- `success_with_data`: canonical post or comment rows were written.
- `success_no_changes`: crawl found comparable source data, but no canonical writes were needed.
- `success_no_results`: crawl completed but no relevant source data was discovered or parsed.
- `blocked`: crawler hit a login wall, CAPTCHA, restricted content, timeout, or equivalent hard block.
- `partial_success`: part of the pipeline succeeded, but a recoverable stage failed.
- `failed`: crawler or required persistence failed.
