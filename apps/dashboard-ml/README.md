# BI-RMP Dashboard ML

This is a rebuilt Dashboard application for the BI-RMP Core Dashboard read API.

The application is intentionally read-only:

- Frontend requests go through the Core API configured by `BI_RMP_CORE_API_URL`.
- No frontend code talks directly to Supabase.
- No database URL, service role key, or project secret is required by this app.
- No model pickle or joblib artifact is loaded by default.

## Structure

```text
apps/dashboard-ml
├── backend
│   └── app.py
├── frontend
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── ml
│   └── safe_text_features.py
├── models
│   └── .gitkeep
├── prompts
│   └── dashboard-analysis.md
├── streamlit
│   └── README.md
├── tools
│   └── validate_dashboard_app.py
├── .env.example
└── requirements.txt
```

## Run Locally

Install dependencies in the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps\dashboard-ml\requirements.txt
```

Start the Dashboard application:

```powershell
$env:BI_RMP_CORE_API_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m uvicorn backend.app:app `
  --app-dir apps\dashboard-ml `
  --host 127.0.0.1 `
  --port 8010
```

Open:

```text
http://127.0.0.1:8010
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m compileall -q `
  apps\dashboard-ml\backend `
  apps\dashboard-ml\ml `
  apps\dashboard-ml\tools

node --check apps\dashboard-ml\frontend\app.js

.\.venv\Scripts\python.exe apps\dashboard-ml\tools\validate_dashboard_app.py
```

## Core API Contract

The UI consumes these read-only endpoints:

- `GET /api/dashboard/businesses`
- `GET /api/dashboard/summary`
- `GET /api/dashboard/reviews`
- `GET /api/dashboard/reviews/{review_id}`

See `docs/integration/dashboard-read-api.md`.
