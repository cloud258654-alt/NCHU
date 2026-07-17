from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def _load_env_file(path: Path) -> None:
    if load_dotenv is not None:
        load_dotenv(path, override=False)
        return

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ[key] = value


_load_env_file(PROJECT_ROOT / ".env")

def _resolve_project_path(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


DATABASE_URL = os.getenv("DATABASE_URL")
HEADLESS = os.getenv("HEADLESS", "True").strip().lower() not in {"false", "0", "no"}
SCROLL_DELAY = float(os.getenv("SCROLL_DELAY", "3.0"))
SCROLL_ROUNDS = int(os.getenv("SCROLL_ROUNDS", "5"))
STORAGE_STATE_PATH = _resolve_project_path(os.getenv("STORAGE_STATE_PATH", "storage_state.json"))
THREADS_STORAGE_STATE_PATH = _resolve_project_path(
    os.getenv("THREADS_STORAGE_STATE_PATH", "storage/threads_state.json")
)
