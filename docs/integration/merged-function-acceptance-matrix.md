# Merged Function Acceptance Matrix

Branch: `integration/bi-rmp-v2-staging-v2`
Observed baseline before Dashboard rebuild: `f6fb7c6`
Baseline test result used for acceptance: `298 passed, 1 warning`.

Status values:

- `IMPLEMENTED_AND_TESTED`: implementation exists and automated tests cover the behavior.
- `IMPLEMENTED_NOT_TESTED`: implementation exists but no direct automated test was found.
- `PARTIAL`: implementation or test coverage exists for part of the behavior, but important acceptance scope is missing.
- `MISSING`: implementation is absent.
- `BLOCKED_EXTERNAL`: behavior depends on an external service or artifact that was intentionally not accessed in this run.

## Core Acceptance Matrix

| # | Function | Status | Acceptance evidence | Risk or gap |
| --- | --- | --- | --- | --- |
| 1 | Client recognition | IMPLEMENTED_AND_TESTED | Route, repository, and 4 API tests exist. | Runtime requires configured PostgreSQL; tests use fakes. |
| 2 | LIFF registration | IMPLEMENTED_AND_TESTED | LIFF config/page/register routes and 9 LIFF tests exist. | Live LINE verification is mocked; user-facing copy needs encoding review. |
| 3 | Business registration | IMPLEMENTED_AND_TESTED | Repository and endpoint path covered by 17 related tests. | Live DB transaction not validated. |
| 4 | Business duplicate check | IMPLEMENTED_AND_TESTED | Duplicate repository and endpoint covered in `test_business.py`. | Live uniqueness depends on database data/collation. |
| 5 | LINE registration notification | IMPLEMENTED_AND_TESTED | Notification service and Flex completion message tests exist. | Live LINE push not executed. |
| 6 | Reputation crawl job | IMPLEMENTED_AND_TESTED | Job create/run/status/latest services covered by 10 tests. | Live crawler and DB task repository not validated against staging. |
| 7 | PTT adapter | IMPLEMENTED_AND_TESTED | Parser, delta, buffer, and snapshot tests exist. | Live PTT crawl not executed. |
| 8 | Google Maps adapter | IMPLEMENTED_AND_TESTED | Google Maps crawler/delta tests exist. | Live Google Maps/Playwright crawl not executed. |
| 9 | Google Maps URL discovery | IMPLEMENTED_AND_TESTED | Source discovery and deadline tests exist. | Live search engine behavior not verified. |
| 10 | Threads adapter | IMPLEMENTED_AND_TESTED | Threads crawler and delta tests exist. | Live Threads session/browser behavior not verified. |
| 11 | Crawl result standardization | IMPLEMENTED_AND_TESTED | Standardization and persistence batching tests exist. | Platform payload drift remains possible. |
| 12 | Supabase/PostgreSQL persistence | IMPLEMENTED_AND_TESTED | Batching, schema, and staging guard tests exist. | No live Supabase connection in this run; writes require explicit `ALLOW_DATABASE_WRITES=true`. |
| 13 | Reviews enriched repository | IMPLEMENTED_AND_TESTED | Contract, aggregation, migration-protection, and script tests exist. | Live `public.reviews_enriched` inspection not executed. |
| 14 | Reputation summary | IMPLEMENTED_AND_TESTED | Summary aggregation tests exist. | Live data quality depends on analysis/enriched rows. |
| 15 | Quantitative report | IMPLEMENTED_AND_TESTED | Quantitative metric and Flex tests exist. | Upstream sentiment/risk quality is outside this acceptance. |
| 16 | LINE Flex message | IMPLEMENTED_AND_TESTED | 11 Flex tests validate structure, metrics, and registration messages. | Live LINE rendering not tested; copy encoding needs review. |
| 17 | Client message log | IMPLEMENTED_AND_TESTED | API tests and schema contract tests exist. | Live DB insert not executed. |
| 18 | n8n internal API authentication | IMPLEMENTED_AND_TESTED | Internal key dependency and n8n workflow tests exist. | Empty `BI_RMP_INTERNAL_API_KEY` disables auth by design; deployment config must set it. |
| 19 | Runner CLI | IMPLEMENTED_AND_TESTED | Parser, defaults, platform selection, and scheduling tests exist. | Live runner not executed. |
| 20 | Health endpoint | IMPLEMENTED_NOT_TESTED | `GET /health` implemented in `Backend/api/main.py`. | No direct unit test currently asserts `{"status": "ok"}`. |

