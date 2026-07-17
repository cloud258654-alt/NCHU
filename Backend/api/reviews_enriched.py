from __future__ import annotations

import os
import re
from typing import Any

from api.enriched_reputation import EnrichedReviewRepository, EnrichedSnapshot
from api.models import BusinessRecord
from api.reputation import DatabaseConfigurationError

_REPORT_RELATION_NAME = "reviews_enriched"
_GLOBAL_REPORT_BUSINESS = BusinessRecord(id=0, name="全體評論", branch_name=None)
_REQUIRED_REVIEW_COLUMNS = frozenset({"review_id", "platform", "sentiment_label"})
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ReviewsEnrichedRepository(EnrichedReviewRepository):
    """Aggregate every row in the shared public.reviews_enriched relation."""

    def resolve_business(
        self,
        *,
        line_user_id: str,
        business_name: str | None = None,
        business_id: int | None = None,
    ) -> BusinessRecord:
        del line_user_id, business_name, business_id
        return _GLOBAL_REPORT_BUSINESS

    def load_snapshot(
        self,
        *,
        line_user_id: str,
        business_name: str | None = None,
        business_id: int | None = None,
    ) -> EnrichedSnapshot:
        del line_user_id, business_name, business_id
        conn = self._connection_factory()
        try:
            schema_name, table_name = _configured_reviews_enriched_relation()
            columns = self._load_relation_columns(
                conn,
                schema_name=schema_name,
                table_name=table_name,
            )
            _validate_reviews_enriched_columns(columns)
            platform_rows, latest_summary = self._load_quantitative_rows(
                conn,
                schema_name=schema_name,
                table_name=table_name,
                columns=columns,
            )
            return EnrichedSnapshot(
                business=_GLOBAL_REPORT_BUSINESS,
                platform_rows=platform_rows,
                latest_summary=latest_summary,
                numeric_risk_available=any(
                    int(row.get("risk_score_count") or 0) > 0
                    for row in platform_rows
                ),
                source_table=f"{schema_name}.{table_name}",
            )
        finally:
            conn.close()

    @staticmethod
    def _load_relation_columns(
        conn: Any,
        *,
        schema_name: str,
        table_name: str,
    ) -> set[str]:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema_name, table_name),
            )
            columns = {str(row[0]) for row in cursor.fetchall()}

        if not columns:
            raise DatabaseConfigurationError(
                f"找不到或無法讀取量化報告來源：{schema_name}.{table_name}"
            )
        return columns

    @staticmethod
    def _load_quantitative_rows(
        conn: Any,
        *,
        schema_name: str,
        table_name: str,
        columns: set[str],
    ) -> tuple[list[dict[str, Any]], str | None]:
        query = _build_reviews_enriched_quantitative_sql(
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
        )

        with conn.cursor() as cursor:
            cursor.execute(query)
            names = [_description_name(item) for item in cursor.description or []]
            rows = [
                dict(zip(names, row, strict=False))
                for row in cursor.fetchall()
            ]
        return rows, None


def _configured_reviews_enriched_relation() -> tuple[str, str]:
    configured = os.getenv(
        "BI_RMP_ENRICHED_REVIEW_TABLE",
        "public.reviews_enriched",
    ).strip()
    if "." in configured:
        schema_name, table_name = configured.split(".", 1)
    else:
        schema_name, table_name = "public", configured

    schema_name = schema_name.strip() or "public"
    table_name = table_name.strip()
    if table_name != _REPORT_RELATION_NAME:
        raise DatabaseConfigurationError(
            "BI_RMP_ENRICHED_REVIEW_TABLE 必須指向 reviews_enriched；"
            "此報告只讀取該 relation 的全部資料"
        )
    if not _IDENTIFIER_PATTERN.fullmatch(schema_name):
        raise DatabaseConfigurationError("reviews_enriched schema 名稱格式不合法")
    return schema_name, table_name


def _validate_reviews_enriched_columns(columns: set[str]) -> None:
    missing = sorted(_REQUIRED_REVIEW_COLUMNS.difference(columns))
    if missing:
        raise DatabaseConfigurationError(
            "public.reviews_enriched 缺少必要欄位：" + ", ".join(missing)
        )


