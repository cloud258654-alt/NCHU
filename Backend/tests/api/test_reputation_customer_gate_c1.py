from __future__ import annotations

import inspect
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.models import BusinessRecord
from api.reputation import (
    BusinessNotFoundError,
    DatabaseConfigurationError,
    PostgresReputationRepository,
    RepositorySnapshot,
    ReputationSummaryService,
    _platform_stats_sql,
)


class SnapshotRepository:
    def __init__(self, snapshots: dict[tuple[str, str | None], RepositorySnapshot]) -> None:
        self.snapshots = snapshots
        self.calls: list[dict[str, object]] = []

    def load_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        key = (str(kwargs["line_user_id"]), str(kwargs.get("task_id")) if kwargs.get("task_id") else None)
        try:
            return self.snapshots[key]
        except KeyError as exc:
            raise BusinessNotFoundError("reputation report not found") from exc


def test_business_scoped_summary_keeps_tenants_separate() -> None:
    repository = SnapshotRepository(
        {
            ("U-A", "101"): _snapshot(
                business_id=1,
                business_name="Shop A",
                platform="ptt",
                total=3,
                task_id="101",
            ),
            ("U-B", "202"): _snapshot(
                business_id=2,
                business_name="Shop B",
                platform="google_maps",
                total=5,
                task_id="202",
            ),
        }
    )
    service = ReputationSummaryService(repository)

    result_a = service.build_summary("U-A", task_id=101)
    result_b = service.build_summary("U-B", task_id=202)

    assert result_a["business"]["name"] == "Shop A"
    assert result_a["overview"]["total_reviews"] == 3
    assert result_a["platforms"][0]["platform"] == "ptt"
    assert result_a["data_contract"]["report_scope"] == "task"
    assert result_b["business"]["name"] == "Shop B"
    assert result_b["overview"]["total_reviews"] == 5
    assert result_b["platforms"][0]["platform"] == "google_maps"


def test_task_ownership_cross_tenant_is_safe_not_found() -> None:
    service = ReputationSummaryService(
        SnapshotRepository(
            {
                ("U-B", "202"): _snapshot(
                    business_id=2,
                    business_name="Shop B Secret",
                    platform="google_maps",
                    total=5,
                    task_id="202",
                )
            }
        )
    )

    with pytest.raises(BusinessNotFoundError) as excinfo:
        service.build_summary("U-A", task_id=202)

    assert "Shop B Secret" not in str(excinfo.value)


