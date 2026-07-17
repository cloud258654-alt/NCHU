from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable

try:
    import psycopg2
    from psycopg2 import sql
except ModuleNotFoundError:  # pragma: no cover - surfaced as configuration error at runtime
    psycopg2 = None
    sql = None

from api.models import BusinessRecord
from api.reputation import (
    BusinessNotFoundError,
    DatabaseConfigurationError,
    ReputationSummaryService,
)


@dataclass(frozen=True)
class EnrichedSnapshot:
    business: BusinessRecord
    platform_rows: list[dict[str, Any]]
    latest_summary: str | None
    numeric_risk_available: bool
    source_table: str


@dataclass
class _PlatformAccumulator:
    total: int = 0
    analyzed: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    unclassified: int = 0
    risk_score_weighted_sum: float = 0.0
    risk_score_count: int = 0
    risk_points: int = 0
    has_risk_points: bool = False
    risk_rank: int = 0
    updated_at: datetime | None = None


_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "business_id": ("business_id", "shop_id", "store_id", "merchant_id"),
    "business_name": (
        "business_name",
        "store_name",
        "shop_name",
        "merchant_name",
        "brand_name",
        "restaurant_name",
        "place_name",
        "client_name",
        "name",
    ),
    "platform": (
        "platform",
        "platform_name",
        "source_platform",
        "review_platform",
        "source",
        "channel",
    ),
    "sentiment": (
        "sentiment",
        "sentiment_label",
        "sentiment_category",
        "sentiment_result",
        "review_sentiment",
        "polarity",
    ),
    "total": (
        "total_reviews",
        "total_review_count",
        "review_count",
        "reviews_count",
        "total_count",
        "reviews_total",
    ),
    "analyzed": ("analyzed_reviews", "analyzed_count", "classified_count"),
    "positive_count": ("positive_count", "positive_reviews", "positive_total", "positive"),
    "neutral_count": ("neutral_count", "neutral_reviews", "neutral_total", "neutral"),
    "negative_count": ("negative_count", "negative_reviews", "negative_total", "negative"),
    "unclassified_count": (
        "unclassified_count",
        "unclassified_reviews",
        "unknown_count",
        "unlabeled_count",
    ),
    "risk_score": (
        "risk_score",
        "risk_score_100",
        "overall_risk_score",
        "average_risk_score",
        "avg_risk_score",
        "risk_value",
    ),
    "risk_points": ("risk_points", "risk_point", "total_risk_points"),
    "risk_level": ("risk_level", "risk_level_label", "risk_grade", "risk_category"),
    "summary": (
        "summary",
        "summary_text",
        "review_summary",
        "ai_summary",
        "analysis_summary",
    ),
    "updated_at": (
        "updated_at",
        "last_updated_at",
        "analyzed_at",
        "reviewed_at",
        "published_at",
        "review_date",
        "created_at",
    ),
}

_PLATFORM_ORDER = {"ptt": 1, "threads": 2, "google_maps": 3}
_PLATFORM_LABELS = {"ptt": "PTT", "threads": "Threads", "google_maps": "Google Maps"}
_RISK_RANK = {"low": 1, "medium": 2, "high": 3}


