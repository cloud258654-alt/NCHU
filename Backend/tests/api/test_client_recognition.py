from __future__ import annotations

from unittest.mock import MagicMock

from api.client_recognition import ClientRecognitionRepository
from api.main import app


def _connection_with_rows(*rows):
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = rows
    return connection, cursor


def test_client_recognition_route_is_registered() -> None:
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert ("/api/line/client-recognition", "POST") in routes


def test_unknown_line_user_is_registered_without_business_fallback() -> None:
    connection, cursor = _connection_with_rows((3, True), None)

    result = ClientRecognitionRepository._recognize(
        connection,
        line_user_id="U-unknown",
    )

    assert result.client_registered is True
    assert result.client_created is True
    assert result.client_found is True
    assert result.client_id == 3
    assert result.business_found is False
    assert result.business_id is None
    assert result.business_name is None
    assert cursor.execute.call_count == 2
    assert "ON CONFLICT (line_user_id)" in cursor.execute.call_args_list[0].args[0]
    connection.commit.assert_called_once()


def test_known_line_user_returns_first_active_business() -> None:
    connection, cursor = _connection_with_rows(
        (3, False),
        (11, "已綁定店家", "總店"),
    )

    result = ClientRecognitionRepository._recognize(
        connection,
        line_user_id="U-known",
    )

    assert result.client_registered is True
    assert result.client_created is False
    assert result.client_found is True
    assert result.client_id == 3
    assert result.business_found is True
    assert result.business_id == 11
    assert result.business_name == "已綁定店家"
    assert result.branch_name == "總店"
    assert cursor.execute.call_count == 2


def test_known_line_user_without_business_is_reported_separately() -> None:
    connection, _ = _connection_with_rows((3, False), None)

    result = ClientRecognitionRepository._recognize(
        connection,
        line_user_id="U-known-without-business",
    )

    assert result.client_registered is True
    assert result.client_created is False
    assert result.client_found is True
    assert result.client_id == 3
    assert result.business_found is False
    assert result.business_id is None
    assert result.business_name is None
