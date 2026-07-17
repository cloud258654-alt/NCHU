# Crawler Diagnostics

Diagnostics are intended to explain zero-yield and blocked crawls without treating all technical completions as data success.

## Common counters

- `discovered_count`: source candidates or cards discovered.
- `fetched_count`: source items fetched or scanned.
- `parsed_count`: parsed records or reviews.
- `matched_count`: records that matched the active window or query.
- `filtered_count`: records filtered out.
- `filter_reasons`: grouped filter counters such as `outside_lookback` and `unknown_time`.

## PTT

PTT reports discovery, fetch, cache, parse, filter, buffer, and rolling-delta sections.

Zero-yield classifications:

- `fetch_zero_yield`: article URLs existed but fetches produced no successful article responses.
- `parser_zero_yield`: fetches completed but parser produced no valid article payloads.
- `empty_result`: discovery, parsing, and filters produced no posts.

## Threads

Threads reports rolling-delta counters and discovered pre-cap counts.

Expected blocked conditions include login wall, CAPTCHA, unusual traffic, and restricted content. These must not be reported as `success_no_results`.

When selector zero-yield or block detection occurs, Threads writes local debug artifacts under:

```text
debug/threads/<crawl_job_id>/
```

The directory contains:

- `screenshot.png`
- `page.html`
- `diagnostics.json`

`diagnostics.json` contains:

- `page_title`
- `current_url`
- `body_text_sample`, capped at 2,000 characters
- `login_wall_detected`
- `captcha_detected`
- `restricted_detected`
- `selector_counts.article`
- `selector_counts.post_links`
- `selector_counts.known_containers`

The repository ignores `debug/`.

## Persistence

Persistence details are returned under `persistence.stages`, with row attempts and writes for:

- canonical posts
- canonical comments
- post metric snapshots
- comment metric snapshots
