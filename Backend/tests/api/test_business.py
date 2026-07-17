from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.business import BusinessRepository
from api.main import app, get_business_repository


def _connection_with_rows(*rows):
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = rows
    return connection, cursor


def test_business_routes_are_registered() -> None:
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/api/line/business/check-duplicate", "POST") in routes


def test_check_duplicate_true() -> None:
    connection, cursor = _connection_with_rows((1,))
    repo = BusinessRepository(connection_factory=lambda: connection)
    assert repo.check_duplicate("文章牛肉湯") is True
    cursor.execute.assert_called_once()
    assert "lower(name) = lower(%s)" in cursor.execute.call_args[0][0]


def test_check_duplicate_false() -> None:
    connection, cursor = _connection_with_rows(None)
    repo = BusinessRepository(connection_factory=lambda: connection)
    assert repo.check_duplicate("快樂小店") is False


def test_register_success() -> None:
    connection, cursor = _connection_with_rows(
        None,  # No duplicate business name
        (42,),  # Client found (client_id = 42)
        (101,), # Inserted business (business_id = 101)
    )
    repo = BusinessRepository(connection_factory=lambda: connection)
    res = repo.register("U12345", "快樂小店", "分店", "餐飲", "台北市")
    assert res["success"] is True
    assert res["business_id"] == 101
    assert res["client_id"] == 42
    assert res["name"] == "快樂小店"
    assert cursor.execute.call_count == 3
    connection.commit.assert_called_once()


def test_register_duplicate_error() -> None:
    connection, cursor = _connection_with_rows(
        (1,),  # Duplicate business name found
    )
    repo = BusinessRepository(connection_factory=lambda: connection)
    with pytest.raises(ValueError, match="已被註冊"):
        repo.register("U12345", "文章牛肉湯")
    connection.rollback.assert_called_once()


def test_register_client_upsert_failure() -> None:
    from api.reputation import DatabaseConfigurationError

    connection, cursor = _connection_with_rows(
        None,  # No duplicate business name
        None,  # Client upsert failed (returns None)
    )
    repo = BusinessRepository(connection_factory=lambda: connection)
    with pytest.raises(DatabaseConfigurationError, match="Unable to register LINE client"):
        repo.register("U99999", "無效客戶店家")
    connection.rollback.assert_called_once()



def test_api_check_duplicate_endpoint() -> None:
    mock_repo = MagicMock()
    mock_repo.check_duplicate.return_value = True
    app.dependency_overrides[get_business_repository] = lambda: mock_repo
    client = TestClient(app)

    try:
        response = client.post(
            "/api/line/business/check-duplicate",
            json={"name": "文章牛肉湯"},
        )
        # If API key checking is enforced, bypass it in tests if needed or test with header
        if response.status_code == 401:
            # retry with test api key
            import os
            api_key = os.getenv("BI_RMP_INTERNAL_API_KEY", "test-key")
            response = client.post(
                "/api/line/business/check-duplicate",
                headers={"X-BI-RMP-API-Key": api_key},
                json={"name": "文章牛肉湯"},
            )
        
        assert response.status_code == 200
        assert response.json() == {"is_duplicate": True}
        mock_repo.check_duplicate.assert_called_once_with("文章牛肉湯")
    finally:
        app.dependency_overrides.clear()





def test_register_success_with_client_name() -> None:
    connection, cursor = _connection_with_rows(
        None,  # No duplicate business name
        (42,),  # Client upserted
        (101,), # Inserted business
    )
    repo = BusinessRepository(connection_factory=lambda: connection)
    res = repo.register("U12345", "快樂小店", "分店", "餐飲", "台北市", client_name="張三")
    assert res["success"] is True
    assert res["business_id"] == 101
    assert res["client_id"] == 42
    assert res["name"] == "快樂小店"
    assert cursor.execute.call_count == 3
    client_upsert_args = cursor.execute.call_args_list[1][0][1]
    assert "張三" in client_upsert_args

