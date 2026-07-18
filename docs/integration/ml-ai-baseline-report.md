# Gate 4 ML AI Offline Baseline Report

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

## Scope

This report records the Gate 4 rebuild of a versioned offline analysis baseline service under `apps/dashboard-ml`.

The original `classifier.pkl`, `vectorizer.pkl`, and trusted model source were not available. This phase therefore implements a deterministic rules baseline, not a restoration of the original model.

No Supabase connection, migration, crawler live run, n8n, LINE, Ollama, LLM call, deployment, or `main` branch operation was executed.

## Implemented API

Implemented in `apps/dashboard-ml/backend/app.py` and `apps/dashboard-ml/ml/rules_baseline.py`.

```http
GET  /api/ml/health
GET  /api/ml/info
POST /api/ml/analyze-review
POST /api/ml/analyze-batch
POST /api/ai/suggest-response
```

## Explicit Limits

- This is not the original restored model.
- This is not a production-grade trained machine learning model.
- No trained-model accuracy is claimed.
- No fake pickle or joblib model was created.
- Ollama and other LLM integrations are deferred.
- The response suggestion endpoint uses deterministic templates only.

## Gate 4.2 API Contract Update

`POST /api/ml/analyze-review` now returns the required contract fields:

- `review_id`, `business_id`, `platform`
- `sentiment_label`, `sentiment_score`
- `risk_score`, `risk_level`
- `topics`, `tags`, `response_suggestion`
- `model_name`, `model_version`, `analysis_method`
- `analysis_id`, `analyzed_at`
- `human_review_required`, `limitations`

Canonical values:

- `model_name`: `bi-rmp-rules-baseline`
- `model_version`: `1.1.0`
- `analysis_method`: `rules_baseline`

`risk_score` uses a 0-100 scale:

- `< 33`: `low`
- `>= 33` and `< 66`: `medium`
- `>= 66`: `high`

`response_suggestion` and `POST /api/ai/suggest-response` return deterministic bilingual templates with `en` and `zh_tw` keys.

Traditional Chinese support was added through deterministic phrase matching for service, quality, price, sentiment, and risk signals. This remains a rules baseline and is not a trained multilingual model.

## Gate 4.3 API Contract Update

Gate 4.3 keeps the Gate 4.2 fields and adds explicit critical escalation,
analysis-id format, and response contract metadata.

Canonical values:

- `model_name`: `bi-rmp-rules-baseline`
- `model_version`: `1.2.0`
- `analysis_method`: `rules_baseline`
- `analysis_type`: `review_risk_sentiment`
- `contract_version`: `gate-4.3`

Additive fields on `POST /api/ml/analyze-review`:

- `critical`
- `critical_signals`
- `escalation_level`
- `response_contract`
- `analysis_type`
- `contract_version`

`risk_level` intentionally remains limited to `low`, `medium`, and `high` so
the offline API does not expand beyond the existing `analysis_results` risk
enum. Critical cases are represented by `critical=true` and
`escalation_level=critical`; `/api/ml/info` exposes `critical_gte=90` in the
0-100 risk score scale.

`analysis_id` is deterministic and versioned as
`rules-v{model_version_dash}-{sha256_32}` after whitespace canonicalization.

`POST /api/ai/suggest-response` now returns `analysis_id`, deterministic
`response_id`, `contract_version`, `response_contract`, `response_suggestion`
as an alias of `suggested_response`, and bilingual `en` / `zh_tw` response
objects.

## Validation

```text
Python compile apps/dashboard-ml/backend apps/dashboard-ml/ml apps/dashboard-ml/tests: PASS
Dashboard tests: 25 passed, 1 warning
ML endpoint focused tests: 14 passed, 1 warning
Core regression: 298 passed, 1 warning
JavaScript syntax: PASS
```

## Covered Behavior

- ML health identifies the offline rules baseline.
- ML info disclaims original model restoration and production ML quality.
- Single review analysis returns the Gate 4.3 contract fields plus backward-compatible Gate 4 fields.
- Critical cases are reported with `critical=true`, `critical_signals`, and `escalation_level=critical` while `risk_level` remains `high`.
- Analysis IDs are deterministic after whitespace canonicalization and include the model version in the ID prefix.
- Response suggestion endpoints include response contract metadata and deterministic response IDs.
- Traditional Chinese positive service/quality text is classified by deterministic phrase rules.
- Traditional Chinese risk complaint text requires human review.
- Batch analysis returns item-level output and aggregate sentiment/risk counts.
- Empty batch is rejected.
- AI response suggestion returns deterministic bilingual templates and requires human review.
- Repeated analysis of the same input is deterministic.
- No `.pkl`, `.pickle`, or `.joblib` model artifacts were created.

## Known Limits

- English and Traditional Chinese phrase rules are only a baseline and do not represent trained accuracy.
- Multilingual quality beyond the covered Traditional Chinese phrase cases is not accepted in this phase.
- No writeback to `analysis_results` was attempted.
- No staging data, Auth, RLS, or Supabase integration was verified.
- Model replacement should keep the API contract stable and add model-versioned tests.
