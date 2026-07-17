# Merged Function Test Plan

Branch: `integration/bi-rmp-v2-staging-v2`
Observed baseline before Dashboard rebuild: `f6fb7c6`
Purpose: define safe validation steps for the merged Core and rebuilt Dashboard application state.

## Safety Boundaries

Allowed:

- Read code, tests, and documentation.
- Run static checks.
- Run existing automated tests that do not require live external services.
- Validate generated documentation.

Not allowed in this plan without a separate explicit phase:

- Supabase init/link/query.
- Migration or db push.
- Live crawler run.
- ML model load, pickle/joblib load, or ML inference.
- n8n startup or workflow mutation.
- LINE live test.
- Staging or production deployment.
- Merge or push `main`.

## Baseline Commands

Run from repository root `E:\Ai study\NCHU`.

```powershell
git branch --show-current
git status --short --branch
git log --oneline --decorate --graph -8
```

Expected:

```text
branch: integration/bi-rmp-v2-staging-v2
working tree: clean before documentation edits, or only intentional documentation files after edits
HEAD includes: f6fb7c6 docs: add merged function inventory and acceptance plan
```

## Static Inventory Checks

```powershell
Test-Path Backend\api\dashboard.py
Test-Path Backend\tests\api\test_dashboard.py
Test-Path docs\integration\dashboard-read-api.md
Test-Path Frontend
Test-Path apps\dashboard-ml
```

Expected:

```text
Backend/api/dashboard.py: True
Backend/tests/api/test_dashboard.py: True
docs/integration/dashboard-read-api.md: True
Frontend: True
apps/dashboard-ml: True
```

## Test Collection

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected minimum:

```text
298 tests collected
```

Known warning:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

## Full Automated Test Suite

```powershell
.\.venv\Scripts\python.exe -m pytest -q -x
```

Expected minimum:

```text
298 passed, 1 warning
```

Current observed result:

```text
298 passed, 1 warning in 2.88s
```

## Focused Test Groups

Use these when validating a narrower change.

### Staging Database Guard

```powershell
.\.venv\Scripts\python.exe -m pytest Backend\tests\core\test_runtime_staging_guard.py -v
```

Expected:

```text
12 passed
```

### Dashboard Backend API

```powershell
.\.venv\Scripts\python.exe -m pytest Backend\tests\api\test_dashboard.py -v
```

Expected:

```text
15 passed
```

### Core Persistence Shape

```powershell
.\.venv\Scripts\python.exe -m pytest Backend\tests\core\test_supabase_batching.py Backend\tests\test_schema_contract.py -v
```

Expected:

```text
all selected tests pass
```

### Crawler Adapters Without Live Crawling

```powershell
.\.venv\Scripts\python.exe -m pytest Backend\tests\adapters Backend\tests\core\test_source_discovery.py Backend\tests\test_runner_platform_selection.py Backend\tests\test_runner_google_maps_deadline.py -v
```

Expected:

```text
all selected tests pass
```

## Static Security Scans

These scans do not read `.env` files.

```powershell
rg -n "supabase.co/rest/v1|/api/supabase-query|SUPABASE_SERVICE_ROLE_KEY|DATABASE_URL" Frontend Backend docs apps/dashboard-ml -g "!**/.env*"
```

Interpretation:

- Matches in backend server code and docs are expected.
- Matches in `apps/dashboard-ml/tools/validate_dashboard_app.py` are expected because that tool defines the forbidden-token list.
- Matches under `apps/dashboard-ml/frontend` must fail the review unless they are proven false positives.

## Dashboard Frontend Acceptance Plan

The rebuilt Dashboard application lives under `apps/dashboard-ml`.

Required checks:

1. Confirm `apps/dashboard-ml` exists.
2. Confirm frontend has configurable Core API base URL.
3. Confirm frontend does not use direct Supabase REST URLs.
4. Confirm frontend does not reference `DATABASE_URL` or service role keys.
5. Run JS/Python syntax checks appropriate to the rebuilt app.
6. Run UI tests for:
   - loading state
   - empty state
   - error state
   - business filter
   - platform filter
   - pagination
   - review detail
   - 404 detail state
7. Smoke test Dashboard frontend against Core API only.

Current static and independent test commands:

```powershell
.\.venv\Scripts\python.exe -m compileall `
  apps\dashboard-ml\backend `
  apps\dashboard-ml\tests

node --check apps\dashboard-ml\frontend\app.js

.\.venv\Scripts\python.exe -m pytest apps\dashboard-ml\tests -q

.\.venv\Scripts\python.exe apps\dashboard-ml\tools\validate_dashboard_app.py

rg -n `
  "supabase\.co/rest/v1|/api/supabase-query|SUPABASE_SERVICE_ROLE_KEY|DATABASE_URL|mzonkpfagqdhaqwybtuo|ovetahxyihemivnlgqhs" `
  apps\dashboard-ml
```

Observed:

```text
compileall: passed
node --check: passed
Dashboard independent pytest: 6 passed, 1 warning
Dashboard app validation passed
apps/dashboard-ml forbidden-token scan: no matches
```

Current local HTTP smoke commands:

```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/health).StatusCode
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/config).StatusCode
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/dashboard).StatusCode
```

Observed:

```text
/api/health: 200
/api/config: 200
/dashboard: 200
```

## Deferred External Acceptance

These checks require separate explicit approval:

| Area | Deferred validation |
| --- | --- |
| Supabase | init/link/project-ref verification, migration dry-run, db push, live read/write checks |
| Crawlers | live PTT, Google Maps, Threads runs |
| ML | model load/inference beyond deterministic safe text features |
| n8n | workflow startup and authenticated internal API calls |
| LINE | LIFF live login and Messaging API push/reply |
| Deployment | staging and production deploy validation |

## Documentation Validation

```powershell
git diff --check
git status --short --branch
```

Expected after Dashboard rebuild:

```text
git diff --check: exit code 0
git status: apps/dashboard-ml files and intentional docs/integration updates only
```
