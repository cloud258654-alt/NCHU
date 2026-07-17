# Agent Instructions

## Communication

- Use objective, neutral analysis.
- Do not flatter, agree for its own sake, or provide emotional reassurance.
- Be direct about risks, unknowns, and verification status.

## Project Handoff

Before making changes, read:

```text
docs/AGENT_HANDOFF.md
docs/architecture_review.md
docs/database_execution_runbook.md
```

The current database target is Supabase. Do not expose `.env` secrets in chat, logs, commits, or documentation.

## Safety

- Do not revert unrelated user changes.
- Do not run destructive database operations unless the user explicitly asks and confirms.
- Prefer `Backend/runner.py` as the crawler entry point.
- Prefer `Backend/core/supabase.py` as the database write layer.
