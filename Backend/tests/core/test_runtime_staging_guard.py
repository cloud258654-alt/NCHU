from __future__ import annotations

import pytest

from core import runtime_settings
import core.supabase as supabase


STAGING_REF = runtime_settings.STAGING_PROJECT_REF
BLOCKED_REF = sorted(runtime_settings.BLOCKED_SUPABASE_PROJECT_REFS)[0]


def _direct_database_url(ref: str, password: str = "password") -> str:
    return f"postgres://user:{password}@db.{ref}.supabase.co:5432/postgres"


def _pooler_database_url(ref: str, password: str = "password") -> str:
    return (
        f"postgres://postgres.{ref}:{password}"
        "@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"
    )


def test_staging_correct_ref_passes(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", STAGING_REF)
    monkeypatch.setenv("SUPABASE_URL", f"https://{STAGING_REF}.supabase.co")
    monkeypatch.setenv("DATABASE_URL", _direct_database_url(STAGING_REF))

    runtime_settings.validate_staging_database_target()


def test_staging_wrong_ref_rejects(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", "unexpectedref")

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    message = str(exc_info.value)
    assert STAGING_REF in message
    assert "unexpectedref" not in message


def test_staging_mixed_url_rejects(monkeypatch):
    database_url = _direct_database_url("otherprojectref", password="secret-password")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", STAGING_REF)
    monkeypatch.setenv("SUPABASE_URL", f"https://{STAGING_REF}.supabase.co")
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    message = str(exc_info.value)
    assert "DATABASE_URL" in message
    assert database_url not in message
    assert "secret-password" not in message


def test_local_blocked_production_ref_rejects(monkeypatch):
    database_url = _direct_database_url(BLOCKED_REF, password="secret-password")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("SUPABASE_PROJECT_REF", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    message = str(exc_info.value)
    assert BLOCKED_REF in message
    assert database_url not in message
    assert "secret-password" not in message


def test_production_does_not_apply_staging_ref_lock(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "true")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", BLOCKED_REF)
    monkeypatch.setenv("DATABASE_URL", _direct_database_url(BLOCKED_REF))

    runtime_settings.validate_staging_database_target()


def test_production_requires_allow_production_db_true(monkeypatch):
    database_url = _direct_database_url(BLOCKED_REF, password="secret-password")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", BLOCKED_REF)
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    message = str(exc_info.value)
    assert "ALLOW_PRODUCTION_DB=true" in message
    assert database_url not in message
    assert "secret-password" not in message


def test_allow_database_writes_false_blocks_writable_connection(monkeypatch):
    calls: list[str] = []

    class FakePsycopg2:
        def connect(self, database_url):
            calls.append(f"connect:{database_url}")
            raise AssertionError("connect should not be called")

    monkeypatch.setenv("ALLOW_DATABASE_WRITES", "false")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@localhost:5432/postgres")
    monkeypatch.setattr(supabase, "psycopg2", FakePsycopg2())

    with pytest.raises(
        runtime_settings.DatabaseWritesDisabledError,
        match="Database writes are disabled for this environment",
    ):
        supabase.get_connection()

    assert calls == []


def test_allow_database_writes_true_allows_writable_connection(monkeypatch):
    calls: list[str] = []

    class FakeConnection:
        def set_client_encoding(self, encoding):
            calls.append(f"encoding:{encoding}")

    class FakePsycopg2:
        def connect(self, database_url):
            calls.append(f"connect:{database_url}")
            return FakeConnection()

    database_url = "postgres://user:secret@localhost:5432/postgres"
    monkeypatch.setenv("ALLOW_DATABASE_WRITES", "true")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(supabase, "psycopg2", FakePsycopg2())

    supabase.get_connection()

    assert calls == [
        f"connect:{database_url}",
        "encoding:UTF8",
    ]


def test_pooler_url_with_correct_explicit_ref_passes(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", STAGING_REF)
    monkeypatch.setenv("DATABASE_URL", _pooler_database_url(STAGING_REF))
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    runtime_settings.validate_staging_database_target()


def test_pooler_url_with_wrong_explicit_ref_rejects(monkeypatch):
    database_url = _pooler_database_url(STAGING_REF, password="secret-password")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", "wrongexplicitref")
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    message = str(exc_info.value)
    assert STAGING_REF in message
    assert database_url not in message
    assert "secret-password" not in message
    assert "wrongexplicitref" not in message


def test_error_messages_do_not_leak_password_or_full_database_url(monkeypatch):
    database_url = _direct_database_url("otherprojectref", password="project-secret")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_PRODUCTION_DB", "false")
    monkeypatch.setenv("SUPABASE_PROJECT_REF", STAGING_REF)
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(runtime_settings.StagingTargetError) as exc_info:
        runtime_settings.validate_staging_database_target()

    message = str(exc_info.value)
    assert database_url not in message
    assert "project-secret" not in message
    assert "postgres://" not in message
    assert "DATABASE_URL" in message


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

    monkeypatch.setenv("ALLOW_DATABASE_WRITES", "true")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@example.test/postgres")
    monkeypatch.setattr(supabase, "psycopg2", FakePsycopg2())
    monkeypatch.setattr(supabase, "validate_staging_database_target", fake_validate)

    supabase.get_connection()

    assert calls == [
        "validate",
        "connect:postgres://user:secret@example.test/postgres",
        "encoding:UTF8",
    ]
