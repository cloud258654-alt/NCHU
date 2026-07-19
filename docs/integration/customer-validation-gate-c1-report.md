# Customer Validation Gate C1 Report

Date: 2026-07-20 (Asia/Taipei workspace date)

Branch: `feature/customer-validation-gate-c1`

Baseline commit: `63ae1a958e71e84869a1b99721da3cf06a6a238a`
(`63ae1a9 docs: record mvp b3 google maps staging validation`)

## Scope

This change updates the LINE reputation summary runtime path so customer
reports are generated from BI-RMP canonical crawl tables, not the legacy
all-row enriched review relation.

Changed files:

```text
.env.example
Backend/api/main.py
Backend/api/models.py
Backend/api/quantitative_report.py
Backend/api/reputation.py
Backend/api/line_flex.py
Backend/tests/api/test_reputation_customer_gate_c1.py
docs/dev-spec/line-reputation-summary.md
docs/dev-spec/n8n-line-integration.md
docs/integration/merged-function-inventory.md
docs/integration/customer-validation-gate-c1-report.md
infra/n8n/workflows/reputation-optimization-flow.json
```

## Original Problem

`POST /api/line/reputation-summary` previously resolved a global
`ReviewsEnrichedRepository` report, ignored customer ownership for the report
data source, and marked `data_contract.report_scope` as `all_rows`. That was
not sufficient for registered customer validation or tenant isolation.

## Ownership And Data Flow

The current LINE summary path validates:

```text
clients.line_user_id
-> business.client_id
-> service_tasks.business_id
-> crawl_jobs.service_task_id
-> crawl_posts.crawl_job_id
-> crawl_comments.crawl_post_id
-> analysis_results.target_type + analysis_results.target_id
```

`task_id` is additive on the summary request. When provided, the backend
resolves the business through `service_tasks` and `clients.line_user_id` before
reading canonical crawl data. Cross-tenant task access returns a generic 404
without exposing the other customer's business name, platform data, or counts.

Task and business report scopes are distinct:

```text
task      The report target CTE contains WHERE st.id = %s and is parameterized
          with the requested task_id.
business  The report target CTE contains WHERE st.business_id = %s and is
          parameterized with the verified business id.
```

For task scope, `crawl_jobs.service_task_id` must resolve from the requested
`service_tasks.id`; previous tasks for the same business are excluded.

Valid analysis predicate:

```text
analysis_status = 'completed'
OR legacy analysis_status IS NULL rows with at least one usable analysis field
```

`pending`, `running`, `failed`, `cancelled`, and unknown non-null statuses are
not selected as latest valid analysis rows.

## API Compatibility

Endpoint path remains:

```text
POST /api/line/reputation-summary
```

Existing fields remain available:

```text
business
overview
overall
platforms
data_contract
request
refresh
line_messages
```

Additive fields:

```text
request.task_id
status
overall.data_status
overall.crawl_status_counts
data_contract.report_scope
data_contract.source_tables
```

`data_contract.report_scope` is now `task` when `task_id` is supplied and
`business` for the active business path. The customer summary runtime path does
not set `all_rows`.

The canonical customer summary route sets:

```text
report_contract.report_type = canonical_reputation_summary
```

The legacy default `reviews_enriched_quantitative` remains only for callers
that do not override `attach_quantitative_metrics()`.

## Review Findings Fixed

1. Task report mixed in other task history.
   Fixed by splitting target CTEs into task and business scopes. Task-scoped
   platform rows and latest summary queries now use `WHERE st.id = %s`.

2. Latest analysis accepted newer invalid rows.
   Fixed by adding a valid-analysis predicate before `DISTINCT ON`, so pending
   or failed rows cannot override a completed or legacy-valid analysis.

3. Canonical response used legacy report type.
   Fixed by parameterizing `attach_quantitative_metrics()` and passing
   `canonical_reputation_summary` from the LINE summary route. Flex message
   generation preserves an existing report type instead of overwriting it.

4. Repository ownership tests did not execute repository behavior.
   Fixed by adding a DB-API execution adapter test harness that runs
   `PostgresReputationRepository` methods against in-memory relational
   fixtures and validates SQL-selected scope, cross-tenant invisibility,
   same-business task isolation, and valid-analysis selection.

5. Final review found that n8n status replies could include raw backend
   `error_message` text in failed, timeout, or cancelled customer messages.
   Fixed by mapping public statuses/error types to fixed LINE messages and by
   adding a workflow behavior test with malicious connection string, stack
   trace, token, password, and service-role payloads.

6. Final review found that repository behavior tests still did not execute
   `crawl_comment` fixtures. Fixed by adding current-task, old-task, and
   cross-tenant comment rows plus comment analysis versions for completed,
   pending, and failed statuses.

