# Phase 4 Port Environment And Staging Lock Report

Date: 2026-07-17
Branch: integration/bi-rmp-v2-staging
Repository: cloud258654-alt/NCHU

## Scope

This report records Phase 4 work for fixed ports, environment templates, and BI-RMP-V2-STAGING target locking.

No Supabase link was executed.
No Supabase database connection was made.
No migration or database command was executed.
No crawler run was executed.
No push to `main` was performed.
No real `.env` file was copied or committed.
No secret value was read, printed, committed, or documented.

## Supabase Change Check

Supabase changelog was checked for breaking changes before implementing local staging guards. Relevant current items were Data API exposure default changes and OpenAPI spec access changes. Phase 4 did not change database schema, grants, RLS, GraphQL, or remote Supabase settings.

## Preflight

- Starting branch: `integration/bi-rmp-v2-staging`.
- Starting `git status --short --branch`: clean.
- `supabase/.temp/project-ref`: absent.
- `docs/AGENT_HANDOFF.md`: absent in this checkout.
- `docs/architecture_review.md`: absent in this checkout.
- `docs/database_execution_runbook.md`: present and reviewed.
- Phase 3 status: FAIL/blocker because `apps/dashboard-ml` and its approved source were unavailable.

## Files Changed

- `.env.core.example`
- `.env.dashboard.example`
- `.env.staging.example`
- `.env.n8n.example`
- `.gitignore`
- `Backend/core/runtime_settings.py`
- `Backend/core/supabase.py`
- `Backend/tests/core/test_runtime_staging_guard.py`
- `docs/integration/staging-recheck/phase-4-environment-report.md`

## Environment Templates

Created four commit-safe environment templates:

- `.env.core.example`
- `.env.dashboard.example`
- `.env.staging.example`
- `.env.n8n.example`

The staging template includes the required fixed values:

```env
APP_ENV=staging
DATABASE_TARGET=staging
ALLOW_PRODUCTION_DB=false
ALLOW_DATABASE_WRITES=false
SUPABASE_PROJECT_NAME=BI-RMP-V2-STAGING
SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe
SUPABASE_URL=https://qlhykeeyjaoikczoambe.supabase.co
DATABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SERVICE_ROLE_KEY=
BI_RMP_CORE_API_URL=http://127.0.0.1:8000
DASHBOARD_ML_API_URL=http://127.0.0.1:8010
OLLAMA_BASE_URL=http://127.0.0.1:11434
SEARXNG_BASE_URL=http://127.0.0.1:8080
N8N_HOST_PORT=5678
```

Secret-bearing fields are intentionally blank.

## Fixed Ports

Recorded in templates and runtime settings:

- Core API: `8000`
- Dashboard ML API: `8010`
- n8n: `5678`
- SearXNG: `8080`
- Ollama: `11434`

`Backend/core/runtime_settings.py` now exposes:

- `BI_RMP_CORE_API_URL`, default `http://127.0.0.1:8000`
- `DASHBOARD_ML_API_URL`, default `http://127.0.0.1:8010`
- `OLLAMA_BASE_URL`, default `http://127.0.0.1:11434`
- `SEARXNG_BASE_URL`, default `http://127.0.0.1:8080`
- `N8N_HOST_PORT`, default `5678`

## Git Ignore

Confirmed ignored:

```text
.env.staging
.env.core
.env.dashboard
.env.n8n
supabase/.temp/project-ref
```

Confirmed commit-allowed:

```text
.env.staging.example
.env.core.example
.env.dashboard.example
.env.n8n.example
```

## Staging Guard

Added `Backend/core/runtime_settings.py::validate_staging_database_target()`.

Guard behavior:

- Rejects forbidden old Supabase project refs:
  - `mzonkpfagqdhaqwybtuo`
  - `ovetahxyihemivnlgqhs`
