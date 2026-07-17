from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = APP_ROOT / "frontend"
FORBIDDEN_FRONTEND_TOKENS = (
    "supabase.co/rest/v1",
    "/api/supabase-query",
    "SUPABASE_SERVICE_ROLE_KEY",
    "DATABASE_URL",
    "postgres://",
    "postgresql://",
)


def main() -> int:
    missing = [
        relative
        for relative in (
            "backend/app.py",
            "frontend/index.html",
            "frontend/app.js",
            "frontend/styles.css",
            "ml/safe_text_features.py",
            "requirements.txt",
            ".env.example",
            "README.md",
        )
        if not (APP_ROOT / relative).exists()
    ]
    if missing:
        print("Missing Dashboard files:")
        for path in missing:
            print(f"- {path}")
        return 1

    violations: list[str] = []
    for path in FRONTEND_ROOT.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_FRONTEND_TOKENS:
            if token in content:
                violations.append(f"{path.relative_to(APP_ROOT)} contains {token}")

    if violations:
        print("Forbidden frontend tokens found:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("Dashboard app validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
