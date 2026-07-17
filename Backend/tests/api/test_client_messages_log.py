import pytest
from fastapi.testclient import TestClient
from api.main import app

def test_log_line_message_unauthorized(monkeypatch):
    monkeypatch.setenv("BI_RMP_INTERNAL_API_KEY", "secure_key")
    client = TestClient(app)
    # Without API key header, should return 401
    response = client.post(
        "/api/line/messages/log",
        json={
            "line_user_id": "U123456",
            "message_text": "Hello World",
            "direction": "incoming"
        }
    )
    assert response.status_code == 401

def test_log_line_message_authorized_mocked(monkeypatch):
    monkeypatch.setenv("BI_RMP_INTERNAL_API_KEY", "testkey")
    calls = []
    
    class FakeRepository:
        def log_message(self, line_user_id, message_text, direction, intent, session_state):
            calls.append((line_user_id, message_text, direction, intent, session_state))
            return {"logged": True, "id": 999, "client_id": 123}

    monkeypatch.setattr("api.main.ClientMessagesLogRepository", FakeRepository)
    
    client = TestClient(app)
    response = client.post(
        "/api/line/messages/log",
        headers={"X-BI-RMP-API-Key": "testkey"},
        json={
            "line_user_id": "U123456",
            "message_text": "Hello World",
            "direction": "incoming",
            "intent": "greet",
            "session_state": {"foo": "bar"}
        }
    )
    assert response.status_code == 200
    assert response.json() == {"logged": True, "id": 999, "client_id": 123}
    assert len(calls) == 1
    assert calls[0] == ("U123456", "Hello World", "incoming", "greet", {"foo": "bar"})
