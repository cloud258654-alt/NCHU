# Google Maps Source Discovery

## Scope

Google Maps source discovery runs only when the selected runner platforms include
`google_maps`. Threads-only and PTT-only runs must not perform Google Maps source
discovery.

Discovery is best-effort and URL-only. Search engine titles are used only for
candidate scoring diagnostics. Search snippets are not saved as Google Maps
review content, and every selected URL is still opened by the Google Maps
crawler before any reviews are parsed.

The discovery flow does not log in to Google, solve CAPTCHA, use stealth
plugins, rotate proxies, or require a Google Maps API key.

## Configuration

```env
GOOGLE_MAPS_DISCOVERY_ENABLED=true
GOOGLE_MAPS_DISCOVERY_ENGINE=auto
GOOGLE_MAPS_DISCOVERY_MAX_RESULTS=10
GOOGLE_MAPS_DISCOVERY_QUERY_VARIANT_LIMIT=4
SEARXNG_BASE_URL=http://localhost:8080
```

Supported `GOOGLE_MAPS_DISCOVERY_ENGINE` values:

- `auto`
- `searxng`
- `duckduckgo`
- `bing`
- `disabled`

For Google Maps, `auto` resolves to `searxng -> duckduckgo -> bing` when
`SEARXNG_BASE_URL` is configured, otherwise `duckduckgo -> bing`. This does not
change Threads discovery engine priority.

## Query Rules

`build_google_maps_discovery_queries(business_name, keyword, location=None)`
builds bounded query variants from the business name and optional location.
The monitoring keyword is included only as a secondary variant and does not
replace the business name.

Example variants:

- `Example Store Taipei site:google.com/maps`
- `Example Store Taipei "ramen" site:google.com/maps`
- `Example Store Taipei Google Maps`
- `Example Store Taipei ramen Google reviews`

## URL Rules

Accepted URL shapes include:

- `https://www.google.com/maps/place/...`
- `https://maps.google.com/...`
- `https://www.google.com.tw/maps/place/...`
- `https://maps.google.com.tw/...`
- `https://www.google.com/maps?cid=...`
- `https://www.google.com/maps?place_id=...`
- `https://www.google.com/maps?query_place_id=...`
- `https://www.google.com/maps/search/?api=1&query=...`

Normalization removes fragments, credentials, tracking parameters, and unrelated
query parameters. Only `api`, `cid`, `place_id`, `query_place_id`, and `query`
are preserved. Taiwan Google Maps hosts are normalized to
`https://www.google.com/maps/...`.

Candidate rejection reasons:

- `empty_url`
- `unsupported_domain`
- `google_homepage`
- `maps_homepage`
- `search_redirect_unresolved`
- `short_redirect_unresolved`
- `not_maps_url`
- `duplicate`
- `low_confidence`
- `accepted`

## Scoring

Candidates are scored without AI:

- `+100` URL contains `/maps/place/`
- `+90` URL contains `cid`
- `+80` URL contains `place_id`
- `+30` title contains the business name
- `+20` title contains the location
- `+10` URL is Google Maps
- `-30` URL is a Maps search URL
- `-100` URL is not an accepted Google Maps URL

The highest scoring accepted candidate is selected. Place URLs normally outrank
search URLs. Discovery stops early only after a high-confidence accepted
candidate is found: `place_url`, `cid_url`, or `place_id_url`. Lower-confidence
accepted candidates such as `search_url` and `maps_url` remain eligible, but do
not prevent trying the next configured engine.

## Fallback

If no accepted candidate is available, or discovery is disabled or times out,
the runner uses a generated Google Maps search URL:

```text
https://www.google.com/maps/search/{business name}
```

When `location` is provided, it is appended to the search term. Generated search
fallback is recorded as:

```text
source = generated_fallback
candidate_type = search_fallback
```

## Deadline

Discovery and the Google Maps crawler share the runner deadline. Discovery uses
the original `--max-minutes` budget. The crawler receives only the remaining
budget after discovery, and is skipped if discovery has already exhausted the
deadline. Each search-engine query uses:

```text
timeout_seconds <= remaining deadline
retry_attempts = 1
```

If the deadline expires before or during engine attempts, discovery still
returns the generated Google Maps search URL fallback.

## Diagnostics

Google Maps source discovery diagnostics include:

- `enabled`
- `engines_attempted`
- `queries`
- `raw_results_seen`
- `accepted_candidates`
- `rejected_candidates`
- `selected_url`
- `selected_source`
- `fallback_used`
- `results`
- `errors`

Each result records the engine, query, raw URL, normalized URL, title, accepted
flag, candidate type, score, and rejection reason. Diagnostics do not include
cookies, credentials, API keys, fragments, or unrelated query parameters.
