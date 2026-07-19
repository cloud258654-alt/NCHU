from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ModuleNotFoundError:  # pragma: no cover - surfaced as configuration error at runtime
    psycopg2 = None
    RealDictCursor = None

from api.models import BusinessRecord, PlatformSummary, ReputationOverview
from services.reputation_scoring.scoring_config import load_reputation_scoring_config


class ReputationError(RuntimeError):
    """Base error for reputation summary operations."""


class BusinessNotFoundError(ReputationError):
    """Raised when a LINE user has no active business mapping."""


class DatabaseConfigurationError(ReputationError):
    """Raised when the backend database is not configured."""


@dataclass(frozen=True)
class RepositorySnapshot:
    business: BusinessRecord
    platform_rows: list[dict[str, Any]]
    latest_summary: str | None
    numeric_risk_available: bool
    report_scope: str = "business"
    task_id: str | None = None
    crawl_status_counts: dict[str, int] | None = None


class SnapshotRepository(Protocol):
    def load_snapshot(
        self,
        line_user_id: str,
        business_id: int | None = None,
        business_name: str | None = None,
        task_id: int | str | None = None,
    ) -> RepositorySnapshot:
        ...


BUSINESS_BY_LINE_USER_SQL = """
SELECT b.id, b.name, b.branch_name
FROM clients c
JOIN business b ON b.client_id = c.id
WHERE c.line_user_id = %s
  AND c.status = 'active'
  AND b.status = 'active'
ORDER BY b.id
LIMIT 1
"""

BUSINESS_BY_ID_SQL = """
SELECT b.id, b.name, b.branch_name
FROM clients c
JOIN business b ON b.client_id = c.id
WHERE c.line_user_id = %s
  AND b.id = %s
  AND c.status = 'active'
  AND b.status = 'active'
LIMIT 1
"""

BUSINESS_BY_NAME_SQL = """
SELECT b.id, b.name, b.branch_name
FROM clients c
JOIN business b ON b.client_id = c.id
WHERE c.line_user_id = %s
  AND lower(btrim(b.name)) = lower(btrim(%s))
  AND c.status = 'active'
  AND b.status = 'active'
ORDER BY b.id
LIMIT 1
"""

BUSINESS_BY_TASK_SQL = """
SELECT b.id, b.name, b.branch_name
FROM clients c
JOIN business b ON b.client_id = c.id
JOIN service_tasks st ON st.business_id = b.id
WHERE c.line_user_id = %s
  AND st.id = %s
  AND st.service_type = 'reputation_monitoring'
  AND c.status = 'active'
  AND b.status = 'active'
LIMIT 1
"""

CRAWL_STATUS_COUNTS_SQL = """
SELECT status, COUNT(*)::integer AS count
FROM crawl_jobs
WHERE service_task_id = %s
GROUP BY status
"""

BUSINESS_TARGETS_SQL = """
WITH targets AS (
    SELECT
        st.business_id,
        'crawl_post'::text AS target_type,
        cp.id AS target_id,
        COALESCE(NULLIF(lower(cj.platform), ''), 'unknown') AS platform,
        cp.updated_at AS observed_at
    FROM crawl_posts cp
    JOIN crawl_jobs cj ON cj.id = cp.crawl_job_id
    JOIN service_tasks st ON st.id = cj.service_task_id
    WHERE st.business_id = %s
      AND st.status <> 'cancelled'
      AND cj.status <> 'cancelled'
      AND cp.is_deleted = false

    UNION ALL

    SELECT
        st.business_id,
        'crawl_comment'::text AS target_type,
        cc.id AS target_id,
        COALESCE(NULLIF(lower(cj.platform), ''), 'unknown') AS platform,
        cc.updated_at AS observed_at
    FROM crawl_comments cc
    JOIN crawl_posts cp ON cp.id = cc.crawl_post_id
    JOIN crawl_jobs cj ON cj.id = cp.crawl_job_id
    JOIN service_tasks st ON st.id = cj.service_task_id
    WHERE st.business_id = %s
      AND st.status <> 'cancelled'
      AND cj.status <> 'cancelled'
      AND cp.is_deleted = false
      AND cc.is_deleted = false
)
"""