class EnrichedReviewRepository:
    """Read the protected enriched review table without assuming one fixed schema."""

    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self._connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        if psycopg2 is None:
            raise DatabaseConfigurationError("psycopg2 is required for enriched reputation reports")
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise DatabaseConfigurationError("DATABASE_URL is required for enriched reputation reports")
        return psycopg2.connect(database_url, connect_timeout=10)

    def load_snapshot(
        self,
        *,
        line_user_id: str,
        business_name: str | None = None,
        business_id: int | None = None,
    ) -> EnrichedSnapshot:
        conn = self._connection_factory()
        try:
            business = self._resolve_business(
                conn,
                line_user_id=line_user_id,
                business_name=business_name,
                business_id=business_id,
            )
            schema_name, table_name, columns = self._discover_table(conn)
            rows = self._load_rows(
                conn,
                schema_name=schema_name,
                table_name=table_name,
                columns=columns,
                business=business,
            )
            platform_rows, latest_summary, numeric_risk_available = aggregate_enriched_rows(
                rows, columns
            )
            return EnrichedSnapshot(
                business=business,
                platform_rows=platform_rows,
                latest_summary=latest_summary,
                numeric_risk_available=numeric_risk_available,
                source_table=f"{schema_name}.{table_name}",
            )
        finally:
            conn.close()

    @staticmethod
    def _resolve_business(
        conn: Any,
        *,
        line_user_id: str,
        business_name: str | None,
        business_id: int | None,
    ) -> BusinessRecord:
        if business_id is not None:
            query = """
                SELECT id, name, branch_name
                FROM business
                WHERE id = %s AND status = 'active'
                LIMIT 1
            """
            params: tuple[Any, ...] = (business_id,)
        elif business_name:
            query = """
                SELECT id, name, branch_name
                FROM business
                WHERE lower(btrim(name)) = lower(btrim(%s))
                  AND status = 'active'
                LIMIT 1
            """
            params = (business_name,)
        else:
            query = """
                SELECT b.id, b.name, b.branch_name
                FROM clients c
                JOIN business b ON b.client_id = c.id
                WHERE c.line_user_id = %s
                  AND c.status = 'active'
                  AND b.status = 'active'
                ORDER BY b.id
                LIMIT 1
            """
            params = (line_user_id,)

        with conn.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if not row:
            target = business_name or str(business_id or line_user_id)
            raise BusinessNotFoundError(f"找不到可查詢的店家：{target}")
        return BusinessRecord(id=int(row[0]), name=str(row[1]), branch_name=row[2])

    def _discover_table(self, conn: Any) -> tuple[str, str, set[str]]:
        if sql is None:
            raise DatabaseConfigurationError("psycopg2.sql is required for enriched reputation reports")

        for schema_name, table_name in _configured_table_candidates():
            with conn.cursor() as cursor:
                cursor.execute("SELECT to_regclass(%s)", (f"{schema_name}.{table_name}",))
                if not cursor.fetchone()[0]:
                    continue
                cursor.execute(
                    sql.SQL("SELECT * FROM {}.{} LIMIT 0").format(
                        sql.Identifier(schema_name), sql.Identifier(table_name)
                    )
                )
                columns = {description.name for description in cursor.description or []}
            if columns:
                return schema_name, table_name, columns

        configured = ", ".join(f"{schema}.{table}" for schema, table in _configured_table_candidates())
        raise DatabaseConfigurationError(
            f"找不到 enriched review table；已檢查：{configured}"
        )

    @staticmethod
    def _load_rows(
        conn: Any,
        *,
        schema_name: str,
        table_name: str,
        columns: set[str],
        business: BusinessRecord,
    ) -> list[dict[str, Any]]:
        if sql is None:
            raise DatabaseConfigurationError("psycopg2.sql is required for enriched reputation reports")

        business_id_column = _find_column(columns, "business_id")
        business_name_column = _find_column(columns, "business_name")
        if business_id_column:
            predicate = sql.SQL("{} = %s").format(sql.Identifier(business_id_column))
            params: tuple[Any, ...] = (business.id,)
        elif business_name_column:
            predicate = sql.SQL("lower(btrim({})) = lower(btrim(%s))").format(
                sql.Identifier(business_name_column)
            )
            params = (business.name,)
        else:
            raise DatabaseConfigurationError(
                f"{schema_name}.{table_name} 缺少 business_id 或店家名稱欄位"
            )

        query = sql.SQL("SELECT * FROM {}.{} WHERE {}").format(
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
            predicate,
        )
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            names = [description.name for description in cursor.description or []]
            return [dict(zip(names, row, strict=False)) for row in cursor.fetchall()]


class EnrichedReputationSummaryService:
    def __init__(self, repository: EnrichedReviewRepository) -> None:
        self._repository = repository

    def build_summary(
        self,
        *,
        line_user_id: str,
        business_name: str | None = None,
        business_id: int | None = None,
    ) -> dict[str, Any]:
        snapshot = self._repository.load_snapshot(
            line_user_id=line_user_id,
            business_name=business_name,
            business_id=business_id,
        )
        platforms = [
            ReputationSummaryService._to_platform_summary(row)
            for row in snapshot.platform_rows
        ]
        overview = ReputationSummaryService._build_overview(
            platforms, snapshot.latest_summary
        )
        return {
            "business": {
                "id": snapshot.business.id,
                "name": snapshot.business.name,
                "branch_name": snapshot.business.branch_name,
                "display_name": snapshot.business.display_name,
            },
            "overview": overview.to_dict(),
            "platforms": [platform.to_dict() for platform in platforms],
            "data_contract": {
                "source_table": snapshot.source_table,
                "numeric_risk_available": snapshot.numeric_risk_available,
            },
        }


