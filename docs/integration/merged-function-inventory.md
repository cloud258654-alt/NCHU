# Merged Function Inventory

Branch: `integration/bi-rmp-v2-staging-v2`
Observed baseline before Dashboard rebuild: `f6fb7c6`
Inventory method: static source, test, document review, rebuilt Dashboard application checks, and local smoke validation.

Not performed in this inventory: Supabase init/link/query, migration, db push, live crawler run, ML model load/inference, n8n startup, LINE live test, deployment, main merge, or main push.

## Repository State Summary

| Item | Observation |
| --- | --- |
| Core API | Present under `Backend/api` |
| Runner CLI | Present at `Backend/runner.py` |
| Platform adapters | Present under `Backend/adapters` for PTT, Google Maps, Threads, and web crawl4ai |
| Dashboard backend read API | Present at `Backend/api/dashboard.py` |
| Dashboard frontend app | Present under `apps/dashboard-ml` as a rebuilt read-only Dashboard application; not a restored original UI |
| Existing frontend | Present: `Frontend/register/index.html`, LIFF registration page only |
| Dashboard API contract doc | Present: `docs/integration/dashboard-read-api.md` |
| Supabase local project folder | Not used in this inventory |

## Core Function Inventory

| # | Function | Implementation files | API route or CLI | Related tests | Static test count |
| --- | --- | --- | --- | --- | ---: |
| 1 | Client recognition | `Backend/api/client_recognition.py`, `Backend/api/main.py`, `Backend/api/line_flex.py` | `POST /api/line/client-recognition` | `Backend/tests/api/test_client_recognition.py` | 4 |
| 2 | LIFF registration | `Backend/api/liff_registration.py`, `Backend/api/main.py`, `Frontend/register/index.html`, `Backend/api/business.py` | `GET /register`, `GET /api/liff/config`, `POST /api/liff/business/register` | `Backend/tests/api/test_liff_registration.py` | 9 |
| 3 | Business registration | `Backend/api/business.py`, `Backend/api/main.py` | `POST /api/liff/business/register` | `Backend/tests/api/test_business.py`, `Backend/tests/api/test_liff_registration.py` | 17 |
| 4 | Business duplicate check | `Backend/api/business.py`, `Backend/api/main.py` | `POST /api/line/business/check-duplicate` | `Backend/tests/api/test_business.py` | 8 |
| 5 | LINE registration notification | `Backend/api/line_registration_notification.py`, `Backend/api/line_flex.py`, `Backend/api/main.py` | Called after LIFF registration | `Backend/tests/api/test_line_registration_notification.py`, `Backend/tests/api/test_line_flex.py` | 4 |
| 6 | Reputation crawl job | `Backend/api/reputation_crawl.py`, `Backend/api/main.py`, `Backend/core/task_repositories.py`, `Backend/runner.py` | `POST /api/line/reputation-crawler/jobs`, `/run`, `/status`, `/status/latest` | `Backend/tests/api/test_reputation_crawl.py`, `Backend/tests/api/test_reputation_crawl_jobs.py` | 10 |
| 7 | PTT adapter | `Backend/adapters/ptt/crawler.py`, `parser.py`, `delta.py`, `local_buffer.py`, `snapshot.py` | `Backend/runner.py --platform ptt` | `Backend/tests/adapters/test_ptt_parser.py`, `test_ptt_delta.py`, `test_ptt_local_buffer.py`, `test_ptt_snapshot.py` | 21 |
| 8 | Google Maps adapter | `Backend/adapters/google_maps/crawler.py`, `delta.py`, `snapshot.py`, `crawl4ai_snapshot.py` | `Backend/runner.py --platform google_maps` | `Backend/tests/adapters/test_google_maps_crawler.py`, `test_google_maps_delta.py` | 19 |
| 9 | Google Maps URL discovery | `Backend/core/source_discovery.py`, `Backend/runner.py` | Runner preflight for Google Maps | `Backend/tests/core/test_source_discovery.py`, `Backend/tests/test_runner_google_maps_deadline.py` | 7 |
| 10 | Threads adapter | `Backend/adapters/threads/crawler.py`, `delta.py` | `Backend/runner.py --platform threads` | `Backend/tests/adapters/test_threads_crawler.py`, `test_threads_delta.py` | 12 |
| 11 | Crawl result standardization | `Backend/core/crawled_post_models.py`, `Backend/core/supabase.py` | Internal normalization layer | `Backend/tests/core/test_crawled_post_models.py`, `Backend/tests/core/test_supabase_batching.py` | 12 |
| 12 | Supabase/PostgreSQL persistence | `Backend/core/supabase.py`, `Backend/core/runtime_settings.py`, `Backend/core/task_repositories.py`, `database/schema.sql` | Internal persistence layer | `Backend/tests/core/test_supabase_batching.py`, `Backend/tests/core/test_runtime_staging_guard.py`, schema contract tests | 26 |
| 13 | Reviews enriched repository | `Backend/api/reviews_enriched.py`, `Backend/api/enriched_reputation.py`, inspection scripts | Used by `POST /api/line/reputation-summary` | `Backend/tests/api/test_reviews_enriched_repository.py`, `test_enriched_reputation.py`, `Backend/tests/database/test_reviews_enriched_migration.py`, script tests | 17 |
| 14 | Reputation summary | `Backend/api/reputation.py`, `Backend/api/enriched_reputation.py`, `Backend/api/main.py` | `POST /api/line/reputation-summary` | `Backend/tests/api/test_reputation_service.py`, `Backend/tests/api/test_enriched_reputation.py` | 4 |
| 15 | Quantitative report | `Backend/api/quantitative_report.py`, `Backend/api/line_flex.py` | Attached to reputation summary response | `Backend/tests/api/test_quantitative_report.py`, `Backend/tests/api/test_line_flex.py` | 13 |
| 16 | LINE Flex message | `Backend/api/line_flex.py` | Returned/sent by LINE API flows | `Backend/tests/api/test_line_flex.py` | 11 |
| 17 | Client message log | `Backend/api/client_messages_log.py`, `Backend/api/main.py`, `database/schema.sql` | `POST /api/line/messages/log` | `Backend/tests/api/test_client_messages_log.py`, schema contract tests | 10 |
| 18 | n8n internal API authentication | `Backend/api/main.py`, `infra/n8n/workflows/reputation-optimization-flow.json` | `X-BI-RMP-API-Key` dependency on internal routes | `Backend/tests/test_n8n_zero_push_workflow.py`, selected API auth tests | 5 |
| 19 | Runner CLI | `Backend/runner.py`, `Backend/core/cli.py`, `Backend/adapters/registry.py` | `python Backend/runner.py --business-name ... --platform ... --dry-run` | `Backend/tests/core/test_rolling_delta_cli.py`, `Backend/tests/test_runner_platform_selection.py`, `Backend/tests/test_runner_google_maps_deadline.py` | 17 |
| 20 | Health endpoint | `Backend/api/main.py` | `GET /health` | No direct unit test found | 0 |

