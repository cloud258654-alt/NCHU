# Gate 4.2 ML Baseline Contract Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

## Scope

Gate 4.2 finalizes the offline deterministic ML baseline contract, risk score scale, and bilingual response shape.

No Supabase connection, database read/write, migration, Ollama, external AI/network call, pickle/joblib artifact, crawler, n8n, LINE, deployment, `main` merge, or `main` push was executed.

## Canonical Contract Values

All ML analysis responses now use:

- `model_name`: `bi-rmp-rules-baseline`
- `model_version`: `1.1.0`
- `analysis_method`: `rules_baseline`

Backward-compatible Gate 4 fields such as `model_kind`, `baseline_version`, `sentiment`, `categories`, `matched_terms`, `summary`, and `suggested_actions` remain present for existing local clients.

## Analyze Review Contract

`POST /api/ml/analyze-review` returns at least:

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

## Risk Scale

`risk_score` is a 0-100 deterministic score.

| Range | `risk_level` |
| --- | --- |
| `0 <= score < 33` | `low` |
| `33 <= score < 66` | `medium` |
| `66 <= score <= 100` | `high` |

`GET /api/ml/info` exposes the scale as:

```json
{"min":0,"max":100,"low_lt":33,"medium_lt":66}
```

## Bilingual Responses

`response_suggestion` and `POST /api/ai/suggest-response` return deterministic response objects:

```json
{"en":"...","zh_tw":"..."}
```

The Traditional Chinese output is generated from fixed templates and phrase rules. It is not produced by an LLM and is not a trained multilingual model output.

## Explicit Limits

- This is not the original restored model.
- This is not production-grade trained ML.
- No trained-model accuracy is claimed.
- No fake pickle or joblib model was created.
- Ollama and other LLM integrations are deferred.
- No writeback to `analysis_results` was attempted.

## Validation

```text
Python compile apps/dashboard-ml/backend apps/dashboard-ml/ml apps/dashboard-ml/tests: PASS
JavaScript syntax apps/dashboard-ml/frontend/app.js: PASS
Dashboard tests: 23 passed, 1 warning
ML focused tests: 12 passed, 1 warning
Core regression: 298 passed, 1 warning
apps/dashboard-ml forbidden-token scan: no matches
models directory: .gitkeep only
HTTP smoke: /api/ml/health 200; /api/ml/info returned canonical values; /api/ml/analyze-review returned negative, risk_score=100.0, risk_level=high, and response keys en/zh_tw for a UTF-8 Traditional Chinese risk case
```