def test_missing_business_response_does_not_use_global_data(monkeypatch) -> None:
    class MissingBusinessService:
        def build_summary(self, **kwargs):
            raise BusinessNotFoundError("reputation report not found")

    monkeypatch.delenv("BI_RMP_INTERNAL_API_KEY", raising=False)
    monkeypatch.delenv("BI_RMP_REGISTRATION_URL", raising=False)
    monkeypatch.delenv("LINE_LIFF_ID", raising=False)
    monkeypatch.setattr(api_main, "get_reputation_service", lambda: MissingBusinessService())

    response = TestClient(api_main.app).post(
        "/api/line/reputation-summary",
        json={"line_user_id": "U-no-business"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "no_business"
    assert payload["data_contract"]["report_scope"] == "none"
    assert payload["platforms"] == []
    assert "all_rows" not in response.text


def test_cross_tenant_task_route_does_not_leak_business_details(monkeypatch) -> None:
    class CrossTenantService:
        def build_summary(self, **kwargs):
            raise BusinessNotFoundError("Shop B Secret has 99 rows")

    monkeypatch.delenv("BI_RMP_INTERNAL_API_KEY", raising=False)
    monkeypatch.setattr(api_main, "get_reputation_service", lambda: CrossTenantService())

    response = TestClient(api_main.app).post(
        "/api/line/reputation-summary",
        json={"line_user_id": "U-A", "task_id": 202},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "reputation report not found"
    assert "Shop B Secret" not in response.text
    assert "99" not in response.text


def test_no_canonical_data_returns_no_data_without_fixture_fallback() -> None:
    service = ReputationSummaryService(
        SnapshotRepository(
            {
                ("U-empty", None): RepositorySnapshot(
                    business=BusinessRecord(id=3, name="Empty Shop"),
                    platform_rows=[],
                    latest_summary=None,
                    numeric_risk_available=False,
                    report_scope="business",
                )
            }
        )
    )

    result = service.build_summary("U-empty")

    assert result["status"] == "no_data"
    assert result["overview"]["total_reviews"] == 0
    assert result["platforms"] == []
    assert result["data_contract"]["report_scope"] == "business"
    assert "all_rows" not in str(result)


def test_post_and_comment_analysis_sql_uses_latest_analysis_per_target() -> None:
    query = _platform_stats_sql(report_scope="task", include_numeric_risk=True)

    assert "'crawl_post'::text AS target_type" in query
    assert "'crawl_comment'::text AS target_type" in query
    assert "SELECT DISTINCT ON (ar.target_type, ar.target_id)" in query
    assert "ORDER BY ar.target_type, ar.target_id, ar.analyzed_at DESC, ar.id DESC" in query
    assert "la.target_type = target.target_type" in query
    assert "la.target_id = target.target_id" in query
    assert "st.id = %s" in query
    assert "ar.analysis_status = 'completed'" in query


def test_partial_platform_result_is_marked_partial() -> None:
    service = ReputationSummaryService(
        SnapshotRepository(
            {
                ("U-A", "101"): _snapshot(
                    business_id=1,
                    business_name="Shop A",
                    platform="ptt",
                    total=4,
                    task_id="101",
                    crawl_status_counts={"success": 1, "failed": 1},
                )
            }
        )
    )

    result = service.build_summary("U-A", task_id=101)

    assert result["status"] == "partial"
    assert result["overall"]["data_status"] == "partial"
    assert result["overall"]["crawl_status_counts"] == {"success": 1, "failed": 1}
    assert result["platforms"][0]["platform"] == "ptt"


def test_database_unavailable_response_does_not_leak_secrets_or_sql(monkeypatch) -> None:
    class FailingService:
        def build_summary(self, **kwargs):
            raise DatabaseConfigurationError(
                "DATABASE_URL=postgres://user:password@db.supabase.co SELECT * FROM clients"
            )

    monkeypatch.delenv("BI_RMP_INTERNAL_API_KEY", raising=False)
    monkeypatch.setattr(api_main, "get_reputation_service", lambda: FailingService())

    response = TestClient(api_main.app).post(
        "/api/line/reputation-summary",
        json={"line_user_id": "U-A", "task_id": 101},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "reputation summary database is unavailable"
    forbidden = ["DATABASE_URL", "password", "supabase.co", "SELECT *", "clients"]
    assert all(value not in response.text for value in forbidden)


def test_customer_summary_production_path_has_no_legacy_dependency() -> None:
    route_source = inspect.getsource(api_main.line_reputation_summary)
    service_source = inspect.getsource(api_main.get_reputation_service)

    assert "ReviewsEnrichedRepository" not in route_source
    assert "ReviewsEnrichedRepository" not in service_source
    assert "reviews_enriched" not in route_source
    assert "master_reviews_enriched" not in route_source
    assert "report_scope\"] = \"all_rows\"" not in route_source


def test_task_scoped_summary_excludes_previous_task_data() -> None:
    db = GateC1Database()
    service = ReputationSummaryService(PostgresReputationRepository(db.connect))

    result = service.build_summary("U-A", task_id=102)

    assert result["data_contract"]["report_scope"] == "task"
    assert result["overview"]["total_reviews"] == 1
    assert [platform["platform"] for platform in result["platforms"]] == ["ptt"]
    assert db.executed_contains("WHERE st.id = %s")
    assert not any(
        "WHERE st.business_id = %s" in query
        for query, _ in db.executed
        if "latest_analysis" in query
    )


def test_task_scoped_summary_does_not_include_historical_successful_platform() -> None:
    db = GateC1Database()
    service = ReputationSummaryService(PostgresReputationRepository(db.connect))

    result = service.build_summary("U-A", task_id=102)

    assert result["status"] == "partial"
    assert result["overall"]["included_platforms"] == ["ptt"]
    assert result["overall"]["missing_platforms"] == ["google_maps", "threads"]
    assert all(platform["platform"] != "google_maps" for platform in result["platforms"])


def test_cross_tenant_task_is_not_visible_at_repository_layer() -> None:
    db = GateC1Database()
    repository = PostgresReputationRepository(db.connect)

    with pytest.raises(BusinessNotFoundError):
        repository.load_snapshot(line_user_id="U-A", task_id=201)


def test_latest_valid_analysis_ignores_newer_failed_analysis() -> None:
    db = GateC1Database()
    db.analysis_results.extend(
        [
            _analysis(10, "crawl_post", 1002, "negative", "completed", 1),
            _analysis(11, "crawl_post", 1002, None, "failed", 2),
        ]
    )
    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["negative"] == 1
    assert result["overview"]["unclassified"] == 0


def test_latest_valid_analysis_ignores_newer_pending_analysis() -> None:
    db = GateC1Database()
    db.analysis_results.extend(
        [
            _analysis(10, "crawl_post", 1002, "negative", "completed", 1),
            _analysis(12, "crawl_post", 1002, None, "pending", 3),
        ]
    )
    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["negative"] == 1
    assert result["overview"]["unclassified"] == 0


def test_latest_completed_analysis_wins() -> None:
    db = GateC1Database()
    db.analysis_results.extend(
        [
            _analysis(10, "crawl_post", 1002, "negative", "completed", 1),
            _analysis(13, "crawl_post", 1002, "positive", "completed", 4),
        ]
    )
    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["positive"] == 1
    assert result["overview"]["negative"] == 0


def test_no_valid_analysis_remains_unclassified() -> None:
    db = GateC1Database()
    db.analysis_results.extend(
        [
            _analysis(11, "crawl_post", 1002, None, "failed", 2),
            _analysis(12, "crawl_post", 1002, None, "pending", 3),
        ]
    )
    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["analyzed_reviews"] == 0
    assert result["overview"]["neutral"] == 0
    assert result["overview"]["unclassified"] == 1


def test_task_snapshot_counts_same_task_comment() -> None:
    db = GateC1Database()
    db.crawl_comments.append(_comment(5002, 1002, 4))
    db.analysis_results.append(_analysis(20, "crawl_comment", 5002, "negative", "completed", 5))

    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["data_contract"]["report_scope"] == "task"
    assert result["overview"]["total_reviews"] == 2
    assert result["overview"]["analyzed_reviews"] == 1
    assert result["overview"]["negative"] == 1
    assert result["overview"]["unclassified"] == 1
    assert result["overall"]["included_platforms"] == ["ptt"]
    assert result["overall"]["missing_platforms"] == ["google_maps", "threads"]
    assert result["platforms"][0]["total"] == 2


def test_task_snapshot_excludes_old_task_and_cross_tenant_comments() -> None:
    db = GateC1Database()
    db.crawl_comments.extend(
        [
            _comment(5001, 1001, 4),
            _comment(5002, 1002, 4),
            _comment(6001, 2001, 4),
        ]
    )
    db.analysis_results.extend(
        [
            _analysis(20, "crawl_comment", 5001, "positive", "completed", 5),
            _analysis(21, "crawl_comment", 5002, "negative", "completed", 5),
            _analysis(22, "crawl_comment", 6001, "negative", "completed", 5),
        ]
    )

    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["total_reviews"] == 2
    assert result["overview"]["positive"] == 0
    assert result["overview"]["negative"] == 1
    assert result["overall"]["included_platforms"] == ["ptt"]
    assert all(platform["platform"] not in {"google_maps", "threads"} for platform in result["platforms"])


@pytest.mark.parametrize("invalid_status", ["pending", "failed"])
def test_comment_latest_valid_analysis_ignores_newer_invalid_status(invalid_status: str) -> None:
    db = GateC1Database()
    db.crawl_comments.append(_comment(5002, 1002, 4))
    db.analysis_results.extend(
        [
            _analysis(20, "crawl_comment", 5002, "negative", "completed", 5),
            _analysis(21, "crawl_comment", 5002, None, invalid_status, 6),
        ]
    )

    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["negative"] == 1
    assert result["overview"]["positive"] == 0
    assert result["overview"]["unclassified"] == 1


def test_comment_latest_completed_analysis_wins() -> None:
    db = GateC1Database()
    db.crawl_comments.append(_comment(5002, 1002, 4))
    db.analysis_results.extend(
        [
            _analysis(20, "crawl_comment", 5002, "negative", "completed", 5),
            _analysis(21, "crawl_comment", 5002, "positive", "completed", 6),
        ]
    )

    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["positive"] == 1
    assert result["overview"]["negative"] == 0
    assert result["overview"]["unclassified"] == 1


def test_comment_with_no_valid_analysis_is_unclassified() -> None:
    db = GateC1Database()
    db.crawl_comments.append(_comment(5002, 1002, 4))
    db.analysis_results.extend(
        [
            _analysis(20, "crawl_comment", 5002, None, "pending", 5),
            _analysis(21, "crawl_comment", 5002, None, "failed", 6),
        ]
    )

    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["total_reviews"] == 2
    assert result["overview"]["analyzed_reviews"] == 0
    assert result["overview"]["unclassified"] == 2


def test_comment_join_does_not_duplicate_post_or_comment_totals() -> None:
    db = GateC1Database()
    db.crawl_comments.append(_comment(5002, 1002, 4))
    db.analysis_results.extend(
        [
            _analysis(20, "crawl_comment", 5002, "negative", "completed", 5),
            _analysis(21, "crawl_comment", 5002, "positive", "completed", 6),
            _analysis(22, "crawl_comment", 5002, "negative", "failed", 7),
        ]
    )

    result = ReputationSummaryService(PostgresReputationRepository(db.connect)).build_summary(
        "U-A",
        task_id=102,
    )

    assert result["overview"]["total_reviews"] == 2
    assert result["overview"]["analyzed_reviews"] == 1
    assert result["overview"]["positive"] == 1
    assert result["overview"]["negative"] == 0
    assert result["platforms"][0]["total"] == 2


def test_canonical_customer_summary_uses_non_legacy_report_type(monkeypatch) -> None:
    class CanonicalService:
        def build_summary(self, **kwargs):
            return ReputationSummaryService(
                SnapshotRepository(
                    {
                        ("U-A", "102"): _snapshot(
                            business_id=1,
                            business_name="Shop A",
                            platform="ptt",
                            total=1,
                            task_id="102",
                        )
                    }
                )
            ).build_summary("U-A", task_id=102)

    monkeypatch.delenv("BI_RMP_INTERNAL_API_KEY", raising=False)
    monkeypatch.setattr(api_main, "get_reputation_service", lambda: CanonicalService())

    response = TestClient(api_main.app).post(
        "/api/line/reputation-summary",
        json={"line_user_id": "U-A", "task_id": 102},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_contract"]["report_type"] == "canonical_reputation_summary"
    assert "reviews_enriched_quantitative" not in response.text


def test_report_scope_matches_repository_query_scope() -> None:
    db = GateC1Database()
    service = ReputationSummaryService(PostgresReputationRepository(db.connect))

    task_result = service.build_summary("U-A", task_id=102)
    task_queries = list(db.executed)
    db.executed.clear()
    business_result = service.build_summary("U-A")

    assert task_result["data_contract"]["report_scope"] == "task"
    assert business_result["data_contract"]["report_scope"] == "business"
    assert any("WHERE st.id = %s" in query for query, _ in task_queries)
    assert any("WHERE st.business_id = %s" in query for query, _ in db.executed)


def _snapshot(
    *,
    business_id: int,
    business_name: str,
    platform: str,
    total: int,
    task_id: str,
    crawl_status_counts: dict[str, int] | None = None,
) -> RepositorySnapshot:
    return RepositorySnapshot(
        business=BusinessRecord(id=business_id, name=business_name),
        platform_rows=[
            {
                "platform": platform,
                "total": total,
                "analyzed": total,
                "positive": max(total - 1, 0),
                "neutral": 0,
                "negative": 1 if total else 0,
                "unclassified": 0,
                "risk_score": 42.0,
                "risk_score_count": total,
                "risk_points": 1,
                "risk_rank": 1,
                "updated_at": datetime(2026, 7, 20, tzinfo=timezone.utc),
            }
        ],
        latest_summary=f"{business_name} scoped summary",
        numeric_risk_available=True,
        report_scope="task",
        task_id=task_id,
        crawl_status_counts=crawl_status_counts or {"success": 1},
    )


class GateC1Database:
    def __init__(self) -> None:
        self.clients = [
            {"id": 1, "line_user_id": "U-A", "status": "active"},
            {"id": 2, "line_user_id": "U-B", "status": "active"},
        ]
        self.business = [
            {"id": 1, "client_id": 1, "name": "Shop A", "branch_name": None, "status": "active"},
            {"id": 2, "client_id": 2, "name": "Shop B", "branch_name": None, "status": "active"},
        ]
        self.service_tasks = [
            {"id": 101, "business_id": 1, "service_type": "reputation_monitoring", "status": "completed"},
            {"id": 102, "business_id": 1, "service_type": "reputation_monitoring", "status": "completed"},
            {"id": 201, "business_id": 2, "service_type": "reputation_monitoring", "status": "completed"},
        ]
        self.crawl_jobs = [
            {"id": 1001, "service_task_id": 101, "platform": "google_maps", "status": "success"},
            {"id": 1002, "service_task_id": 102, "platform": "ptt", "status": "success"},
            {"id": 1003, "service_task_id": 102, "platform": "google_maps", "status": "failed"},
            {"id": 2001, "service_task_id": 201, "platform": "threads", "status": "success"},
        ]
        self.crawl_posts = [
            _post(1001, 1001, 1),
            _post(1002, 1002, 2),
            _post(2001, 2001, 3),
        ]
        self.crawl_comments: list[dict[str, Any]] = []
        self.analysis_results = [
            _analysis(1, "crawl_post", 1001, "positive", "completed", 1),
            _analysis(2, "crawl_post", 2001, "negative", "completed", 1),
        ]
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def connect(self) -> "GateC1Connection":
        return GateC1Connection(self)

    def executed_contains(self, text: str) -> bool:
        return any(text in query for query, _ in self.executed)

    def resolve_business(
        self,
        *,
        line_user_id: str,
        business_id: int | None = None,
        business_name: str | None = None,
        task_id: int | None = None,
    ) -> dict[str, Any] | None:
        matching_clients = [
            client
            for client in self.clients
            if client["line_user_id"] == line_user_id and client["status"] == "active"
        ]
        if not matching_clients:
            return None
        client_ids = {client["id"] for client in matching_clients}
        businesses = [
            item
            for item in self.business
            if item["client_id"] in client_ids and item["status"] == "active"
        ]
        if task_id is not None:
            allowed_business_ids = {
                task["business_id"]
                for task in self.service_tasks
                if task["id"] == task_id and task["service_type"] == "reputation_monitoring"
            }
            businesses = [item for item in businesses if item["id"] in allowed_business_ids]
        elif business_id is not None:
            businesses = [item for item in businesses if item["id"] == business_id]
        elif business_name is not None:
            businesses = [
                item for item in businesses if item["name"].strip().casefold() == business_name.strip().casefold()
            ]
        return sorted(businesses, key=lambda item: item["id"])[0] if businesses else None

    def targets(self, *, scope: str, scope_id: int) -> list[dict[str, Any]]:
        if scope == "task":
            task_ids = {scope_id}
        else:
            task_ids = {
                task["id"]
                for task in self.service_tasks
                if task["business_id"] == scope_id and task["status"] != "cancelled"
            }
        jobs = [
            job
            for job in self.crawl_jobs
            if job["service_task_id"] in task_ids and job["status"] != "cancelled"
        ]
        job_by_id = {job["id"]: job for job in jobs}
        targets = []
        for post in self.crawl_posts:
            job = job_by_id.get(post["crawl_job_id"])
            if not job or post.get("is_deleted"):
                continue
            targets.append(
                {
                    "target_type": "crawl_post",
                    "target_id": post["id"],
                    "platform": job["platform"],
                    "observed_at": post["updated_at"],
                }
            )
        for comment in self.crawl_comments:
            post = next((item for item in self.crawl_posts if item["id"] == comment["crawl_post_id"]), None)
            job = job_by_id.get(post["crawl_job_id"] if post else None)
            if not job or not post or post.get("is_deleted") or comment.get("is_deleted"):
                continue
            targets.append(
                {
                    "target_type": "crawl_comment",
                    "target_id": comment["id"],
                    "platform": job["platform"],
                    "observed_at": comment["updated_at"],
                }
            )
        return targets

    def latest_analysis_by_target(self) -> dict[tuple[str, int], dict[str, Any]]:
        valid = [row for row in self.analysis_results if _valid_analysis(row)]
        ordered = sorted(
            valid,
            key=lambda row: (row["target_type"], row["target_id"], row["analyzed_at"], row["id"]),
            reverse=True,
        )
        latest: dict[tuple[str, int], dict[str, Any]] = {}
        for row in ordered:
            latest.setdefault((row["target_type"], row["target_id"]), row)
        return latest


class GateC1Connection:
    def __init__(self, db: GateC1Database) -> None:
        self.db = db

    def cursor(self, cursor_factory=None) -> "GateC1Cursor":
        return GateC1Cursor(self.db)

    def close(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class GateC1Cursor:
    def __init__(self, db: GateC1Database) -> None:
        self.db = db
        self.rows: list[Any] = []

    def __enter__(self) -> "GateC1Cursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        self.db.executed.append((query, params))
        if "SELECT b.id, b.name, b.branch_name" in query:
            self.rows = self._business_rows(query, params)
        elif "GROUP BY status" in query:
            self.rows = self._status_rows(params)
        elif "SELECT la.summary" in query:
            self.rows = self._summary_rows(query, params)
        elif "SELECT\n    platform," in query:
            self.rows = self._platform_rows(query, params)
        else:
            raise AssertionError(f"unexpected SQL in Gate C1 test adapter: {query}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def _business_rows(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        line_user_id = str(params[0])
        task_id = int(params[1]) if "st.id = %s" in query else None
        business_id = int(params[1]) if "b.id = %s" in query else None
        business_name = str(params[1]) if "lower(btrim(b.name))" in query else None
        business = self.db.resolve_business(
            line_user_id=line_user_id,
            business_id=business_id,
            business_name=business_name,
            task_id=task_id,
        )
        if business is None:
            return []
        return [
            {
                "id": business["id"],
                "name": business["name"],
                "branch_name": business["branch_name"],
            }
        ]

    def _status_rows(self, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        counts = Counter(
            job["status"]
            for job in self.db.crawl_jobs
            if job["service_task_id"] == int(params[0])
        )
        return [{"status": status, "count": count} for status, count in counts.items()]

    def _summary_rows(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        scope = _scope_from_query(query)
        targets = self.db.targets(scope=scope, scope_id=int(params[0]))
        latest = self.db.latest_analysis_by_target()
        summaries = [
            analysis
            for target in targets
            if (analysis := latest.get((target["target_type"], target["target_id"])))
            and analysis.get("summary")
        ]
        summaries.sort(key=lambda row: (row["analyzed_at"], row["id"]), reverse=True)
        return [{"summary": summaries[0]["summary"]}] if summaries else []

    def _platform_rows(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        scope = _scope_from_query(query)
        targets = self.db.targets(scope=scope, scope_id=int(params[0]))
        latest = self.db.latest_analysis_by_target()
        grouped: dict[str, dict[str, Any]] = {}
        for target in targets:
            platform = target["platform"]
            row = grouped.setdefault(
                platform,
                {
                    "platform": platform,
                    "total": 0,
                    "analyzed": 0,
                    "positive": 0,
                    "neutral": 0,
                    "negative": 0,
                    "unclassified": 0,
                    "risk_score": None,
                    "risk_score_count": 0,
                    "risk_points": None,
                    "risk_rank": 0,
                    "updated_at": None,
                },
            )
            row["total"] += 1
            analysis = latest.get((target["target_type"], target["target_id"]))
            if analysis is None:
                row["unclassified"] += 1
            else:
                row["analyzed"] += 1
                sentiment = analysis.get("sentiment")
                if sentiment in {"positive", "neutral", "negative"}:
                    row[sentiment] += 1
                else:
                    row["unclassified"] += 1
                if analysis.get("risk_score") is not None:
                    row["risk_score"] = analysis["risk_score"]
                    row["risk_score_count"] += 1
                if analysis.get("risk_points") is not None:
                    row["risk_points"] = (row["risk_points"] or 0) + analysis["risk_points"]
                row["risk_rank"] = max(row["risk_rank"], {"low": 1, "medium": 2, "high": 3}.get(analysis.get("risk_level"), 0))
            row["updated_at"] = max(
                [value for value in (row["updated_at"], target["observed_at"], analysis.get("analyzed_at") if analysis else None) if value]
            )
        return [grouped[key] for key in sorted(grouped)]


def _scope_from_query(query: str) -> str:
    if "WHERE st.id = %s" in query:
        return "task"
    if "WHERE st.business_id = %s" in query:
        return "business"
    raise AssertionError("query did not include a supported repository scope")


def _valid_analysis(row: dict[str, Any]) -> bool:
    if row.get("analysis_status") == "completed":
        return True
    if row.get("analysis_status") is not None:
        return False
    return any(
        row.get(field) is not None
        for field in ("sentiment", "risk_level", "summary", "risk_score", "risk_points")
    )


def _post(post_id: int, crawl_job_id: int, day: int) -> dict[str, Any]:
    return {
        "id": post_id,
        "crawl_job_id": crawl_job_id,
        "updated_at": datetime(2026, 7, day, tzinfo=timezone.utc),
        "is_deleted": False,
    }


def _comment(comment_id: int, crawl_post_id: int, day: int) -> dict[str, Any]:
    return {
        "id": comment_id,
        "crawl_post_id": crawl_post_id,
        "updated_at": datetime(2026, 7, day, tzinfo=timezone.utc),
        "is_deleted": False,
    }


def _analysis(
    analysis_id: int,
    target_type: str,
    target_id: int,
    sentiment: str | None,
    status: str | None,
    day: int,
) -> dict[str, Any]:
    return {
        "id": analysis_id,
        "target_type": target_type,
        "target_id": target_id,
        "sentiment": sentiment,
        "analysis_status": status,
        "risk_level": "high" if sentiment == "negative" else ("low" if sentiment == "positive" else None),
        "risk_score": 80.0 if sentiment == "negative" else (20.0 if sentiment == "positive" else None),
        "risk_points": 3 if sentiment == "negative" else (1 if sentiment == "positive" else None),
        "summary": f"{status or 'legacy'} {sentiment or 'none'}",
        "analyzed_at": datetime(2026, 7, day, tzinfo=timezone.utc),
    }
