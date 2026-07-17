from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from backend.app import app  # noqa: E402


def _client() -> TestClient:
    return TestClient(app)


def test_health_returns_200() -> None:
    response = _client().get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_returns_core_api_url(monkeypatch) -> None:
    monkeypatch.setenv("BI_RMP_CORE_API_URL", "http://core.example.test:8000/")

    response = _client().get("/api/config")

    assert response.status_code == 200
    assert response.json() == {
        "coreApiBaseUrl": "http://core.example.test:8000",
        "dashboardApiPrefix": "/api/dashboard",
    }


def test_config_does_not_include_secrets(monkeypatch) -> None:
    monkeypatch.setenv("BI_RMP_CORE_API_URL", "http://127.0.0.1:8000")
    forbidden = [
        "SUPABASE" + "_SERVICE_ROLE_KEY",
        "DATABASE" + "_URL",
        "PASSWORD",
        "TOKEN",
        "postgres" + "://",
        "postgresql" + "://",
    ]

    response = _client().get("/api/config")
    body = response.text

    assert response.status_code == 200
    assert all(token not in body for token in forbidden)


def test_dashboard_page_loads() -> None:
    response = _client().get("/dashboard")

    assert response.status_code == 200
    assert "Reputation Dashboard" in response.text


def test_static_js_and_css_load() -> None:
    client = _client()

    js_response = client.get("/static/app.js")
    css_response = client.get("/static/styles.css")

    assert js_response.status_code == 200
    assert "loadDashboard" in js_response.text
    assert css_response.status_code == 200
    assert "Reputation Dashboard" not in css_response.text