def aggregate_enriched_rows(
    rows: Iterable[dict[str, Any]], columns: set[str]
) -> tuple[list[dict[str, Any]], str | None, bool]:
    column_map = {key: _find_column(columns, key) for key in _COLUMN_CANDIDATES}
    aggregate_shape = any(
        column_map[key]
        for key in (
            "total",
            "positive_count",
            "neutral_count",
            "negative_count",
            "unclassified_count",
        )
    )
    numeric_risk_available = bool(column_map["risk_score"] or column_map["risk_points"])
    accumulators: dict[str, _PlatformAccumulator] = {}
    latest_summary: str | None = None
    latest_summary_at: datetime | None = None

    for row in rows:
        platform = _normalize_platform(_value(row, column_map["platform"]))
        accumulator = accumulators.setdefault(platform, _PlatformAccumulator())

        if aggregate_shape:
            positive = _as_int(_value(row, column_map["positive_count"]))
            neutral = _as_int(_value(row, column_map["neutral_count"]))
            negative = _as_int(_value(row, column_map["negative_count"]))
            unclassified = _as_int(_value(row, column_map["unclassified_count"]))
            analyzed = _as_int(_value(row, column_map["analyzed"]))
            if analyzed == 0:
                analyzed = positive + neutral + negative
            total_value = _value(row, column_map["total"])
            total = _as_int(total_value) if total_value is not None else analyzed + unclassified
            if not column_map["unclassified_count"]:
                unclassified = max(total - analyzed, 0)
        else:
            sentiment = _normalize_sentiment(_value(row, column_map["sentiment"]))
            total = 1
            positive = int(sentiment == "positive")
            neutral = int(sentiment == "neutral")
            negative = int(sentiment == "negative")
            analyzed = int(sentiment is not None)
            unclassified = 1 - analyzed

        accumulator.total += max(total, 0)
        accumulator.analyzed += max(analyzed, 0)
        accumulator.positive += max(positive, 0)
        accumulator.neutral += max(neutral, 0)
        accumulator.negative += max(negative, 0)
        accumulator.unclassified += max(unclassified, 0)

        risk_score = _as_float_or_none(_value(row, column_map["risk_score"]))
        if risk_score is not None:
            weight = max(analyzed if aggregate_shape else 1, 1)
            accumulator.risk_score_weighted_sum += risk_score * weight
            accumulator.risk_score_count += weight

        risk_points = _as_int_or_none(_value(row, column_map["risk_points"]))
        if risk_points is not None:
            accumulator.risk_points += risk_points
            accumulator.has_risk_points = True

        risk_level = _normalize_risk_level(_value(row, column_map["risk_level"]))
        accumulator.risk_rank = max(accumulator.risk_rank, _RISK_RANK.get(risk_level or "", 0))

        updated_at = _as_datetime(_value(row, column_map["updated_at"]))
        if updated_at and (accumulator.updated_at is None or updated_at > accumulator.updated_at):
            accumulator.updated_at = updated_at

        summary = _as_text(_value(row, column_map["summary"]))
        if summary and (
            latest_summary is None
            or latest_summary_at is None
            or (updated_at is not None and updated_at >= latest_summary_at)
        ):
            latest_summary = summary
            latest_summary_at = updated_at

    platform_rows: list[dict[str, Any]] = []
    for platform, accumulator in sorted(
        accumulators.items(), key=lambda item: (_PLATFORM_ORDER.get(item[0], 99), item[0])
    ):
        risk_score = None
        if accumulator.risk_score_count:
            risk_score = accumulator.risk_score_weighted_sum / accumulator.risk_score_count
        platform_rows.append(
            {
                "platform": platform,
                "label": _PLATFORM_LABELS.get(platform, platform.replace("_", " ").title()),
                "total": accumulator.total,
                "analyzed": accumulator.analyzed,
                "positive": accumulator.positive,
                "neutral": accumulator.neutral,
                "negative": accumulator.negative,
                "unclassified": accumulator.unclassified,
                "risk_score": risk_score,
                "risk_score_count": accumulator.risk_score_count,
                "risk_points": accumulator.risk_points if accumulator.has_risk_points else None,
                "risk_rank": accumulator.risk_rank,
                "updated_at": accumulator.updated_at,
            }
        )
    return platform_rows, latest_summary, numeric_risk_available


def _configured_table_candidates() -> list[tuple[str, str]]:
    configured = os.getenv("BI_RMP_ENRICHED_REVIEW_TABLE", "public.master_reviews_enriched").strip()
    candidates = [configured, "public.master_reviews_enriched", "public.review_enriched"]
    parsed: list[tuple[str, str]] = []
    for candidate in candidates:
        if not candidate:
            continue
        if "." in candidate:
            schema_name, table_name = candidate.split(".", 1)
        else:
            schema_name, table_name = "public", candidate
        pair = (schema_name.strip(), table_name.strip())
        if pair not in parsed:
            parsed.append(pair)
    return parsed


def _find_column(columns: set[str], key: str) -> str | None:
    lowered = {column.lower(): column for column in columns}
    for candidate in _COLUMN_CANDIDATES[key]:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _value(row: dict[str, Any], column: str | None) -> Any:
    return row.get(column) if column else None


def _normalize_platform(value: Any) -> str:
    text = _as_text(value)
    if not text:
        return "unknown"
    normalized = text.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"google", "googlemaps", "google_map", "google_maps_reviews"}:
        return "google_maps"
    return normalized


def _normalize_sentiment(value: Any) -> str | None:
    text = (_as_text(value) or "").lower()
    if text in {"positive", "pos", "正面", "正向", "好評"}:
        return "positive"
    if text in {"neutral", "neu", "中立", "普通"}:
        return "neutral"
    if text in {"negative", "neg", "負面", "負向", "負評"}:
        return "negative"
    return None


def _normalize_risk_level(value: Any) -> str | None:
    text = (_as_text(value) or "").lower()
    if text in {"high", "h", "高", "高風險", "高度", "嚴重"}:
        return "high"
    if text in {"medium", "mid", "m", "中", "中風險", "中度"}:
        return "medium"
    if text in {"low", "l", "低", "低風險", "低度"}:
        return "low"
    return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int:
    converted = _as_int_or_none(value)
    return converted if converted is not None else 0


def _as_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(Decimal(str(value)))
    except (ArithmeticError, ValueError):
        return None


def _as_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
