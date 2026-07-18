# MVP-A Gate A3 Fictional Test Data Report

Date: 2026-07-18

Target project:

- Supabase project: BI-RMP-V2-STAGING
- Project ref: qlhykeeyjaoikczoambe
- Region: ap-northeast-2
- PostgreSQL: 17.6.1.147

## Dashboard Read Source

`GET /api/dashboard/reviews` uses `Backend/api/dashboard.py::DashboardRepository.list_reviews`.

The endpoint reads Dashboard-visible reviews from this SQL path:

```text
crawl_posts cp
JOIN crawl_jobs cj ON cj.id = cp.crawl_job_id
JOIN service_tasks st ON st.id = cj.service_task_id
JOIN business b ON b.id = st.business_id
LEFT JOIN latest crawl_post analysis_results
```

No view is used for `/api/dashboard/reviews`. Gate A3 therefore validates the same join path, not a raw `crawl_posts` count.

## Scope

Gate A3 creates one staging-only, fictional, removable raw-review fixture.

The final fixture intentionally does not create ML output:

- `analysis_results`: 0
- fixture alerts: 0
- fixture reputation score snapshots: 0

A5 is responsible for ML execution and for creating three analysis results.

The fixture business is:

- `MVP 測試咖啡館`

The three Dashboard-readable review texts are:

- Positive: `服務人員很親切，咖啡很好喝，環境也很乾淨。`
- General negative: `等候時間太久，價格有點太貴，希望改善服務速度。`
- High risk: `多人飲用後身體不適並送醫，請立即安排人工調查。`

No real crawler, n8n, LINE, ML, Ollama, external AI, deployment, main merge, or old Supabase operation was executed.

## Files

- Apply fixture: `database/testdata/mvp_a_fixture.sql`
- Remove fixture: `database/testdata/mvp_a_fixture_rollback.sql`

Both scripts are idempotent for `fixture_id=mvp-a-fixture-001`. The apply script first runs the rollback CTE, then inserts the fixture in a separate statement inside one transaction.

## Final Row Counts

| Check | Result |
| --- | ---: |
| Business count | 1 |
| Dashboard-readable review count | 3 |
| Analysis result count | 0 |
| Duplicate review count | 0 |
| Relationship violation count | 0 |
| Cross-business record count | 0 |

Supporting fixture rows after second apply:

| Table | Rows |
| --- | ---: |
| clients | 1 |
| business | 1 |
| service_tasks | 1 |
| crawl_jobs | 3 |
| crawl_posts | 3 |
| crawl_comments | 3 |
| post_metric_snapshots | 3 |
| comment_metric_snapshots | 3 |
| analysis_results | 0 |
| alerts | 0 |
| reputation_score_snapshots | 0 |
| client_messages_log | 1 |
| crawl_logs | 1 |

## Dashboard-Readable Reviews

| Kind | Platform | platform_post_id | dedupe_key | Content |
| --- | --- | --- | --- | --- |
| positive | google_maps | `mvp-a-fixture-source-positive-001` | `mvp-a-fixture-review-positive-001` | `服務人員很親切，咖啡很好喝，環境也很乾淨。` |
| general_negative | ptt | `mvp-a-fixture-source-negative-001` | `mvp-a-fixture-review-negative-001` | `等候時間太久，價格有點太貴，希望改善服務速度。` |
| high_risk | threads | `mvp-a-fixture-source-high-risk-001` | `mvp-a-fixture-review-high-risk-001` | `多人飲用後身體不適並送醫，請立即安排人工調查。` |

All three rows belong to the same fixture business and resolve through:

```text
business <- service_tasks <- crawl_jobs <- crawl_posts
```

## Rollback And Idempotency

Rollback: PASS

Rollback was executed first and removed all `fixture_id=mvp-a-fixture-001` records, including prior Gate A3 analysis/alert/reputation rows. A marker cleanup query returned 0 rows across fixture tables after rollback.

Second apply idempotency: PASS

The fixture was applied twice. Final state remained:

- Business count: 1
- Dashboard-readable review count: 3
- Analysis result count: 0
- Duplicate review count: 0
- Relationship violation count: 0
- Cross-business record count: 0

## Security State

The A2.1 closure state remained unchanged after rollback and repeated apply:

- Runtime tables checked: 13
- RLS enabled tables: 13
- Public policies: 0
- anon/authenticated SELECT/INSERT/UPDATE/DELETE grants: 0
