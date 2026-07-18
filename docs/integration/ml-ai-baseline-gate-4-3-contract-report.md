# Gate 4.3 ML Baseline Contract Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

## Scope

Gate 4.3 completes the local offline ML baseline contract for critical
escalation, deterministic analysis IDs, and response contract metadata.

No Supabase init, login, link, database read/write, migration, crawler, n8n,
LINE, Ollama, external AI/network call, deployment, `main` merge, or push was
executed.

## Preflight

- Current branch: `integration/bi-rmp-v2-staging-v2`
- HEAD: `0e7be19356c28f40cfc58f8786b8d34d12dd29fb`
- Starting working tree: clean
- `docs/database_execution_runbook.md`: present and reviewed
- `docs/AGENT_HANDOFF.md`: absent in this checkout
- `docs/architecture_review.md`: absent in this checkout

## Canonical Contract Values

- `model_name`: `bi-rmp-rules-baseline`
- `model_version`: `1.2.0`
- `analysis_method`: `rules_baseline`
- `analysis_type`: `review_risk_sentiment`
- `contract_version`: `gate-4.3`

## Critical Escalation

`risk_level` intentionally remains limited to:

- `low`
- `medium`
- `high`

This preserves compatibility with the current `analysis_results.risk_level`
schema contract. Critical cases are represented additively:

- `critical`: boolean
- `critical_signals`: matched critical terms
- `escalation_level`: `critical` when critical signals are present

`GET /api/ml/info` exposes:

```json
{"min":0,"max":100,"low_lt":33,"medium_lt":66,"critical_gte":90}
```

## Analysis ID

`analysis_id` is deterministic after whitespace canonicalization and uses:

```text
rules-v{model_version_dash}-{sha256_32}
```

For Gate 4.3, tests assert the concrete format:

```text
rules-v1-2-0-[0-9a-f]{32}
```

## Response Contract

`POST /api/ml/analyze-review`, `POST /api/ml/analyze-batch`, and
`POST /api/ai/suggest-response` expose `response_contract` metadata.

`response_suggestion` remains the canonical bilingual response object:

```json
{"en":"...","zh_tw":"..."}
```

`POST /api/ai/suggest-response` also returns:

- `analysis_id`
- deterministic `response_id`
- `response_suggestion` alias matching `suggested_response`
- `contract_version`
- `response_contract`

## Explicit Limits

- This is not the original restored model.
- This is not production-grade trained ML.
- No trained-model accuracy is claimed.
- No fake pickle or joblib model was created.
- Ollama and other LLM integrations remain deferred.
- No writeback to `analysis_results` was attempted.

## Validation

```text
Python compile apps/dashboard-ml/backend apps/dashboard-ml/ml apps/dashboard-ml/tests: PASS
JavaScript syntax apps/dashboard-ml/frontend/app.js: PASS
Dashboard tests: 25 passed, 1 warning
ML focused tests: 14 passed, 1 warning
Core regression: 298 passed, 1 warning
Dashboard validation tool: PASS
apps/dashboard-ml forbidden-token scan: no matches
```
