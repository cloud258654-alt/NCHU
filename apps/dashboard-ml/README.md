# BI-RMP Dashboard ML

This is a rebuilt Dashboard application for the BI-RMP Core Dashboard read API.
It is not a restoration of the original Dashboard source and is not claimed to
match the original UI exactly.

The application is intentionally read-only:

- Frontend requests go through the Core API configured by `BI_RMP_CORE_API_URL`.
- No frontend code talks directly to Supabase.
- No database URL, service role key, or project secret is required by this app.
- No model pickle or joblib artifact is loaded by default.
- Gate 4 offline analysis uses deterministic rules only; it is not a restored trained model.

## Structure

```text
apps/dashboard-ml
|-- backend
|   |-- api_server.py
|   `-- app.py
|-- frontend
|   |-- app.js
|   |-- index.html
|   `-- styles.css
|-- ml
|   `-- safe_text_features.py
|-- models
|   `-- .gitkeep
|-- prompts
|   `-- dashboard-analysis.md
|-- streamlit
|   `-- README.md
|-- tests
|   |-- frontend_behavior.test.js
|   |-- test_dashboard_backend.py
|   `-- test_frontend_behavior.py
|-- tools
|   `-- validate_dashboard_app.py
|-- .env.example
`-- requirements.txt
```

## Run Locally

Install dependencies in the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps\dashboard-ml\requirements.txt
```

Start the Dashboard application with an explicit app directory because the
`dashboard-ml` directory name contains a hyphen:

```powershell
$env:BI_RMP_CORE_API_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m uvicorn backend.api_server:app `
  --app-dir apps\dashboard-ml `
  --host 127.0.0.1 `
  --port 8010
```

Open:

```text
http://127.0.0.1:8010/dashboard
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m compileall `
  apps\dashboard-ml\backend `
  apps\dashboard-ml\tests

node --check apps\dashboard-ml\frontend\app.js

.\.venv\Scripts\python.exe -m pytest apps\dashboard-ml\tests -q

.\.venv\Scripts\python.exe apps\dashboard-ml\tools\validate_dashboard_app.py
```

## Offline Analysis API

Gate 4 adds a versioned deterministic baseline API:

- `GET /api/ml/health`
- `GET /api/ml/info`
- `POST /api/ml/analyze-review`
- `POST /api/ml/analyze-batch`
- `POST /api/ai/suggest-response`

This baseline is not the original model, is not production-grade trained ML, and does not claim trained-model accuracy. Response suggestions use deterministic bilingual templates, not Ollama or another LLM.

Canonical Gate 4.3 contract values:

- `model_name`: `bi-rmp-rules-baseline`
- `model_version`: `1.2.0`
- `analysis_method`: `rules_baseline`
- `analysis_type`: `review_risk_sentiment`
- `contract_version`: `gate-4.3`

`POST /api/ml/analyze-review` returns the Gate 4.3 contract fields:

- `review_id`, `business_id`, `platform`
- `sentiment_label`, `sentiment_score`
- `risk_score`, `risk_level`
- `topics`, `tags`, `response_suggestion`
- `model_name`, `model_version`, `analysis_method`, `analysis_type`
- `analysis_id`, `analyzed_at`
- `human_review_required`, `critical`, `critical_signals`, `escalation_level`
- `contract_version`, `response_contract`, `limitations`

`risk_score` uses a 0-100 scale. Values below 33 are `low`, values from 33 to below 66 are `medium`, and values from 66 upward are `high`.

Gate 4.3 keeps the persisted `risk_level` enum limited to `low`, `medium`, and `high`.
Critical events are represented additively through `critical=true`,
`critical_signals`, and `escalation_level=critical`; non-critical escalation
values are `none`, `review`, and `urgent`. `critical_gte` is exposed as 90 in
`/api/ml/info`.

`analysis_id` is deterministic and versioned as
`rules-v{model_version_dash}-{sha256_32}` after canonical whitespace normalization.

`response_suggestion` and `POST /api/ai/suggest-response` return deterministic bilingual response text:

- `en`
- `zh_tw`

`POST /api/ai/suggest-response` also returns `analysis_id`, `response_id`,
`contract_version`, `response_contract`, and a `response_suggestion` alias for
the canonical bilingual response object.

Traditional Chinese support is deterministic phrase matching for baseline service, quality, price, sentiment, and risk signals. It is not a trained multilingual model.

## Core API Contract

The UI consumes these read-only endpoints:

- `GET /api/dashboard/businesses`
- `GET /api/dashboard/summary`
- `GET /api/dashboard/reviews`
- `GET /api/dashboard/reviews/{review_id}`

See `docs/integration/dashboard-read-api.md`.
