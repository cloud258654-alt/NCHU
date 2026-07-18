# Dashboard Rebuild Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

## Scope

This report records the rebuild of `apps/dashboard-ml` after repeated checks found no trustworthy source for restoring the original Dashboard application.

This is a new Dashboard application built against the existing Core Dashboard read API. It is not a restoration of the original Dashboard source and must not be treated as a UI-identical replacement.

No Supabase connection was made. No migration, db push, crawler, n8n, LINE, staging deployment, production deployment, or `main` push was executed.

## Source Decision

The original `apps/dashboard-ml` could not be recovered from local branches, remote branches, Codex temporary refs, or searched local source directories. The prior Phase 3 report remains the evidence for the failed restore/import attempt.

The approved decision for this phase was to rebuild a new Dashboard application.

## Application Responsibilities

Dashboard backend under `apps/dashboard-ml/backend`:

- Serves `GET /api/health`.
- Serves `GET /api/config` with the configured Core API base URL.
- Serves `GET /config.js` for browser runtime configuration.
- Serves `GET /dashboard` and the static frontend assets.
- Does not connect to Supabase or PostgreSQL.

Dashboard frontend under `apps/dashboard-ml/frontend`:

- Reads Core API configuration from browser runtime config.
- Calls only the Core Dashboard read API.
- Implements loading, empty state, error state, pagination, business filter, platform filter, and review detail behavior.
- Does not directly call Supabase endpoints or use server-side database credentials.

## ML Status

Gate 4 adds an offline deterministic rules baseline under `apps/dashboard-ml/ml`. Gate 4.3 fixes the canonical contract values to `model_name=bi-rmp-rules-baseline`, `model_version=1.2.0`, `analysis_method=rules_baseline`, `analysis_type=review_risk_sentiment`, and `contract_version=gate-4.3`, uses a 0-100 risk score, and returns deterministic bilingual response templates. `risk_level` remains limited to `low`, `medium`, and `high`; critical cases are represented additively through `critical=true`, `critical_signals`, and `escalation_level=critical`, while non-critical escalation uses `none`, `review`, or `urgent`. This is not the original restored model, not production-grade trained machine learning, and no trained-model accuracy is claimed. No pickle or joblib model is loaded or created.

## Validation Results

Python compile:

```text
compileall apps/dashboard-ml/backend apps/dashboard-ml/tests: PASS
```

JavaScript syntax:

```text
node --check apps/dashboard-ml/frontend/app.js: PASS
```

Dashboard independent tests:

```text
26 passed, 1 warning
```

Core regression:

```text
298 passed, 1 warning
```

Short smoke test:

```text
GET /api/health: 200
GET /api/config: 200
GET /dashboard: 200
```

Security scan:

```text
apps/dashboard-ml forbidden Supabase and secret token scan: no matches
```

Gate 3 browser acceptance:

```text
Playwright Chromium acceptance: 5 passed
```

## Known Limits

- This rebuilt UI is not claimed to match the original Dashboard exactly.
- Browser-level functional acceptance against a local fake Core API passed in Gate 3.
- Visual parity with the original Dashboard was not tested and is not claimed.
- Live staging Core API and live staging data were not contacted.
- Supabase initialization, link, migration dry-run, and db push remain separate phases.
- Trained ML model restoration/replacement and LLM integration remain separate phases.