TASK_TARGETS_SQL = """
WITH targets AS (
    SELECT
        st.business_id,
        'crawl_post'::text AS target_type,
        cp.id AS target_id,
        COALESCE(NULLIF(lower(cj.platform), ''), 'unknown') AS platform,
        cp.updated_at AS observed_at
    FROM service_tasks st
    JOIN crawl_jobs cj ON cj.service_task_id = st.id
    JOIN crawl_posts cp ON cp.crawl_job_id = cj.id
    WHERE st.id = %s
      AND cj.status <> 'cancelled'
      AND cp.is_deleted = false

    UNION ALL

    SELECT
        st.business_id,
        'crawl_comment'::text AS target_type,
        cc.id AS target_id,
        COALESCE(NULLIF(lower(cj.platform), ''), 'unknown') AS platform,
        cc.updated_at AS observed_at
    FROM service_tasks st
    JOIN crawl_jobs cj ON cj.service_task_id = st.id
    JOIN crawl_posts cp ON cp.crawl_job_id = cj.id
    JOIN crawl_comments cc ON cc.crawl_post_id = cp.id
    WHERE st.id = %s
      AND cj.status <> 'cancelled'
      AND cp.is_deleted = false
      AND cc.is_deleted = false
)
"""

LATEST_SUMMARY_SELECT_SQL = """
,
latest_analysis AS (
    SELECT DISTINCT ON (ar.target_type, ar.target_id)
        ar.target_type,
        ar.target_id,
        ar.summary,
        ar.analyzed_at,
        ar.id
    FROM analysis_results ar
    WHERE {valid_analysis_predicate}
    ORDER BY ar.target_type, ar.target_id, ar.analyzed_at DESC, ar.id DESC
)
SELECT la.summary
FROM targets target
JOIN latest_analysis la
  ON la.target_type = target.target_type
 AND la.target_id = target.target_id
WHERE la.summary IS NOT NULL
  AND btrim(la.summary) <> ''
ORDER BY la.analyzed_at DESC, la.id DESC
LIMIT 1
"""

PLATFORM_STATS_SELECT_SQL = """
,
latest_analysis AS (
    SELECT DISTINCT ON (ar.target_type, ar.target_id)
        ar.target_type,
        ar.target_id,
        ar.sentiment,
        ar.sentiment_score,
        ar.risk_level,
        {risk_score_expression} AS risk_score,
        {risk_points_expression} AS risk_points,
        ar.analyzed_at
    FROM analysis_results ar
    WHERE {valid_analysis_predicate}
    ORDER BY ar.target_type, ar.target_id, ar.analyzed_at DESC, ar.id DESC
),
joined AS (
    SELECT
        target.platform,
        target.observed_at,
        la.target_id IS NOT NULL AS is_analyzed,
        COALESCE(la.sentiment, 'unclassified') AS sentiment,
        la.risk_level,
        la.risk_score,
        la.risk_points,
        la.analyzed_at
    FROM targets target
    LEFT JOIN latest_analysis la
      ON la.target_type = target.target_type
     AND la.target_id = target.target_id
)
SELECT
    platform,
    COUNT(*)::integer AS total,
    COUNT(*) FILTER (WHERE is_analyzed)::integer AS analyzed,
    COUNT(*) FILTER (WHERE sentiment = 'positive')::integer AS positive,
    COUNT(*) FILTER (WHERE sentiment = 'neutral')::integer AS neutral,
    COUNT(*) FILTER (WHERE sentiment = 'negative')::integer AS negative,
    COUNT(*) FILTER (
        WHERE NOT is_analyzed OR sentiment NOT IN ('positive', 'neutral', 'negative')
    )::integer AS unclassified,
    AVG(risk_score)::float AS risk_score,
    COUNT(risk_score)::integer AS risk_score_count,
    SUM(risk_points)::integer AS risk_points,
    MAX(
        CASE risk_level
            WHEN 'high' THEN 3
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
        END
    )::integer AS risk_rank,
    GREATEST(MAX(observed_at), MAX(analyzed_at)) AS updated_at
FROM joined
GROUP BY platform
ORDER BY
    CASE platform
        WHEN 'ptt' THEN 1
        WHEN 'threads' THEN 2
        WHEN 'google_maps' THEN 3
        ELSE 99
    END,
    platform
"""

