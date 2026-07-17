from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

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

STAGING_PROJECT_REF = "qlhykeeyjaoikczoambe"
STAGING_PROJECT_NAME = "BI-RMP-V2-STAGING"
BLOCKED_SUPABASE_PROJECT_REFS = frozenset(
    {
        "mzonkpfagqdhaqwybtuo",
        "ovetahxyihemivnlgqhs",
    }
)


class StagingTargetError(ValueError):
    """Raised when runtime configuration points at a forbidden database target."""


def _resolve_project_path(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _extract_project_ref_from_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return host.removeprefix("db.").split(".", 1)[0]
    if host.endswith(".supabase.co"):
        return host.split(".", 1)[0]
    return None


def _configured_project_refs() -> dict[str, str]:
    refs: dict[str, str] = {}
    explicit_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    if explicit_ref:
        refs["SUPABASE_PROJECT_REF"] = explicit_ref

    for name in ("SUPABASE_URL", "DATABASE_URL"):
        ref = _extract_project_ref_from_url(os.getenv(name, "").strip())
        if ref:
            refs[name] = ref
    return refs


def validate_staging_database_target() -> None:
    refs = _configured_project_refs()
    blocked = sorted(set(refs.values()) & BLOCKED_SUPABASE_PROJECT_REFS)
    if blocked:
        raise StagingTargetError(
            "database target uses a forbidden Supabase project ref: "
            + ", ".join(blocked)
        )

    app_env = os.getenv("APP_ENV", "").strip().lower()
    if app_env != "staging":
        return

    project_ref = refs.get("SUPABASE_PROJECT_REF")
    if project_ref != STAGING_PROJECT_REF:
        raise StagingTargetError(
            "APP_ENV=staging requires SUPABASE_PROJECT_REF="
            f"{STAGING_PROJECT_REF}"
        )

    for name, ref in refs.items():
        if ref != STAGING_PROJECT_REF:
            raise StagingTargetError(
                f"APP_ENV=staging requires {name} to target "
                f"{STAGING_PROJECT_REF}"
            )

    if _env_bool("ALLOW_PRODUCTION_DB", default=False):
        raise StagingTargetError("APP_ENV=staging requires ALLOW_PRODUCTION_DB=false")


DATABASE_URL = os.getenv("DATABASE_URL")
APP_ENV = os.getenv("APP_ENV", "local").strip()
DATABASE_TARGET = os.getenv("DATABASE_TARGET", "").strip()
ALLOW_PRODUCTION_DB = _env_bool("ALLOW_PRODUCTION_DB", default=False)
ALLOW_DATABASE_WRITES = _env_bool("ALLOW_DATABASE_WRITES", default=True)
SUPABASE_PROJECT_NAME = os.getenv("SUPABASE_PROJECT_NAME", "").strip()
SUPABASE_PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
BI_RMP_CORE_API_URL = os.getenv("BI_RMP_CORE_API_URL", "http://127.0.0.1:8000").strip()
DASHBOARD_ML_API_URL = os.getenv("DASHBOARD_ML_API_URL", "http://127.0.0.1:8010").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080").strip()
N8N_HOST_PORT = int(os.getenv("N8N_HOST_PORT", "5678"))
HEADLESS = os.getenv("HEADLESS", "True").strip().lower() not in {"false", "0", "no"}
SCROLL_DELAY = float(os.getenv("SCROLL_DELAY", "3.0"))
SCROLL_ROUNDS = int(os.getenv("SCROLL_ROUNDS", "5"))
STORAGE_STATE_PATH = _resolve_project_path(os.getenv("STORAGE_STATE_PATH", "storage_state.json"))
THREADS_STORAGE_STATE_PATH = _resolve_project_path(
    os.getenv("THREADS_STORAGE_STATE_PATH", "storage/threads_state.json")
)
