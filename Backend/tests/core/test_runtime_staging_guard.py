from __future__ import annotations

import pytest

from core import runtime_settings
import core.supabase as supabase


def test_staging_guard_accepts_locked_staging_target(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", runtime_settings.STAGING_PROJECT_REF)
    monkeypatch.setenv(
        "SUPABASE_URL",
        f"https://{runtime_settings.STAGING_PROJECT_REF}.supabase.co",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgres://user:password@db.{runtime_settings.STAGING_PROJECT_REF}.supabase.co:5432/postgres",
    )

    runtime_settings.validate_staging_database_target()


@pytest.mark.parametrize("blocked_ref", sorted(runtime_settings.BLOCKED_SUPABASE_PROJECT_REFS))
def test_staging_guard_rejects_blocked_supabase_refs(monkeypatch, blocked_ref):
    database_url = f"postgres://user:secret@db.{blocked_ref}.supabase.co:5432/postgres"
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("SUPABASE_PROJECT_REF", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    message = str(exc_info.value)
    assert blocked_ref in message
    assert database_url not in message
    assert "secret" not in message


def test_staging_guard_requires_exact_project_ref(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", "unexpectedref")
    monkeypatch.setenv(
        "SUPABASE_URL",
        f"https://{runtime_settings.STAGING_PROJECT_REF}.supabase.co",
    )

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    assert runtime_settings.STAGING_PROJECT_REF in str(exc_info.value)
    assert "unexpectedref" not in str(exc_info.value)


def test_staging_guard_rejects_mixed_staging_targets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", runtime_settings.STAGING_PROJECT_REF)
    monkeypatch.setenv("SUPABASE_URL", "https://otherprojectref.supabase.co")

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    assert "SUPABASE_URL" in str(exc_info.value)
    assert "otherprojectref" not in str(exc_info.value)


def test_staging_guard_rejects_production_db_override(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "true")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", runtime_settings.STAGING_PROJECT_REF)

    with pytest.raises(runtime_settings.StagingTargetError, match="ALLOW_PRODUCTION_DB=false"):
        runtime_settings.validate_staging_database_target()


def test_supabase_connection_validates_target_before_connect(monkeypatch):
    calls: list[str] = []

    class FakeConnection:
        def set_client_encoding(self, encoding):
            calls.append(f"encoding:{encoding}")

    class FakePsycopg2:
        def connect(self, database_url):
            calls.append(f"connect:{database_url}")
            return FakeConnection()

    def fake_validate():
        calls.append("validate")

    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@example.test/postgres")
    monkeypatch.setattr(supabase, "psycopg2", FakePsycopg2())
    monkeypatch.setattr(supabase, "validate_staging_database_target", fake_validate)

    supabase.get_connection()

    assert calls == [
        "validate",
        "connect:postgres://user:secret@example.test/postgres",
        "encoding:UTF8",
    ]
