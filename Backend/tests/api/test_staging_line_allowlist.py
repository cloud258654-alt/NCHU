from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import api.main as main
from api.liff_registration import LiffIdentity
from api.staging_allowlist import PUBLIC_STAGING_BLOCKED_MESSAGE


def _client(monkeypatch):
    monkeypatch.delenv("BI_RMP_INTERNAL_API_KEY", raising=False)
    for provider_name in (
        "get_client_recognition_repository",
        "get_reputation_crawl_job_service",
        "get_reputation_service",
    ):
        provider = getattr(main, provider_name)
        if hasattr(provider, "cache_clear"):
            provider.cache_clear()
    main.app.dependency_overrides.clear()
    return TestClient(main.app)


def _business_found_result():
    return SimpleNamespace(
        business_found=True,
        to_dict=lambda: {
            "client_registered": True,
            "client_found": True,
            "business_found": True,
            "business_id": 1,
            "business_name": "Staging Test Store",
        },
    )


def test_staging_allowlist_blocks_client_recognition_before_database_write(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("BI_RMP_LINE_ALLOWED_USER_IDS", "U-allowed")
    repo = MagicMock()
    monkeypatch.setattr(main, "get_client_recognition_repository", lambda: repo)

    response = _client(monkeypatch).post(
        "/api/line/client-recognition",
        json={"line_user_id": "U-blocked"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": PUBLIC_STAGING_BLOCKED_MESSAGE}
    assert "U-blocked" not in response.text
    assert "U-allowed" not in response.text
    repo.recognize.assert_not_called()


def test_staging_allowlist_allows_configured_user(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("BI_RMP_LINE_ALLOWED_USER_IDS", "U-allowed,U-other")
    repo = MagicMock()
    repo.recognize.return_value = _business_found_result()
    monkeypatch.setattr(main, "get_client_recognition_repository", lambda: repo)

    response = _client(monkeypatch).post(
        "/api/line/client-recognition",
        json={"line_user_id": "U-allowed"},
    )

    assert response.status_code == 200
    assert response.json()["business_found"] is True
    repo.recognize.assert_called_once_with("U-allowed")


def test_empty_staging_allowlist_preserves_existing_behavior(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("BI_RMP_LINE_ALLOWED_USER_IDS", "")
    repo = MagicMock()
    repo.recognize.return_value = _business_found_result()
    monkeypatch.setattr(main, "get_client_recognition_repository", lambda: repo)

    response = _client(monkeypatch).post(
        "/api/line/client-recognition",
        json={"line_user_id": "U-any"},
    )

    assert response.status_code == 200
    repo.recognize.assert_called_once_with("U-any")


def test_non_staging_environment_ignores_allowlist(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("BI_RMP_LINE_ALLOWED_USER_IDS", "U-allowed")
    repo = MagicMock()
    repo.recognize.return_value = _business_found_result()
    monkeypatch.setattr(main, "get_client_recognition_repository", lambda: repo)

    response = _client(monkeypatch).post(
        "/api/line/client-recognition",
        json={"line_user_id": "U-not-in-list"},
    )

    assert response.status_code == 200
    repo.recognize.assert_called_once_with("U-not-in-list")


def test_staging_allowlist_blocks_liff_registration_after_verified_identity(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("BI_RMP_LINE_ALLOWED_USER_IDS", "U-allowed")
    client = _client(monkeypatch)
    verifier = MagicMock()
    verifier.verify.return_value = LiffIdentity(line_user_id="U-blocked")
    repo = MagicMock()
    main.app.dependency_overrides[main.get_liff_token_verifier] = lambda: verifier
    main.app.dependency_overrides[main.get_business_repository] = lambda: repo

    response = client.post(
        "/api/liff/business/register",
        json={
            "id_token": "token",
            "client_name": "Tester",
            "name": "Staging Test Store",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": PUBLIC_STAGING_BLOCKED_MESSAGE}
    repo.register.assert_not_called()


def test_staging_allowlist_blocks_job_creation_before_service(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("BI_RMP_LINE_ALLOWED_USER_IDS", "U-allowed")
    service = MagicMock()
    monkeypatch.setattr(main, "get_reputation_crawl_job_service", lambda: service)

    response = _client(monkeypatch).post(
        "/api/line/reputation-crawler/jobs",
        json={
            "line_user_id": "U-blocked",
            "business_name": "Staging Test Store",
        },
    )

    assert response.status_code == 403
    service.create_job.assert_not_called()
