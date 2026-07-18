# Dashboard Gate 3 Browser Acceptance Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`
Baseline commit: `f0e78960fb2ec147923e76a90daf6bda3a9bc0e9`

## Scope

Gate 3 validates the rebuilt Dashboard application in a real browser using Playwright Chromium.

This run used only:

- Local Dashboard service
- Local fake Core API
- Fixed fake test data
- Playwright Chromium
- Automated browser tests

This run did not use Supabase, `DATABASE_URL`, service role keys, live crawlers, n8n, LINE, Ollama, ML models, migrations, deployments, or `main`.

## Result

PASS

## Browser Coverage

Implemented in `apps/dashboard-ml/tests/test_dashboard_browser_acceptance.py`.

Covered behavior:

- Dashboard loads at `/dashboard`
- Frontend calls the configured Core API base URL
- Businesses normal state
- Businesses empty state
- Summary normal state
- Summary/Core API unavailable error state
- Reviews normal state
- Reviews empty state
- Pagination
- Business filter
- Platform filter
- Review detail 200 state
- Review detail 404 state
- Browser request log contains no direct Supabase calls

The browser tests use a local fake Core API with fixed fake data. They do not validate live staging data quality.

## Verification

```text
git branch --show-current:
integration/bi-rmp-v2-staging-v2

git status --short --branch before changes:
clean and synchronized with origin/integration/bi-rmp-v2-staging-v2

Playwright Chromium launch:
chromium ok

Dashboard browser acceptance:
5 passed in 11.61s

Dashboard independent tests:
11 passed, 1 warning in 11.37s

Python compile:
PASS

JavaScript syntax:
PASS

Core regression:
298 passed, 1 warning in 2.80s

Security scan:
apps/dashboard-ml forbidden Supabase and secret token scan returned no matches
```

## Known Limits

- This is a rebuilt Dashboard, not the recovered original Dashboard.
- The test does not claim exact visual or behavioral parity with the original UI.
- The fake Core API validates UI behavior and request wiring only.
- Live staging Core API and live Supabase data remain unverified.
- ML inference remains unimplemented and untested.