## Security Checks

- Summary route no longer imports or wires `ReviewsEnrichedRepository`.
- Customer summary SQL scopes by verified `clients.line_user_id` and either
  requested `service_tasks.id` or verified business id.
- `task_id` resolution is an ownership check, not a post-query Python filter.
- Missing business returns `no_business` without fixture or global data.
- Cross-tenant task lookup returns generic not-found.
- Database unavailable response is sanitized and does not include exception SQL
  or connection details.
- n8n customer-facing status replies do not include raw backend diagnostics.
  Failed, timeout, cancelled, and database-unavailable messages are selected
  from public mapping only.
- No Supabase schema migration, RLS, grants, policies, or production database
  access were performed.

## Focused Tests

Command:

```text
python -m pytest -q Backend\tests\api\test_reputation_customer_gate_c1.py Backend\tests\api\test_reputation_service.py Backend\tests\api\test_reputation_crawl.py Backend\tests\api\test_reputation_crawl_jobs.py Backend\tests\api\test_client_recognition.py Backend\tests\api\test_line_flex.py Backend\tests\test_n8n_zero_push_workflow.py
```

After `/review` fixes, focused tests were run with:

```text
python -m pytest -q Backend\tests\api\test_reputation_customer_gate_c1.py Backend\tests\api\test_reputation_service.py Backend\tests\api\test_reputation_crawl.py Backend\tests\api\test_reputation_crawl_jobs.py Backend\tests\api\test_client_recognition.py Backend\tests\api\test_line_flex.py Backend\tests\api\test_quantitative_report.py Backend\tests\test_n8n_zero_push_workflow.py
```

Result after final review fixes: `59 passed, 1 warning`.

Covered:

```text
business-scoped summary
task ownership and cross-tenant not-found
missing business
no canonical data
post/comment latest-analysis SQL guard
repository SQL behavior adapter
comment repository behavior adapter
task-scoped data excluding prior tasks
latest valid analysis excluding failed/pending rows
latest valid comment analysis excluding failed/pending rows
old-task and cross-tenant comment isolation
n8n malicious status error-message behavior
canonical non-legacy report type
partial platform status
secret-safe 503 response
legacy dependency guard
existing LINE Flex, n8n, client recognition, crawler job/status compatibility
```

## Full Regression

Command:

```text
python -m pytest -q
```

Result after final review fixes: `326 passed, 1 warning`.

The warning is the existing `fastapi.testclient` Starlette deprecation warning.

## Other Validation

```text
python -m compileall -q Backend
```

Result: pass. Docker emitted a local `C:\Users\Cloud\.docker\config.json`
access-denied warning while still returning a valid Compose config.

```text
python -m json.tool infra\n8n\workflows\reputation-optimization-flow.json
python -m json.tool Backend\config\schema_allowlist.json
```

Result: pass.

```text
node -e "...validate workflow jsCode with new Function..."
```

Result: `workflow js ok`.

```text
docker compose --env-file .env.example -f infra\n8n\docker-compose.yml config
```

Result: pass.

```text
git diff --check
```

Result: pass. Git emitted only line-ending warnings for tracked text files.

Repository-wide guard on the production customer summary path found no runtime
dependency on:

```text
public.reviews_enriched
public.master_reviews_enriched
report_scope=all_rows
```

Remaining mentions are limited to negative/current documentation statements,
legacy enriched review tooling, tests for that tooling, protected schema
allowlists, `.env.example` comments/legacy variable, and the
`attach_quantitative_metrics()` legacy default retained for legacy callers.
The canonical route test confirms customer summary responses use
`canonical_reputation_summary`.

## Remaining Risks

- `docs/AGENT_HANDOFF.md` and `docs/architecture_review.md` were required by
  project instructions but do not exist in this checkout.
- The remote branch `feature/customer-validation-gate-c1` did not exist; this
  local branch was created from baseline commit `63ae1a9`.
- Validation was local. Repository behavior is covered by a DB-API execution
  adapter against in-memory relational fixtures, including `crawl_comment`
  rows, but no live Supabase query was executed by requirement.
- `BI_RMP_ENRICHED_REVIEW_TABLE` remains for legacy inspection tooling; it is
  not removed to avoid breaking those explicit legacy tests and scripts.

## Conclusion

RESULT: PASS

Gate C1 passes local validation. The LINE customer summary runtime path is now
business/task scoped over canonical crawl data, task reports do not include
other task history, latest analysis excludes invalid newer rows, the response
uses the canonical report type, and the customer path no longer uses the legacy
all-row enriched review source.
