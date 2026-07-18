# MVP-0 Scope And Acceptance Standard

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`

## Decision

MVP-0 uses a fixed scope from this point forward. The Gate 4.3 ML baseline
lineage is accepted as:

```text
MVP ML Baseline v1.2.0
```

The user-declared local baseline was `f7a3134 fix: finalize gate 4.3 ml
contract`. That commit was later amended in place; the effective repository
HEAD at MVP-0 preflight was:

```text
ddd4f7c fix: finalize gate 4.3 ml contract
```

## Accepted ML Contract

`risk_level` values are fixed:

- `low`
- `medium`
- `high`

Critical escalation is additive and does not expand `risk_level`:

- `critical`: boolean
- `critical_signals`: string array
- `escalation_level`: one of `none`, `review`, `urgent`, or `critical`

`analysis_id` is fixed as:

```text
rules-v1-2-0-{sha256_32}
```

The 32-hex hash length is accepted for MVP-0.

## Non-Blocking For MVP-0

The following items must not block MVP-0 acceptance:

- Adding `critical` to the `risk_level` enum
- Changing SHA-256 IDs from 32 hex to 64 hex
- Idealizing field names
- Dashboard UI polish
- Model accuracy optimization
- Production LLM or Ollama integration
- Additional platform support

Record these items in backlog instead of reopening MVP-0 scope.

## Change Gate

Only P0 and P1 issues may change existing Dashboard or ML code after this
freeze.

P0:

- Secret leakage
- Accidental Production connection
- Data corruption or data loss
- Complete authorization failure

P1:

- Core API cannot start
- Dashboard core workflow cannot operate
- ML endpoint cannot analyze
- Migration cannot create Staging
- Basic data flow cannot complete

All P2 or lower issues go to backlog.

## MVP-0 Acceptance Commands

Allowed local validation commands:

```powershell
git branch --show-current
git status --short --branch
git log --oneline --decorate -6
.\.venv\Scripts\python.exe -m compileall apps\dashboard-ml\backend apps\dashboard-ml\ml apps\dashboard-ml\tests
node --check apps\dashboard-ml\frontend\app.js
.\.venv\Scripts\python.exe -m pytest apps\dashboard-ml\tests -q
.\.venv\Scripts\python.exe -m pytest apps\dashboard-ml\tests\test_ml_offline_baseline.py -q
.\.venv\Scripts\python.exe -m pytest -q -x
.\.venv\Scripts\python.exe apps\dashboard-ml\tools\validate_dashboard_app.py
rg -n "supabase\.co/rest/v1|/api/supabase-query|SUPABASE_SERVICE_ROLE_KEY|DATABASE_URL|mzonkpfagqdhaqwybtuo|ovetahxyihemivnlgqhs" apps\dashboard-ml
git diff --check
```

Expected local results:

```text
Branch: integration/bi-rmp-v2-staging-v2
Working tree: clean at start and after commit
Dashboard tests: pass
ML focused tests: pass
Core regression: pass
Forbidden-token scan: no matches
```

## Explicitly Out Of Scope

Do not execute these during MVP-0 acceptance unless a later task explicitly
authorizes a separate phase:

- Supabase init, login, link, or query
- Database read/write
- Migration
- Crawler
- n8n
- LINE
- Ollama
- External AI or network calls, except an explicitly requested Git push
- Deployment
- `main` merge or push