## Dashboard Function Inventory

Dashboard backend API exists. Dashboard frontend application has been rebuilt under `apps/dashboard-ml`.

| # | Function | Implementation files | API route or UI | Related tests | Static test count |
| --- | --- | --- | --- | --- | ---: |
| 1 | Businesses API | `Backend/api/dashboard.py`, `Backend/api/main.py` | `GET /api/dashboard/businesses` | `Backend/tests/api/test_dashboard.py` | 15 |
| 2 | Summary API | `Backend/api/dashboard.py`, `Backend/api/main.py` | `GET /api/dashboard/summary?business_id=` | `Backend/tests/api/test_dashboard.py` | 15 |
| 3 | Reviews API | `Backend/api/dashboard.py`, `Backend/api/main.py` | `GET /api/dashboard/reviews` | `Backend/tests/api/test_dashboard.py` | 15 |
| 4 | Single review API | `Backend/api/dashboard.py`, `Backend/api/main.py` | `GET /api/dashboard/reviews/{review_id}` | `Backend/tests/api/test_dashboard.py` | 15 |
| 5 | Pagination | `Backend/api/dashboard.py` | `page`, `page_size` query params | `Backend/tests/api/test_dashboard.py` | 3 |
| 6 | Business filter | `Backend/api/dashboard.py` | `business_id` query param | `Backend/tests/api/test_dashboard.py` | 2 |
| 7 | Platform filter | `Backend/api/dashboard.py` | `platform` query param | `Backend/tests/api/test_dashboard.py` | 2 |
| 8 | Empty state | `apps/dashboard-ml/frontend/app.js`, `index.html` | Dashboard UI empty review state | `apps/dashboard-ml/tests/frontend_behavior.test.js` | 1 |
| 9 | Error state | `Backend/api/dashboard.py`, `apps/dashboard-ml/frontend/app.js` | Sanitized 503 backend responses and Dashboard UI error banner | `Backend/tests/api/test_dashboard.py`, Dashboard frontend behavior tests | 3 |
| 10 | Dashboard frontend | `apps/dashboard-ml/frontend/index.html`, `app.js`, `styles.css` | `GET /dashboard`, static JS/CSS | `apps/dashboard-ml/tests/test_dashboard_backend.py`, `node --check`, app validation tool | 4 |
| 11 | Frontend Core API integration | `apps/dashboard-ml/backend/app.py`, `apps/dashboard-ml/frontend/app.js` | `GET /api/config`; Core API HTTP client | Dashboard backend and frontend behavior tests | 4 |
| 12 | Direct Supabase access removal | `apps/dashboard-ml/frontend`, `apps/dashboard-ml/tools/validate_dashboard_app.py` | Frontend calls Core API only | Forbidden-token scan against `apps/dashboard-ml`; frontend behavior tests | 2 |

## Dashboard Separation

```text
Dashboard backend API: present
Dashboard frontend application: present under apps/dashboard-ml
Frontend Core API integration: implemented through BI_RMP_CORE_API_URL runtime config
Direct Supabase access removal: statically verified for apps/dashboard-ml/frontend
Original Dashboard parity: not claimed; this is a rebuilt application
```