VALID_ANALYSIS_PREDICATE = """
(
    ar.analysis_status = 'completed'
    OR (
        ar.analysis_status IS NULL
        AND (
            ar.sentiment IS NOT NULL
            OR ar.risk_level IS NOT NULL
            OR NULLIF(btrim(ar.summary), '') IS NOT NULL
            {legacy_numeric_clause}
        )
    )
)
"""


def _latest_summary_sql(*, report_scope: str) -> str:
    return _targets_sql(report_scope) + LATEST_SUMMARY_SELECT_SQL.format(
        valid_analysis_predicate=_valid_analysis_predicate(include_numeric_risk=False),
    )


def _platform_stats_sql(*, report_scope: str, include_numeric_risk: bool) -> str:
    risk_score_expression = "ar.risk_score" if include_numeric_risk else "NULL::numeric"
    risk_points_expression = "ar.risk_points" if include_numeric_risk else "NULL::integer"

    return _targets_sql(report_scope) + PLATFORM_STATS_SELECT_SQL.format(
        risk_score_expression=risk_score_expression,
        risk_points_expression=risk_points_expression,
        valid_analysis_predicate=_valid_analysis_predicate(
            include_numeric_risk=include_numeric_risk
        ),
    )


def _targets_sql(report_scope: str) -> str:
    if report_scope == "task":
        return TASK_TARGETS_SQL
    if report_scope == "business":
        return BUSINESS_TARGETS_SQL
    raise ValueError(f"unsupported reputation report scope: {report_scope}")


def _valid_analysis_predicate(*, include_numeric_risk: bool) -> str:
    legacy_numeric_clause = (
        "\n            OR ar.risk_score IS NOT NULL\n            OR ar.risk_points IS NOT NULL"
        if include_numeric_risk
        else ""
    )
    return VALID_ANALYSIS_PREDICATE.format(legacy_numeric_clause=legacy_numeric_clause)


class PostgresReputationRepository:
    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self._connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        if psycopg2 is None:
            raise DatabaseConfigurationError("psycopg2 is required for the reputation summary API")

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise DatabaseConfigurationError("DATABASE_URL is required for the reputation summary API")

        return psycopg2.connect(database_url, connect_timeout=10)

    def load_snapshot(
        self,
        line_user_id: str,
        business_id: int | None = None,
        business_name: str | None = None,
        task_id: int | str | None = None,
    ) -> RepositorySnapshot:
        conn = self._connection_factory()
        try:
            resolved_task_id = str(task_id) if task_id is not None else None
            business = self._resolve_business(
                conn,
                line_user_id=line_user_id,
                business_id=business_id,
                business_name=business_name,
                task_id=resolved_task_id,
            )
            report_scope = "task" if resolved_task_id is not None else "business"
            scope_id = resolved_task_id if resolved_task_id is not None else business.id
            rows, numeric_risk_available = self._load_platform_rows(
                conn,
                report_scope=report_scope,
                scope_id=scope_id,
            )
            latest_summary = self._load_latest_summary(
                conn,
                report_scope=report_scope,
                scope_id=scope_id,
            )
            crawl_status_counts = (
                self._load_crawl_status_counts(conn, resolved_task_id)
                if resolved_task_id is not None
                else {}
            )
            return RepositorySnapshot(
                business=business,
                platform_rows=rows,
                latest_summary=latest_summary,
                numeric_risk_available=numeric_risk_available,
                report_scope=report_scope,
                task_id=resolved_task_id,
                crawl_status_counts=crawl_status_counts,
            )
        finally:
            conn.close()

    @staticmethod
    def _resolve_business(
        conn: Any,
        *,
        line_user_id: str,
        business_id: int | None,
        business_name: str | None,
        task_id: str | None,
    ) -> BusinessRecord:
        if task_id is not None:
            query = BUSINESS_BY_TASK_SQL
            params: tuple[Any, ...] = (line_user_id, task_id)
        elif business_id is not None:
            query = BUSINESS_BY_ID_SQL
            params = (line_user_id, business_id)
        elif business_name:
            query = BUSINESS_BY_NAME_SQL
            params = (line_user_id, business_name)
        else:
            query = BUSINESS_BY_LINE_USER_SQL
            params = (line_user_id,)

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()

        if not row:
            raise BusinessNotFoundError("reputation report not found")

        return BusinessRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            branch_name=row.get("branch_name"),
        )

    @staticmethod
    def _load_platform_rows(
        conn: Any,
        *,
        report_scope: str,
        scope_id: int | str,
    ) -> tuple[list[dict[str, Any]], bool]:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    _platform_stats_sql(
                        report_scope=report_scope,
                        include_numeric_risk=True,
                    ),
                    (scope_id, scope_id),
                )
                return list(cursor.fetchall()), True
        except Exception as exc:
            if getattr(exc, "pgcode", None) != "42703":
                raise

            conn.rollback()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    _platform_stats_sql(
                        report_scope=report_scope,
                        include_numeric_risk=False,
                    ),
                    (scope_id, scope_id),
                )
                return list(cursor.fetchall()), False

    @staticmethod
    def _load_latest_summary(
        conn: Any,
        *,
        report_scope: str,
        scope_id: int | str,
    ) -> str | None:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(_latest_summary_sql(report_scope=report_scope), (scope_id, scope_id))
            row = cursor.fetchone()
        return str(row["summary"]).strip() if row and row.get("summary") else None

    @staticmethod
    def _load_crawl_status_counts(conn: Any, task_id: str) -> dict[str, int]:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(CRAWL_STATUS_COUNTS_SQL, (task_id,))
            rows = cursor.fetchall()
        return {str(row["status"]): int(row["count"] or 0) for row in rows}


