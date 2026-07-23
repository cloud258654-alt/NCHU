from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.dashboard import DashboardRepository, get_dashboard_repository
from api.main import app
from api.reputation import DatabaseConfigurationError


class FakeDashboardRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.businesses = [
            {
                "id": 1,
                "name": "Demo Shop",
                "branch_name": "Main",
                "industry": "restaurant",
                "status": "active",
                "review_count": 12,
                "latest_review_at": "2026-07-17T10:00:00+00:00",
            }
        ]
        self.summary = {
            "total_businesses": 1,
            "total_items": 18,
            "total_reviews": 12,
            "total_comments": 6,
            "analyzed_items": 10,
            "positive": 6,
            "neutral": 3,
            "negative": 1,
            "unclassified": 8,
            "risk_level": "medium",
            "updated_at": "2026-07-17T10:00:00+00:00",
        }
        self.reviews = {
            "items": [
                {
                    "id": 101,
                    "business_id": 1,
                    "business_name": "Demo Shop",
                    "platform": "google_maps",
                    "title": "Good service",
                    "author_name": "Alice",
                    "content": "Good service and food",
                    "link": "https://example.test/review/101",
                    "published_at": "2026-07-16T10:00:00+00:00",
                    "updated_at": "2026-07-17T10:00:00+00:00",
                    "sentiment": "positive",
                    "risk_level": "low",
                    "summary": "Customer liked the service.",
                }
            ],
            "page": 2,
            "page_size": 5,
            "total": 11,
        }
        self.review = {
            "id": 101,
            "business_id": 1,
            "business_name": "Demo Shop",
            "platform": "google_maps",
            "title": "Good service",
            "author_name": "Alice",
            "content": "Good service and food",
            "link": "https://example.test/review/101",
            "sentiment": "positive",
            "risk_level": "low",
        }

    def list_businesses(self):
        self.calls.append(("list_businesses", {}))
        return self.businesses

    def get_summary(self, *, business_id=None):
        self.calls.append(("get_summary", {"business_id": business_id}))
        return self.summary

    def list_reviews(self, *, page, page_size, business_id=None, platform=None):
        self.calls.append(
            (
                "list_reviews",
                {
                    "page": page,
                    "page_size": page_size,
                    "business_id": business_id,
                    "platform": platform,
                },
            )
        )
        return self.reviews

    def get_review(self, review_id):
        self.calls.append(("get_review", {"review_id": review_id}))
        if review_id == 404:
            return None
        return self.review


def _client_with_repo(repo):
    app.dependency_overrides[get_dashboard_repository] = lambda: repo
    return TestClient(app)


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def _connection_with_rows(rows):
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = rows[0] if rows else None
    return connection, cursor


def test_dashboard_routes_are_registered_as_get_only() -> None:
    targets = {
        "/api/dashboard/businesses",
        "/api/dashboard/summary",
        "/api/dashboard/reviews",
        "/api/dashboard/reviews/{review_id}",
    }

    route_methods = {
        route.path: set(getattr(route, "methods", set()))
        for route in app.routes
        if getattr(route, "path", None) in targets
    }

    assert set(route_methods) == targets
    assert all(methods == {"GET"} for methods in route_methods.values())


def test_dashboard_mutating_methods_are_not_registered() -> None:
    client = TestClient(app)

    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/api/dashboard/reviews")
        assert response.status_code == 405


def test_businesses_endpoint_returns_repository_payload() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get("/api/dashboard/businesses")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Demo Shop"
    assert repo.calls == [("list_businesses", {})]


def test_summary_endpoint_passes_optional_business_id() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get("/api/dashboard/summary?business_id=1")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()["total_reviews"] == 12
    assert repo.calls == [("get_summary", {"business_id": 1})]


def test_reviews_endpoint_passes_pagination_and_filters() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get(
            "/api/dashboard/reviews",
            params={
                "page": 2,
                "page_size": 5,
                "business_id": 1,
                "platform": "google_maps",
            },
        )
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == 101
    assert repo.calls == [
        (
            "list_reviews",
            {
                "page": 2,
                "page_size": 5,
                "business_id": 1,
                "platform": "google_maps",
            },
        )
    ]


def test_reviews_endpoint_rejects_invalid_page() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get("/api/dashboard/reviews?page=0")
    finally:
        _clear_overrides()

    assert response.status_code == 422
    assert repo.calls == []


def test_reviews_endpoint_caps_page_size() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get("/api/dashboard/reviews?page_size=101")
    finally:
        _clear_overrides()

    assert response.status_code == 422
    assert repo.calls == []


