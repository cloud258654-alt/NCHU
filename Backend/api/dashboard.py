from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ModuleNotFoundError:  # pragma: no cover - raised as a config error at runtime
    psycopg2 = None
    RealDictCursor = None

from api.reputation import DatabaseConfigurationError

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class DashboardRepository:
    """Read-only dashboard repository backed by the BI-RMP runtime schema."""

    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self._connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        if psycopg2 is None:
            raise DatabaseConfigurationError("psycopg2 is required for dashboard API")

        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise DatabaseConfigurationError("DATABASE_URL is required for dashboard API")

        return psycopg2.connect(database_url, connect_timeout=10)

    def list_businesses(self) -> list[dict[str, Any]]:
        conn = self._connection_factory()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT
                        b.id,
                        b.name,
                        b.branch_name,
                        b.industry,
                        b.status,
                        COUNT(DISTINCT cp.id)::integer AS review_count,
                        MAX(cp.updated_at) AS latest_review_at
                    FROM business b
                    LEFT JOIN service_tasks st ON st.business_id = b.id
                    LEFT JOIN crawl_jobs cj ON cj.service_task_id = st.id
                    LEFT JOIN crawl_posts cp ON cp.crawl_job_id = cj.id
                    GROUP BY b.id, b.name, b.branch_name, b.industry, b.status
                    ORDER BY b.updated_at DESC, b.id DESC
                    """
                )
                return [_serialize_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_summary(self, *, business_id: int | None = None) -> dict[str, Any]:
        business_count = self._count_businesses(business_id=business_id)
        conn = self._connection_factory()
        try:
            where_clause = "WHERE st.business_id = %s" if business_id is not None else ""
            params: tuple[Any, ...] = (business_id, business_id) if business_id is not None else ()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""
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
                        {where_clause}

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
                        {where_clause}
                    ),
                    latest_analysis AS (
                        SELECT DISTINCT ON (ar.target_type, ar.target_id)
                            ar.target_type,
                            ar.target_id,
                            ar.sentiment,
                            ar.risk_level,
                            ar.analyzed_at
                        FROM analysis_results ar
                        WHERE ar.analysis_status = 'completed'
                        ORDER BY ar.target_type, ar.target_id, ar.analyzed_at DESC, ar.created_at DESC, ar.id DESC
                    ),
                    joined AS (
                        SELECT
                            target.*,
                            la.target_id IS NOT NULL AS is_analyzed,
                            COALESCE(la.sentiment, 'unclassified') AS sentiment,
                            la.risk_level,
                            la.analyzed_at
                        FROM targets target
                        LEFT JOIN latest_analysis la
                          ON la.target_type = target.target_type
                         AND la.target_id = target.target_id
                    )
                    SELECT
                        COUNT(*)::integer AS total_items,
                        COUNT(*) FILTER (WHERE target_type = 'crawl_post')::integer AS total_reviews,
                        COUNT(*) FILTER (WHERE target_type = 'crawl_comment')::integer AS total_comments,
                        COUNT(*) FILTER (WHERE is_analyzed)::integer AS analyzed_items,
                        COUNT(*) FILTER (WHERE sentiment = 'positive')::integer AS positive,
                        COUNT(*) FILTER (WHERE sentiment = 'neutral')::integer AS neutral,
                        COUNT(*) FILTER (WHERE sentiment = 'negative')::integer AS negative,
                        COUNT(*) FILTER (
                            WHERE NOT is_analyzed
                               OR sentiment NOT IN ('positive', 'neutral', 'negative')
                        )::integer AS unclassified,
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
                    """,
                    params,
                )
                row = cursor.fetchone() or {}
        finally:
            conn.close()

        summary = _serialize_row(row)
        summary["total_businesses"] = business_count
        summary["risk_level"] = _risk_level_from_rank(summary.pop("risk_rank", None))
        return summary

    def list_reviews(
        self,
        *,
        page: int,
        page_size: int,
        business_id: int | None = None,
        platform: str | None = None,
    ) -> dict[str, Any]:
        filters = []
        params: list[Any] = []
        if business_id is not None:
            filters.append("st.business_id = %s")
            params.append(business_id)
        if platform:
            filters.append("lower(cj.platform) = lower(%s)")
            params.append(platform)
        where_clause = "WHERE " + " AND ".join(filters) if filters else ""
        offset = (page - 1) * page_size

        conn = self._connection_factory()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""
                    WITH latest_analysis AS (
                        SELECT DISTINCT ON (ar.target_id)
                            ar.target_id,
                            ar.sentiment,
                            ar.risk_level,
                            ar.summary,
                            COALESCE(NULLIF(ar.score_explanation->>'critical', '')::boolean, false) AS critical,
                            COALESCE(ar.score_explanation->'critical_signals', '[]'::jsonb) AS critical_signals,
                            NULLIF(ar.score_explanation->>'escalation_level', '') AS escalation_level,
                            COALESCE(
                                NULLIF(ar.score_explanation->'rules_baseline'->>'human_review_required', '')::boolean,
                                false
                            ) AS human_review_required,
                            ar.analyzed_at
                        FROM analysis_results ar
                        WHERE ar.target_type = 'crawl_post'
                          AND ar.analysis_status = 'completed'
                        ORDER BY ar.target_id, ar.analyzed_at DESC, ar.created_at DESC, ar.id DESC
                    )
                    SELECT
                        cp.id,
                        st.business_id,
                        b.name AS business_name,
                        cj.platform,
                        cp.title,
                        cp.author_name,
                        cp.content,
                        cp.link,
                        cp.published_at,
                        cp.updated_at,
                        la.sentiment,
                        la.risk_level,
                        la.summary,
                        la.critical,
                        la.critical_signals,
                        la.escalation_level,
                        la.human_review_required,
                        COUNT(*) OVER()::integer AS total_count
                    FROM crawl_posts cp
                    JOIN crawl_jobs cj ON cj.id = cp.crawl_job_id
                    JOIN service_tasks st ON st.id = cj.service_task_id
                    JOIN business b ON b.id = st.business_id
                    LEFT JOIN latest_analysis la ON la.target_id = cp.id
                    {where_clause}
                    ORDER BY cp.updated_at DESC, cp.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*params, page_size, offset),
                )
                rows = [_serialize_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

        total = int(rows[0].pop("total_count", 0)) if rows else 0
        for row in rows:
            row.pop("total_count", None)
        return {
            "items": rows,
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    def get_review(self, review_id: int) -> dict[str, Any] | None:
        conn = self._connection_factory()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    WITH latest_analysis AS (
                        SELECT DISTINCT ON (ar.target_id)
                            ar.target_id,
                            ar.sentiment,
                            ar.risk_level,
                            ar.summary,
                            ar.recommendation,
                            COALESCE(NULLIF(ar.score_explanation->>'critical', '')::boolean, false) AS critical,
                            COALESCE(ar.score_explanation->'critical_signals', '[]'::jsonb) AS critical_signals,
                            NULLIF(ar.score_explanation->>'escalation_level', '') AS escalation_level,
                            COALESCE(
                                NULLIF(ar.score_explanation->'rules_baseline'->>'human_review_required', '')::boolean,
                                false
                            ) AS human_review_required,
                            ar.analyzed_at
                        FROM analysis_results ar
                        WHERE ar.target_type = 'crawl_post'
                          AND ar.analysis_status = 'completed'
                        ORDER BY ar.target_id, ar.analyzed_at DESC, ar.created_at DESC, ar.id DESC
                    )
                    SELECT
                        cp.id,
                        st.business_id,
                        b.name AS business_name,
                        cj.platform,
                        cp.platform_post_id,
                        cp.title,
                        cp.author_id,
                        cp.author_name,
                        cp.content,
                        cp.link,
                        cp.published_at,
                        cp.like_count,
                        cp.comment_count,
                        cp.share_count,
                        cp.view_count,
                        cp.reaction_count,
                        cp.extra_data,
                        cp.created_at,
                        cp.updated_at,
                        la.sentiment,
                        la.risk_level,
                        la.summary,
                        la.recommendation,
                        la.critical,
                        la.critical_signals,
                        la.escalation_level,
                        la.human_review_required,
                        la.analyzed_at
                    FROM crawl_posts cp
                    JOIN crawl_jobs cj ON cj.id = cp.crawl_job_id
                    JOIN service_tasks st ON st.id = cj.service_task_id
                    JOIN business b ON b.id = st.business_id
                    LEFT JOIN latest_analysis la ON la.target_id = cp.id
                    WHERE cp.id = %s
                    LIMIT 1
                    """,
                    (review_id,),
                )
                row = cursor.fetchone()
                return _serialize_row(row) if row else None
        finally:
            conn.close()

    def _count_businesses(self, *, business_id: int | None = None) -> int:
        conn = self._connection_factory()
        try:
            query = "SELECT COUNT(*)::integer AS count FROM business"
            params: tuple[Any, ...] = ()
            if business_id is not None:
                query += " WHERE id = %s"
                params = (business_id,)
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone() or {}
                return int(row.get("count") or 0)
        finally:
            conn.close()


def get_dashboard_repository() -> DashboardRepository:
    return DashboardRepository()


@router.get("/businesses")
def list_dashboard_businesses(
    repo: DashboardRepository = Depends(get_dashboard_repository),
) -> list[dict[str, Any]]:
    try:
        return repo.list_businesses()
    except DatabaseConfigurationError as exc:
        raise _dashboard_config_error() from exc
    except Exception as exc:
        raise _dashboard_unavailable_error() from exc


@router.get("/summary")
def get_dashboard_summary(
    business_id: int | None = Query(default=None, gt=0),
    repo: DashboardRepository = Depends(get_dashboard_repository),
) -> dict[str, Any]:
    try:
        return repo.get_summary(business_id=business_id)
    except DatabaseConfigurationError as exc:
        raise _dashboard_config_error() from exc
    except Exception as exc:
        raise _dashboard_unavailable_error() from exc


@router.get("/reviews")
def list_dashboard_reviews(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    business_id: int | None = Query(default=None, gt=0),
    platform: str | None = Query(default=None, min_length=1, max_length=64),
    repo: DashboardRepository = Depends(get_dashboard_repository),
) -> dict[str, Any]:
    try:
        return repo.list_reviews(
            page=page,
            page_size=page_size,
            business_id=business_id,
            platform=platform,
        )
    except DatabaseConfigurationError as exc:
        raise _dashboard_config_error() from exc
    except Exception as exc:
        raise _dashboard_unavailable_error() from exc


@router.get("/reviews/{review_id}")
def get_dashboard_review(
    review_id: int = Path(gt=0),
    repo: DashboardRepository = Depends(get_dashboard_repository),
) -> dict[str, Any]:
    try:
        review = repo.get_review(review_id)
    except DatabaseConfigurationError as exc:
        raise _dashboard_config_error() from exc
    except Exception as exc:
        raise _dashboard_unavailable_error() from exc
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard review was not found",
        )
    return review


def _serialize_row(row: Any) -> dict[str, Any]:
    output = dict(row or {})
    for key, value in list(output.items()):
        if isinstance(value, (datetime, date)):
            output[key] = value.isoformat()
    return output


def _risk_level_from_rank(value: Any) -> str | None:
    try:
        rank = int(value or 0)
    except (TypeError, ValueError):
        return None
    return {1: "low", 2: "medium", 3: "high"}.get(rank)


def _dashboard_config_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Dashboard database is not configured",
    )


def _dashboard_unavailable_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Dashboard data is unavailable",
    )