PLATFORM_LABELS = {
    "ptt": "PTT",
    "threads": "Threads",
    "google_maps": "Google Maps",
}

RISK_LEVEL_BY_RANK = {1: "low", 2: "medium", 3: "high"}


class ReputationSummaryService:
    def __init__(self, repository: SnapshotRepository) -> None:
        self._repository = repository

    def build_summary(
        self,
        line_user_id: str,
        business_id: int | None = None,
        business_name: str | None = None,
        task_id: int | str | None = None,
    ) -> dict[str, Any]:
        load_kwargs: dict[str, Any] = {"line_user_id": line_user_id}
        if business_id is not None:
            load_kwargs["business_id"] = business_id
        if business_name:
            load_kwargs["business_name"] = business_name
        if task_id is not None:
            load_kwargs["task_id"] = task_id
        snapshot = self._repository.load_snapshot(**load_kwargs)
        config = load_reputation_scoring_config()
        platforms = [self._to_platform_summary(row) for row in snapshot.platform_rows]
        overview = self._build_overview(platforms, snapshot.latest_summary)
        included_platforms = [platform.platform for platform in platforms if platform.total > 0]
        expected_platforms = ["google_maps", "ptt", "threads"]
        missing_platforms = [platform for platform in expected_platforms if platform not in included_platforms]
        coverage_ratio = round(len(included_platforms) / len(expected_platforms), 4) if expected_platforms else 0.0
        data_status = _data_status(
            total_reviews=overview.total_reviews,
            crawl_status_counts=snapshot.crawl_status_counts or {},
        )

        return {
            "status": data_status,
            "analysis_mode": config["analysis"]["mode"],
            "scoring_version": config["version"],
            "business": {
                "id": snapshot.business.id,
                "name": snapshot.business.name,
                "branch_name": snapshot.business.branch_name,
                "display_name": snapshot.business.display_name,
            },
            "overview": overview.to_dict(),
            "overall": {
                "score_status": _score_status(overview.analyzed_reviews, overview.total_reviews),
                "provisional_score": None,
                "unified_score": None,
                "provisional_rating": None,
                "unified_rating": None,
                "coverage_ratio": coverage_ratio,
                "included_platforms": included_platforms,
                "missing_platforms": missing_platforms,
                "data_status": data_status,
                "crawl_status_counts": snapshot.crawl_status_counts or {},
            },
            "platforms": [platform.to_dict() for platform in platforms],
            "data_contract": {
                "sentiment_field": "analysis_results.sentiment",
                "risk_score_field": "analysis_results.risk_score",
                "risk_points_field": "analysis_results.risk_points",
                "numeric_risk_available": snapshot.numeric_risk_available,
                "report_scope": snapshot.report_scope,
                "source_tables": [
                    "public.clients",
                    "public.business",
                    "public.service_tasks",
                    "public.crawl_jobs",
                    "public.crawl_posts",
                    "public.crawl_comments",
                    "public.analysis_results",
                ],
            },
        }

    @staticmethod
    def _to_platform_summary(row: dict[str, Any]) -> PlatformSummary:
        platform = str(row.get("platform") or "unknown")
        risk_rank = int(row.get("risk_rank") or 0)
        raw_risk_score = row.get("risk_score")
        raw_risk_points = row.get("risk_points")

        return PlatformSummary(
            platform=platform,
            label=PLATFORM_LABELS.get(platform, platform.replace("_", " ").title()),
            total=int(row.get("total") or 0),
            analyzed=int(row.get("analyzed") or 0),
            positive=int(row.get("positive") or 0),
            neutral=int(row.get("neutral") or 0),
            negative=int(row.get("negative") or 0),
            unclassified=int(row.get("unclassified") or 0),
            risk_score=round(float(raw_risk_score), 1) if raw_risk_score is not None else None,
            risk_score_count=int(row.get("risk_score_count") or 0),
            risk_points=int(raw_risk_points) if raw_risk_points is not None else None,
            risk_level=RISK_LEVEL_BY_RANK.get(risk_rank),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _build_overview(
        platforms: list[PlatformSummary], latest_summary: str | None
    ) -> ReputationOverview:
        total_reviews = sum(item.total for item in platforms)
        analyzed_reviews = sum(item.analyzed for item in platforms)
        positive = sum(item.positive for item in platforms)
        neutral = sum(item.neutral for item in platforms)
        negative = sum(item.negative for item in platforms)
        unclassified = sum(item.unclassified for item in platforms)

        scored_platforms = [
            item for item in platforms if item.risk_score is not None and item.risk_score_count > 0
        ]
        scored_count = sum(item.risk_score_count for item in scored_platforms)
        risk_score = None
        if scored_count:
            risk_score = round(
                sum((item.risk_score or 0.0) * item.risk_score_count for item in scored_platforms)
                / scored_count,
                1,
            )

        risk_points_values = [item.risk_points for item in platforms if item.risk_points is not None]
        risk_points = sum(risk_points_values) if risk_points_values else None

        risk_level = None
        for candidate in ("high", "medium", "low"):
            if any(item.risk_level == candidate for item in platforms):
                risk_level = candidate
                break

        updated_values = [item.updated_at for item in platforms if item.updated_at is not None]
        updated_at = max(updated_values) if updated_values else None

        summary = latest_summary or ReputationSummaryService._fallback_summary(
            total_reviews=total_reviews,
            positive=positive,
            neutral=neutral,
            negative=negative,
        )

        return ReputationOverview(
            total_reviews=total_reviews,
            analyzed_reviews=analyzed_reviews,
            positive=positive,
            neutral=neutral,
            negative=negative,
            unclassified=unclassified,
            risk_score=risk_score,
            risk_points=risk_points,
            risk_level=risk_level,
            summary=summary,
            updated_at=updated_at,
        )

    @staticmethod
    def _fallback_summary(*, total_reviews: int, positive: int, neutral: int, negative: int) -> str:
        if total_reviews == 0:
            return "目前尚未收集到可用的網路評價資料。"
        if negative > positive:
            return "目前負面評價比例偏高，建議優先檢視近期留言與主要負評來源。"
        if positive > negative:
            return "目前整體評價偏正面，仍建議持續關注新增負評與風險變化。"
        if neutral >= max(positive, negative):
            return "目前網路評價以中立內容為主，建議持續累積資料後再觀察趨勢。"
        return "目前正負評價接近，建議持續追蹤近期評論變化。"


def _score_status(analyzed_reviews: int, total_reviews: int) -> str:
    if total_reviews <= 0:
        return "insufficient_data"
    if analyzed_reviews <= 0:
        return "provisional"
    return "complete"


def _data_status(*, total_reviews: int, crawl_status_counts: dict[str, int]) -> str:
    if total_reviews <= 0:
        return "no_data"
    failed = sum(crawl_status_counts.get(status, 0) for status in ("failed", "timeout"))
    succeeded = sum(
        crawl_status_counts.get(status, 0)
        for status in ("success", "completed", "partial_success")
    )
    if failed:
        return "partial" if succeeded else "partial"
    return "complete"
