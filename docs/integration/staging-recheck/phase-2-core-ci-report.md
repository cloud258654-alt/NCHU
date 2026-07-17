# Phase 2 Core API And CI Baseline Report

Date: 2026-07-17
Branch: integration/bi-rmp-v2-staging
Repository: cloud258654-alt/NCHU

## Scope

This report verifies the Core API, Dashboard backend baseline, test baseline, CI Python setting, and production workflow risk on the staging integration branch.

No Supabase connection was made.
No crawler run was executed.
No migration or database command was executed.
No push to `main` was performed.
No secret value was read, printed, committed, or documented.

## Preflight

- Phase 1 report exists at `docs/integration/staging-recheck/phase-1-git-reconciliation.md`.
- Starting branch: `integration/bi-rmp-v2-staging`.
- Starting `git status --short --branch`: clean.
- `supabase/.temp/project-ref`: absent.
- `docs/AGENT_HANDOFF.md`: absent in this checkout.
- `docs/architecture_review.md`: absent in this checkout.
- `docs/database_execution_runbook.md`: present and reviewed.

## Phase 5 Backend Files

All required files are present:

- `Backend/api/dashboard.py`
- `Backend/api/main.py`
- `Backend/tests/api/test_dashboard.py`
- `docs/integration/phase-5-report.md`

No old local version was used to overwrite the current `9df66d6` dashboard backend test fix.

## Python Environment

The requested interpreter path `.venv\Scripts\python.exe` was absent at the start of Phase 2, so a local `.venv` was created in the repository root.

Initial `pip install -r requirements.txt` failed while downloading `crawl4ai` because of SSL certificate verification failure against the package host. A second install using:

```powershell
.\.venv\Scripts\python.exe -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

completed successfully. This is an environment workaround and should not be copied into CI unless explicitly reviewed.

Local Python version:

```text
Python 3.11.9
```

## Dependency Compatibility Check

Installed package metadata from the local `.venv`:

```text
pytest: version=9.1.1 requires_python=>=3.10
pytest-asyncio: version=1.4.0 requires_python=>=3.10
python-dotenv: version=1.2.2 requires_python=>=3.10
psycopg2-binary: version=2.9.12 requires_python=>=3.9
PyYAML: version=6.0.3 requires_python=>=3.8
playwright: version=1.61.0 requires_python=>=3.10
beautifulsoup4: version=4.15.0 requires_python=>=3.7.0
lxml: version=6.1.1 requires_python=>=3.8
Crawl4AI: version=0.9.2 requires_python=>=3.10
aiohttp: version=3.14.1 requires_python=>=3.10
fastapi: version=0.139.2 requires_python=>=3.10
uvicorn: version=0.51.0 requires_python=>=3.10
tzdata: version=2026.3 requires_python=>=2
```

Interpretation:

- The installed package metadata does not declare an upper Python version bound that excludes Python 3.14.
- Local validation was performed on Python 3.11.9, not Python 3.14.
- Because there is no local Python 3.14 runtime in this checkout, Phase 2 did not prove Python 3.14 CI compatibility.
- Because the tests passed locally and no direct CI failure was reproduced, `.github/workflows/ci.yml` was not modified.

Recommendation:

Use a CI matrix with the local baseline Python and the forward CI target, for example `3.11` and `3.14`, in a later reviewed CI change. This preserves the currently validated local runtime while keeping visibility on Python 3.14.

## Core Compile

Command:

```powershell
.\.venv\Scripts\python.exe -m compileall -q Backend
```

Result:

```text
PASS
```

## Full Pytest

Command:

```powershell
$env:PYTHONPATH = "$PWD\Backend"
$env:DATABASE_URL = ""
.\.venv\Scripts\python.exe -m pytest -q -x
```

Result:

```text
286 passed, 1 warning in 3.29s
```

Warning:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

Baseline comparison: meets the required `286 passed, 1 warning` baseline.

## Runner Help

Command:

```powershell
.\.venv\Scripts\python.exe Backend\runner.py --help
```

Result:

```text
PASS
```

The command displayed CLI usage and exited successfully.

## Dashboard Backend Single-File Test

Command:

```powershell
$env:PYTHONPATH = "$PWD\Backend"
$env:DATABASE_URL = ""
.\.venv\Scripts\python.exe -m pytest Backend\tests\api\test_dashboard.py -v
```

Result:

```text
15 passed, 1 warning in 0.88s
```

Baseline comparison: meets the required `15 passed, 1 warning` dashboard baseline.

## Dashboard Routes

Confirmed GET routes:

```text
/api/dashboard/businesses
/api/dashboard/summary
/api/dashboard/reviews
/api/dashboard/reviews/{review_id}
```

Evidence:

- `Backend/api/dashboard.py` declares four `@router.get(...)` handlers under `/api/dashboard`.
- `Backend/api/main.py` registers the same four Dashboard routes.
- `Backend/tests/api/test_dashboard.py::test_dashboard_routes_are_registered_as_get_only` passed.
- `Backend/tests/api/test_dashboard.py::test_dashboard_mutating_methods_are_not_registered` passed.

No Dashboard POST, PUT, PATCH, or DELETE route was found or added.

## CI Workflow

`.github/workflows/ci.yml` currently uses:

```yaml
python-version: "3.14"
```

Decision:

- No CI file change was made in Phase 2.
- Local tests passed on Python 3.11.9.
- Dependency metadata did not identify a Python 3.14 blocker.
- No direct CI failure was reproduced locally.

Recommended later action:

- Prefer a reviewed matrix such as `3.11` and `3.14`.
- If CI stability is prioritized over forward-version coverage, `3.12` is a conservative alternative.
- Maintaining only `3.14` leaves a gap because the local validated runtime is `3.11.9`.

## Production Workflow Blocker

`.github/workflows/deploy-production.yml` triggers production deploy on:

```yaml
on:
  push:
    branches:
      - main
```

Blocker:

Do not push `main` during staging integration. A push to `main` can trigger the production deployment workflow.

## PASS / FAIL

PASS

Rationale:

- Core compile passed.
- Full pytest met the `286 passed` baseline.
- Dashboard single-file test met the `15 passed` baseline.
- Dashboard routes are correct and GET-only.
- CI Python version was reviewed and left unchanged because no failure was reproduced.
- Production deploy-on-main risk was confirmed and recorded as a blocker.
- No Supabase connection, crawler run, migration, destructive SQL, or push to `main` was executed.