- When `APP_ENV=staging`, requires `SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe`.
- When `APP_ENV=staging`, requires `SUPABASE_URL` and `DATABASE_URL`, when present, to point at `qlhykeeyjaoikczoambe`.
- When `APP_ENV=staging`, rejects `ALLOW_PRODUCTION_DB=true`.
- Error messages use project refs and setting names only; they do not include full `DATABASE_URL` values or passwords.

`Backend/core/supabase.py::get_connection()` now calls the guard before `psycopg2.connect(...)`.

## Dashboard Port And Frontend

`DASHBOARD_ML_API_URL=http://127.0.0.1:8010` was added to environment templates.

Dashboard ML frontend verification could not be completed because `apps/dashboard-ml` is still absent from this checkout. Therefore:

- `apps/dashboard-ml/frontend/app.js`: absent
- `node --check apps/dashboard-ml/frontend/app.js`: not runnable
- No frontend guessing behavior could be inspected or corrected
- No minimal Dashboard ML `/api/health` endpoint was added because the Dashboard ML application itself is unavailable

This remains blocked by Phase 3.

## Supabase Link Read-Only Check

Command:

```powershell
if (Test-Path -LiteralPath 'supabase/.temp/project-ref') { Get-Content -LiteralPath 'supabase/.temp/project-ref' } else { 'ABSENT' }
```

Result:

```text
ABSENT
```

Interpretation: normal; repository is not currently linked. No `supabase link` was executed.

## Tests

Compile:

```powershell
.\.venv\Scripts\python.exe -m compileall -q Backend
```

Result:

```text
PASS
```

Targeted staging guard tests:

```powershell
$env:PYTHONPATH = "$PWD\Backend"
$env:DATABASE_URL = ""
.\.venv\Scripts\python.exe -m pytest Backend\tests\core\test_runtime_staging_guard.py -q
```

Result:

```text
7 passed in 0.13s
```

Full pytest:

```powershell
$env:PYTHONPATH = "$PWD\Backend"
$env:DATABASE_URL = ""
.\.venv\Scripts\python.exe -m pytest -q -x
```

Result:

```text
293 passed, 1 warning in 2.68s
```

Warning:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

## Smoke Tests

Core API server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing
```

Result:

```text
HTTP 200
{"status":"ok"}
```

Dashboard ML API:

```powershell
Invoke-WebRequest http://127.0.0.1:8010/api/health -UseBasicParsing -TimeoutSec 3
```

Result:

```text
Failed: unable to connect to remote server
```

Interpretation: `apps/dashboard-ml` is absent, so there is no Dashboard ML API to run on port `8010`.

## Old Ref And Secret Scan

Command:

```powershell
rg -n "mzonkpfagqdhaqwybtuo|ovetahxyihemivnlgqhs|SUPABASE_SERVICE_ROLE_KEY=.*\S|DATABASE_URL=.*postgres|DATABASE_URL=.*supabase" .env.core.example .env.dashboard.example .env.staging.example .env.n8n.example Backend/core Backend/tests/core
```

Result:

```text
Backend/core/runtime_settings.py contains the two old refs only in BLOCKED_SUPABASE_PROJECT_REFS.
No non-empty DATABASE_URL or SUPABASE_SERVICE_ROLE_KEY value was found in the env templates.
```

## PASS / FAIL

FAIL

Completed:

- Env templates were created without secrets.
- Real env files and Supabase temp files are ignored.
- Staging ref guard was implemented.
- Old Supabase refs are rejected.
- Guard is called before PostgreSQL connection.
- Tests pass.
- Core API on port `8000` passed `/health`.
- No Supabase link, migration, crawler run, or push to `main` was executed.

Blocking failure:

- `apps/dashboard-ml` is absent, so Dashboard ML API cannot run on port `8010`.
- Dashboard ML frontend cannot be inspected for API port guessing.
- The required two-service smoke test cannot pass until Phase 3 is unblocked.

## Required Follow-Up

Restore `apps/dashboard-ml` from an approved source, then rerun Dashboard ML syntax checks and the `8010` `/api/health` smoke test.