## Dashboard Acceptance Matrix

| # | Function | Status | Acceptance evidence | Risk or gap |
| --- | --- | --- | --- | --- |
| 1 | Businesses API | IMPLEMENTED_AND_TESTED | `GET /api/dashboard/businesses`; `test_dashboard.py`; Dashboard UI business selector behavior test. | No live DB validation. |
| 2 | Summary API | IMPLEMENTED_AND_TESTED | `GET /api/dashboard/summary`; optional `business_id` test; Dashboard UI summary cards. | No live DB validation. |
| 3 | Reviews API | IMPLEMENTED_AND_TESTED | `GET /api/dashboard/reviews`; repository and route tests; Dashboard UI table behavior tests. | Browser E2E against a running Core API is still deferred. |
| 4 | Single review API | IMPLEMENTED_AND_TESTED | `GET /api/dashboard/reviews/{review_id}`; 200/404/invalid ID tests; Dashboard detail 200/404 behavior tests. | Browser E2E remains deferred. |
| 5 | Pagination | IMPLEMENTED_AND_TESTED | `page`, `page_size`, invalid page, cap tests, and Dashboard previous/next behavior test. | Browser E2E is still deferred. |
| 6 | Business filter | IMPLEMENTED_AND_TESTED | `business_id` query tests for summary/reviews and Dashboard business selector. | Ownership authorization is not implemented in Dashboard API. |
| 7 | Platform filter | IMPLEMENTED_AND_TESTED | `platform` query, parameterized repository tests, and Dashboard platform selector. | Browser E2E is still deferred. |
| 8 | Empty state | IMPLEMENTED_AND_TESTED | Dashboard UI renders an empty review state when no items are returned. | No live staging data scenario was executed. |
| 9 | Error state | IMPLEMENTED_AND_TESTED | Backend sanitized 503 tests and Dashboard UI error banner exist. | No live outage scenario was executed. |
| 10 | Dashboard frontend | IMPLEMENTED_AND_TESTED | `apps/dashboard-ml/frontend` rebuilt; `/dashboard`, static JS/CSS, JS syntax, and behavior tests pass. | Not claimed to match the original Dashboard UI exactly. |
| 11 | Frontend Core API integration | IMPLEMENTED_AND_TESTED | `/api/config` serves `BI_RMP_CORE_API_URL`; frontend behavior tests verify Core API calls. | Requires staging Core API URL at runtime. |
| 12 | Direct Supabase access removal | IMPLEMENTED_AND_TESTED | Forbidden-token scan against `apps/dashboard-ml` returned no matches; frontend behavior tests verify no direct Supabase calls. | Future frontend changes must keep the scan passing. |

## Current Acceptance Conclusion

```text
Core backend: accepted at automated-test level
Dashboard backend API: accepted at automated-test level
Dashboard frontend: accepted at static, syntax, independent behavior-test, and local smoke-test level
Staging database behavior: not accepted live, intentionally not connected
Deployment readiness: not accepted, deployment not in scope
```

## Blocking Gaps Before Full Staging Acceptance

1. Run Dashboard frontend browser E2E tests with a real browser.
2. Smoke test the rebuilt Dashboard against a running staging Core API.
3. Keep Supabase initialization/link/migration/db push in a separate explicit phase.
4. Keep ML model loading/inference in a separate explicit phase.