def _build_reviews_enriched_quantitative_sql(
    *,
    schema_name: str,
    table_name: str,
    columns: set[str],
) -> str:
    _validate_reviews_enriched_columns(columns)
    relation = f"{_quote_identifier(schema_name)}.{_quote_identifier(table_name)}"

    platform_column = _quote_identifier("platform")
    sentiment_column = _quote_identifier("sentiment_label")
    normalized_platform = (
        f"lower(replace(replace(btrim({platform_column}::text), '-', '_'), ' ', '_'))"
    )
    platform_expression = f"""
        CASE {normalized_platform}
            WHEN 'google' THEN 'google_maps'
            WHEN 'googlemaps' THEN 'google_maps'
            WHEN 'google_map' THEN 'google_maps'
            WHEN 'google_maps_reviews' THEN 'google_maps'
            ELSE COALESCE(NULLIF({normalized_platform}, ''), 'unknown')
        END
    """
    normalized_sentiment = f"lower(btrim({sentiment_column}::text))"
    sentiment_expression = f"""
        CASE
            WHEN {normalized_sentiment} IN ('positive', 'pos', '正面', '正向', '好評')
                THEN 'positive'
            WHEN {normalized_sentiment} IN ('neutral', 'neu', '中立', '普通')
                THEN 'neutral'
            WHEN {normalized_sentiment} IN ('negative', 'neg', '負面', '負向', '負評')
                THEN 'negative'
            ELSE NULL
        END
    """

    risk_score_expression = _safe_numeric_expression("risk_score", columns)
    risk_level_expression = _risk_level_expression(columns)
    updated_at_expression = _first_timestamp_expression(
        columns,
        "analyzed_at",
        "review_time",
    )

    return f"""
        WITH all_reviews AS (
            SELECT
                {platform_expression} AS platform,
                {sentiment_expression} AS sentiment,
                {risk_score_expression} AS risk_score,
                NULL::integer AS risk_points,
                {risk_level_expression} AS risk_level,
                {updated_at_expression} AS updated_at
            FROM {relation}
        )
        SELECT
            platform,
            COUNT(*)::integer AS total,
            COUNT(sentiment)::integer AS analyzed,
            COUNT(*) FILTER (WHERE sentiment = 'positive')::integer AS positive,
            COUNT(*) FILTER (WHERE sentiment = 'neutral')::integer AS neutral,
            COUNT(*) FILTER (WHERE sentiment = 'negative')::integer AS negative,
            COUNT(*) FILTER (WHERE sentiment IS NULL)::integer AS unclassified,
            AVG(risk_score)::float8 AS risk_score,
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
            MAX(updated_at) AS updated_at,
            NULL::text AS latest_summary
        FROM all_reviews
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


def _safe_numeric_expression(column: str, columns: set[str]) -> str:
    if column not in columns:
        return "NULL::numeric"
    identifier = _quote_identifier(column)
    value = f"btrim({identifier}::text)"
    return (
        f"CASE WHEN {value} ~ '^-?[0-9]+([.][0-9]+)?$' "
        f"THEN {value}::numeric ELSE NULL END"
    )


def _risk_level_expression(columns: set[str]) -> str:
    if "risk_level" not in columns:
        return "NULL::text"
    identifier = _quote_identifier("risk_level")
    normalized = f"lower(btrim({identifier}::text))"
    return f"""
        CASE
            WHEN {normalized} IN ('high', 'h', '高', '高風險', '高度', '嚴重') THEN 'high'
            WHEN {normalized} IN ('medium', 'mid', 'm', '中', '中風險', '中度') THEN 'medium'
            WHEN {normalized} IN ('low', 'l', '低', '低風險', '低度') THEN 'low'
            ELSE NULL
        END
    """


def _first_timestamp_expression(columns: set[str], *candidates: str) -> str:
    for column in candidates:
        if column in columns:
            return f"{_quote_identifier(column)}::timestamptz"
    return "NULL::timestamptz"


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise DatabaseConfigurationError(f"SQL identifier 格式不合法：{value}")
    return f'"{value}"'


def _description_name(description: Any) -> str:
    name = getattr(description, "name", None)
    if name:
        return str(name)
    return str(description[0])