def test_single_review_endpoint_returns_review() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get("/api/dashboard/reviews/101")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()["id"] == 101
    assert repo.calls == [("get_review", {"review_id": 101})]


def test_single_review_endpoint_returns_404_when_missing() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get("/api/dashboard/reviews/404")
    finally:
        _clear_overrides()

    assert response.status_code == 404
    assert response.json() == {"detail": "Dashboard review was not found"}


def test_single_review_endpoint_rejects_non_integer_id_without_repo_call() -> None:
    repo = FakeDashboardRepository()
    client = _client_with_repo(repo)
    try:
        response = client.get("/api/dashboard/reviews/not-an-int")
    finally:
        _clear_overrides()

    assert response.status_code == 422
    assert repo.calls == []


def test_database_configuration_error_is_sanitized() -> None:
    class BrokenRepo(FakeDashboardRepository):
        def list_businesses(self):
            raise DatabaseConfigurationError("DATABASE_URL=postgres://secret")

    client = _client_with_repo(BrokenRepo())
    try:
        response = client.get("/api/dashboard/businesses")
    finally:
        _clear_overrides()

    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard database is not configured"}
    assert "DATABASE_URL" not in response.text
    assert "secret" not in response.text


def test_repository_exception_is_sanitized() -> None:
    class BrokenRepo(FakeDashboardRepository):
        def get_summary(self, *, business_id=None):
            raise RuntimeError("SELECT secret_token FROM hidden")

    client = _client_with_repo(BrokenRepo())
    try:
        response = client.get("/api/dashboard/summary")
    finally:
        _clear_overrides()

    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard data is unavailable"}
    assert "secret_token" not in response.text
    assert "SELECT" not in response.text


def test_repository_list_businesses_uses_read_only_select_and_closes_connection() -> None:
    rows = [
        {
            "id": 1,
            "name": "Demo Shop",
            "branch_name": None,
            "industry": "restaurant",
            "status": "active",
            "review_count": 3,
            "latest_review_at": datetime(2026, 7, 17, tzinfo=timezone.utc),
        }
    ]
    connection, cursor = _connection_with_rows(rows)

    result = DashboardRepository(connection_factory=lambda: connection).list_businesses()

    assert result[0]["latest_review_at"] == "2026-07-17T00:00:00+00:00"
    sql = cursor.execute.call_args[0][0].lower()
    assert "select" in sql
    assert all(word not in sql for word in (" insert ", " update ", " delete ", " upsert "))
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once()


def test_repository_list_reviews_uses_parameterized_filters_and_pagination() -> None:
    rows = [
        {
            "id": 101,
            "business_id": 1,
            "business_name": "Demo Shop",
            "platform": "ptt",
            "title": "Review",
            "author_name": "Alice",
            "content": "content",
            "link": "https://example.test",
            "published_at": None,
            "updated_at": None,
            "sentiment": "positive",
            "risk_level": "low",
            "summary": "ok",
            "total_count": 9,
        }
    ]
    connection, cursor = _connection_with_rows(rows)

    result = DashboardRepository(connection_factory=lambda: connection).list_reviews(
        page=3,
        page_size=4,
        business_id=1,
        platform="ptt",
    )

    assert result["total"] == 9
    assert result["page"] == 3
    assert result["page_size"] == 4
    assert result["items"][0]["id"] == 101
    sql, params = cursor.execute.call_args[0]
    assert "st.business_id = %s" in sql
    assert "lower(cj.platform) = lower(%s)" in sql
    assert "ar.analysis_status = 'completed'" in sql
    assert "ar.analyzed_at DESC, ar.created_at DESC, ar.id DESC" in sql
    assert params == (1, "ptt", 4, 8)
    connection.commit.assert_not_called()


def test_repository_get_review_uses_parameterized_id() -> None:
    rows = [{"id": 101, "title": "Review", "updated_at": None}]
    connection, cursor = _connection_with_rows(rows)

    result = DashboardRepository(connection_factory=lambda: connection).get_review(101)

    assert result == {"id": 101, "title": "Review", "updated_at": None}
    sql, params = cursor.execute.call_args[0]
    assert "WHERE cp.id = %s" in sql
    assert "ar.analysis_status = 'completed'" in sql
    assert "ar.analyzed_at DESC, ar.created_at DESC, ar.id DESC" in sql
    assert params == (101,)
    connection.commit.assert_not_called()


def test_dashboard_summary_uses_only_latest_completed_analysis():
    source = DashboardRepository.get_summary.__code__.co_consts
    sql = "\n".join(value for value in source if isinstance(value, str))

    assert "WHERE ar.analysis_status = 'completed'" in sql
    assert "ar.analyzed_at DESC, ar.created_at DESC, ar.id DESC" in sql
