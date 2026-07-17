from __future__ import annotations

import json
from unittest.mock import MagicMock
from urllib.parse import parse_qs

from fastapi.testclient import TestClient

from api.liff_registration import (
    LiffAuthenticationError,
    LiffIdentity,
    LiffTokenVerifier,
)
from api.main import (
    app,
    get_business_repository,
    get_liff_token_verifier,
    get_line_registration_notification_service,
)


class FakeVerifier:
    def __init__(self, identity: LiffIdentity | None = None) -> None:
        self.identity = identity
        self.tokens: list[str] = []

    def verify(self, id_token: str) -> LiffIdentity:
        self.tokens.append(id_token)
        if self.identity is None:
            raise LiffAuthenticationError("LINE 登入憑證無效或已過期")
        return self.identity


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_liff_routes_are_registered() -> None:
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert ("/register", "GET") in routes
    assert ("/api/liff/config", "GET") in routes
    assert ("/api/liff/business/register", "POST") in routes


def test_liff_registration_page_contains_accessible_form() -> None:
    response = TestClient(app).get("/register")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "https://static.line-scdn.net/liff/edge/2/sdk.js" in response.text
    assert '<label for="client-name">' in response.text
    assert '<label for="name">' in response.text
    assert 'aria-live="polite"' in response.text
    assert "prefers-reduced-motion" in response.text


def test_liff_config_requires_liff_id(monkeypatch) -> None:
    monkeypatch.delenv("LINE_LIFF_ID", raising=False)

    response = TestClient(app).get("/api/liff/config")

    assert response.status_code == 503


def test_liff_config_returns_public_liff_id(monkeypatch) -> None:
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-AbcdEfgh")

    response = TestClient(app).get("/api/liff/config")

    assert response.status_code == 200
    assert response.json() == {"liff_id": "1234567890-AbcdEfgh"}


def test_liff_registration_uses_verified_line_id_and_submitted_client_name() -> None:
    verifier = FakeVerifier(LiffIdentity("U-verified", "LINE 顯示名稱"))
    repo = MagicMock()
    repo.register.return_value = {
        "success": True,
        "business_id": 101,
        "client_id": 42,
        "name": "快樂小店",
    }
    notifier = MagicMock()
    notifier.send_registration_completed.return_value = True
    app.dependency_overrides[get_liff_token_verifier] = lambda: verifier
    app.dependency_overrides[get_business_repository] = lambda: repo
    app.dependency_overrides[get_line_registration_notification_service] = lambda: notifier

    try:
        response = TestClient(app).post(
            "/api/liff/business/register",
            json={
                "id_token": "signed-id-token",
                "client_name": "王小明",
                "name": "快樂小店",
                "branch_name": "總店",
                "industry": "餐飲",
                "address": "台北市",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert verifier.tokens == ["signed-id-token"]
    assert response.json()["registration_notification_sent"] is True
    repo.register.assert_called_once_with(
        line_user_id="U-verified",
        name="快樂小店",
        branch_name="總店",
        industry="餐飲",
        address="台北市",
        client_name="王小明",
    )
    notifier.send_registration_completed.assert_called_once_with(
        line_user_id="U-verified",
        business_name="快樂小店",
        branch_name="總店",
    )


def test_liff_registration_rejects_unverified_identity() -> None:
    app.dependency_overrides[get_liff_token_verifier] = lambda: FakeVerifier()
    app.dependency_overrides[get_business_repository] = lambda: MagicMock()

    try:
        response = TestClient(app).post(
            "/api/liff/business/register",
            json={
                "id_token": "expired-token",
                "client_name": "王小明",
                "name": "快樂小店",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "LINE 登入憑證無效" in response.json()["detail"]


def test_liff_registration_rejects_client_supplied_line_user_id() -> None:
    response = TestClient(app).post(
        "/api/liff/business/register",
        json={
            "id_token": "signed-id-token",
            "line_user_id": "U-attacker-controlled",
            "client_name": "王小明",
            "name": "快樂小店",
        },
    )

    assert response.status_code == 422


def test_liff_registration_requires_submitted_client_name() -> None:
    response = TestClient(app).post(
        "/api/liff/business/register",
        json={"id_token": "signed-id-token", "name": "快樂小店"},
    )

    assert response.status_code == 422


def test_liff_token_verifier_posts_token_and_channel_id() -> None:
    captured: dict[str, object] = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = parse_qs(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "sub": "U-verified",
                "aud": "1234567890",
                "name": "王小明",
            }
        )

    identity = LiffTokenVerifier(
        channel_id="1234567890",
        opener=opener,
    ).verify("signed-id-token")

    assert identity == LiffIdentity("U-verified", "王小明")
    assert captured == {
        "url": "https://api.line.me/oauth2/v2.1/verify",
        "body": {
            "id_token": ["signed-id-token"],
            "client_id": ["1234567890"],
        },
        "timeout": 10,
    }
