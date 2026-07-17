# Gate 4.1 ML Baseline Contract Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

## Scope

Gate 4.1 updates the offline deterministic ML baseline contract and adds Traditional Chinese phrase support.

No Supabase connection, database read/write, migration, Ollama, external AI/network call, pickle/joblib artifact, crawler, n8n, LINE, deployment, or `main` branch operation was executed.

## Analyze Review Contract

`POST /api/ml/analyze-review` returns all required fields:

- `review_id`
- `business_id`
- `platform`
- `sentiment_label`
- `sentiment_score`
- `risk_score`
- `risk_level`
- `topics`
- `tags`
- `response_suggestion`
- `model_name`
- `model_version`
- `analysis_method`
- `analysis_id`
- `analyzed_at`
- `human_review_required`
- `limitations`

Backward-compatible Gate 4 fields such as `sentiment`, `categories`, `matched_terms`, `summary`, and `suggested_actions` remain present.

## Traditional Chinese Support

Traditional Chinese support is implemented with deterministic phrase matching for:

- positive sentiment
- negative sentiment
- service topics
- quality topics
- price topics
- risk topics
- human review escalation
- baseline response suggestions

This remains a rules baseline. It is not a trained multilingual model, does not claim trained-model accuracy, and does not restore the unavailable original model.

## Validation

```text
ML focused tests: 12 passed, 1 warning
Dashboard tests: 23 passed, 1 warning
Core regression: 298 passed, 1 warning
Python compile: PASS
JavaScript syntax: PASS
apps/dashboard-ml security scan: no matches
models directory: .gitkeep only
UTF-8 JSON smoke: contract fields present, Traditional Chinese positive case classified as positive/low with service and quality topics
```

## Encoding Note

One manual PowerShell smoke request did not transmit Traditional Chinese text as usable UTF-8 in this terminal session. The same endpoint passed with Python standard-library UTF-8 JSON and with pytest. API clients should send JSON as UTF-8, preferably with `Content-Type: application/json; charset=utf-8`.
