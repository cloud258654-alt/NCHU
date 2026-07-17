# Phase 3 Dashboard ML Import Report

Date: 2026-07-17
Branch: integration/bi-rmp-v2-staging
Repository: cloud258654-alt/NCHU

## Scope

This report records the attempt to restore or import the missing `apps/dashboard-ml` application.

No Supabase connection was made.
No crawler run was executed.
No migration or database command was executed.
No model pickle was executed or imported.
No `.env` file was copied.
No push to `main` was performed.
No source project was modified.
No secret value was read, printed, committed, or documented.

## Preflight

- Phase 2 report exists at `docs/integration/staging-recheck/phase-2-core-ci-report.md`.
- Starting branch: `integration/bi-rmp-v2-staging`.
- Starting `git status --short --branch`: clean.
- `supabase/.temp/project-ref`: absent.
- `docs/AGENT_HANDOFF.md`: absent in this checkout.
- `docs/architecture_review.md`: absent in this checkout.
- `docs/database_execution_runbook.md`: present and reviewed.

## Git History Search

Required commands:

```powershell
git log --all --oneline -- apps/dashboard-ml
git log --all --name-status -- apps/dashboard-ml
```

Observed behavior:

- `git log --all --oneline -- apps/dashboard-ml` failed because a `refs/codex/turn-diffs/...` ref points at a non-commit tree object.
- `git log --all --name-status -- apps/dashboard-ml` returned no matching history.

Follow-up search against formal refs:

```powershell
git log --branches --remotes --oneline -- apps/dashboard-ml
git log --branches --remotes --name-status -- apps/dashboard-ml
```

Result: no output.

Interpretation: no dashboard import commit exists in local branches or remote refs.

Codex temporary refs were also inspected:

```powershell
git ls-tree -r --name-only c42a1d4 -- apps/dashboard-ml
git log --oneline --name-status c42a1d4 -- apps/dashboard-ml
```

Result: no output.

Interpretation: the temporary tree object did not contain `apps/dashboard-ml`.

## Source Project Search

Required source:

```text
D:\group-project-V2-main
```

Result:

```text
Not found
```

Additional read-only checks:

- `D:\BI-RMP-main`: not found
- `E:\group-project-V2-main`: not found
- `E:\BI-RMP-main`: not found
- `E:\Ai study`: no `dashboard-ml`, `group-project-V2-main`, `BI-RMP-main`, or `BI-RMP-V2` source directory found
- `E:\原桌面資料`: no `dashboard-ml`, `group-project-V2-main`, `BI-RMP-main`, or `BI-RMP-V2` source directory found
- `C:\Users\Cloud\Desktop`: no `dashboard-ml`, `group-project-V2-main`, `BI-RMP-main`, or `BI-RMP-V2` source directory found
- `C:\Users\Cloud\Desktop\BI-RMP-V2_STAGING_Codex_Recheck_v2`: contains Phase documents only; no source application directory
- `D:\tmp`: no matching source directory found
- `E:\Temp`: no matching source directory found

Interpretation: the specified read-only source project is unavailable in this environment.

## Required Structure Check

Target path:

```text
apps/dashboard-ml
```

Result:

```text
Absent
```

Because the application could not be recovered from Git history and the specified source project was unavailable, these required paths could not be created from an approved source:

- `apps/dashboard-ml/backend`
- `apps/dashboard-ml/frontend`
- `apps/dashboard-ml/ml`
- `apps/dashboard-ml/models`
- `apps/dashboard-ml/prompts`
- `apps/dashboard-ml/data`
- `apps/dashboard-ml/streamlit`
- `apps/dashboard-ml/tools`
- `apps/dashboard-ml/requirements.txt`
- `apps/dashboard-ml/.env.example`
- `apps/dashboard-ml/README.md`

## Verification

The required verification commands were not runnable because `apps/dashboard-ml` is absent:

```powershell
.\.venv\Scripts\python.exe -m compileall -q `
  apps\dashboard-ml\backend `
  apps\dashboard-ml\ml `
  apps\dashboard-ml\streamlit `
  apps\dashboard-ml\tools

node --check apps\dashboard-ml\frontend\app.js
Get-FileHash apps\dashboard-ml\models\classifier.pkl -Algorithm SHA256
Get-FileHash apps\dashboard-ml\models\vectorizer.pkl -Algorithm SHA256
```

No model pickle was executed.
No model hash could be recorded because the model files were unavailable.

## Old Connection And Secret Scan

The required `git grep` scans against `apps/dashboard-ml` were not runnable because the path is absent:

```powershell
git grep -n "mzonkpfagqdhaqwybtuo" -- apps/dashboard-ml
git grep -n "ovetahxyihemivnlgqhs" -- apps/dashboard-ml
git grep -n "supabase.co/rest/v1" -- apps/dashboard-ml/frontend
git grep -n "SUPABASE_SERVICE_ROLE_KEY" -- apps/dashboard-ml/frontend
git grep -n "DATABASE_URL" -- apps/dashboard-ml/frontend
```

No copied dashboard files exist to scan.

## PASS / FAIL

FAIL

Rationale:

- `apps/dashboard-ml` was not present in this checkout.
- No restore commit was found in branches or remote refs.
- The required source project `D:\group-project-V2-main` was not present.
- No approved source was available for a non-destructive import.
- Python/JS syntax checks could not run because the app is absent.
- Model hashes could not be recorded because the model files are absent.

## Blocker

Provide one of the following before rerunning Phase 3:

- Restore or mount the read-only source project at `D:\group-project-V2-main`.
- Provide the exact local path to the read-only source project that contains `dashboard-ml`.
- Provide a branch or commit containing `apps/dashboard-ml`.

Until one of those sources is available, Phase 3 cannot satisfy the restore/import PASS criteria without inventing application contents.
