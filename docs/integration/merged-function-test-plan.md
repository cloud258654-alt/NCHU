# Merged Function Test Plan

Branch: `integration/bi-rmp-v2-staging-v2`
Observed HEAD: `313b289`
Purpose: define safe validation steps for the merged Core and Dashboard backend state.

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
HEAD includes: 313b289 fix: enforce environment-specific database safety guards
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
apps/dashboard-ml: False
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
298 passed, 1 warning in 2.83s
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
rg -n "supabase.co/rest/v1|/api/supabase-query|SUPABASE_SERVICE_ROLE_KEY|DATABASE_URL" Frontend Backend docs -g "!**/.env*"
```

Interpretation:

- Matches in backend server code and docs are expected.
- Dashboard frontend direct Supabase access cannot be fully validated until `apps/dashboard-ml` exists.
- Any match under a future `apps/dashboard-ml/frontend` path must be reviewed and removed unless it is documentation-only.

## Dashboard Frontend Acceptance Plan

This section is blocked until `apps/dashboard-ml` is restored.

Required checks after restore:

1. Confirm `apps/dashboard-ml` exists.
2. Confirm frontend has configurable Core API base URL.
3. Confirm frontend does not use direct Supabase REST URLs.
4. Confirm frontend does not reference `DATABASE_URL` or service role keys.
5. Run JS/Python syntax checks appropriate to the restored app.
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

## Deferred External Acceptance

These checks require separate explicit approval:

| Area | Deferred validation |
| --- | --- |
| Supabase | init/link/project-ref verification, migration dry-run, db push, live read/write checks |
| Crawlers | live PTT, Google Maps, Threads runs |
| ML | model load/inference and Dashboard ML API behavior |
| n8n | workflow startup and authenticated internal API calls |
| LINE | LIFF live login and Messaging API push/reply |
| Deployment | staging and production deploy validation |

## Documentation Validation

```powershell
git diff --check
git status --short --branch
```

Expected after creating the three documentation files:

```text
git diff --check: exit code 0
git status: only docs/integration/merged-function-*.md files are untracked or modified
```
