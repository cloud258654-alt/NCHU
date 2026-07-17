from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.reviews_enriched import (  # noqa: E402
    _configured_reviews_enriched_relation,
    _quote_identifier,
)
from core.supabase import get_connection  # noqa: E402

_REQUIRED_COLUMNS = frozenset({"review_id", "platform", "sentiment_label"})
_OPTIONAL_COLUMNS = frozenset(
    {
        "sentiment_score",
        "risk_score",
        "risk_level",
        "rating",
        "analyzed_at",
        "review_time",
        "flag_food_safety",
        "flag_legal_risk",
        "flag_hygiene_risk",
        "emotion_joy",
        "emotion_anger",
        "emotion_disappointment",
        "reviews_tag",
    }
)
_SAFE_SAMPLE_COLUMNS = (
    "review_id",
    "platform",
    "sentiment_label",
    "sentiment_score",
    "rating",
    "risk_score",
    "risk_level",
    "flag_food_safety",
    "flag_legal_risk",
    "flag_hygiene_risk",
    "analyzed_at",
    "review_time",
)
_RELATION_TYPE = {
    "r": "table",
    "p": "partitioned_table",
    "v": "view",
    "m": "materialized_view",
}


def evaluate_contract(column_names: set[str]) -> dict[str, Any]:
    missing_required = sorted(_REQUIRED_COLUMNS.difference(column_names))
    optional_present = sorted(_OPTIONAL_COLUMNS.intersection(column_names))
    return {
        "valid": not missing_required,
        "report_scope": "all_rows",
        "required_columns": sorted(_REQUIRED_COLUMNS),
        "missing_required_columns": missing_required,
        "business_filter_columns": [],
        "optional_columns_present": optional_present,
        "optional_columns_missing": sorted(
            _OPTIONAL_COLUMNS.difference(column_names)
        ),
    }


def safe_sample_columns(column_names: set[str]) -> list[str]:
    return [name for name in _SAFE_SAMPLE_COLUMNS if name in column_names]


def inspect_reviews_enriched(
    connection_factory: Callable[[], Any] = get_connection,
    *,
    sample_limit: int = 3,
    scan_limit: int = 10_000,
) -> dict[str, Any]:
    schema_name, table_name = _configured_reviews_enriched_relation()
    relation_name = f"{schema_name}.{table_name}"
    conn = connection_factory()

    try:
        if hasattr(conn, "set_session"):
            conn.set_session(readonly=True, autocommit=False)

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relkind
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relname = %s
                  AND c.relkind IN ('r', 'p', 'v', 'm')
                LIMIT 1
                """,
                (schema_name, table_name),
            )
            relation_row = cursor.fetchone()
            if not relation_row:
                return _empty_report(relation_name, scan_limit)

            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema_name, table_name),
            )
            column_rows = cursor.fetchall()
            columns = [
                {
                    "name": str(row[0]),
                    "data_type": str(row[1]),
                    "nullable": str(row[2]) == "YES",
                    "position": int(row[3]),
                }
                for row in column_rows
            ]
            column_names = {column["name"] for column in columns}
            contract = evaluate_contract(column_names)

            relation_sql = (
                f"{_quote_identifier(schema_name)}."
                f"{_quote_identifier(table_name)}"
            )
            effective_scan_limit = max(1, min(int(scan_limit), 100_000))
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT 1
                    FROM {relation_sql}
                    LIMIT %s
                ) inspected_rows
                """,
                (effective_scan_limit,),
            )
            scanned_row_count = int(cursor.fetchone()[0])

            platform_distribution = _fetch_distribution(
                cursor,
                relation_sql=relation_sql,
                column="platform",
                available=column_names,
                scan_limit=effective_scan_limit,
            )
            sentiment_distribution = _fetch_distribution(
                cursor,
                relation_sql=relation_sql,
                column="sentiment_label",
                available=column_names,
                scan_limit=effective_scan_limit,
            )
            samples = _fetch_samples(
                cursor,
                relation_sql=relation_sql,
                column_names=column_names,
                sample_limit=sample_limit,
            )

        if hasattr(conn, "rollback"):
            conn.rollback()

        return {
            "relation": relation_name,
            "exists": True,
            "relation_type": _RELATION_TYPE.get(
                str(relation_row[0]),
                str(relation_row[0]),
            ),
            "report_scope": "all_rows",
            "columns": columns,
            "contract": contract,
            "scanned_row_count": scanned_row_count,
            "scan_limit": effective_scan_limit,
            "scan_limit_reached": scanned_row_count >= effective_scan_limit,
            "platform_distribution": platform_distribution,
            "sentiment_distribution": sentiment_distribution,
            "samples": samples,
        }
    finally:
        conn.close()


def _empty_report(relation_name: str, scan_limit: int) -> dict[str, Any]:
    return {
        "relation": relation_name,
        "exists": False,
        "relation_type": None,
        "report_scope": "all_rows",
        "columns": [],
        "contract": evaluate_contract(set()),
        "scanned_row_count": 0,
        "scan_limit": scan_limit,
        "scan_limit_reached": False,
        "platform_distribution": [],
        "sentiment_distribution": [],
        "samples": [],
    }


def _fetch_distribution(
    cursor: Any,
    *,
    relation_sql: str,
    column: str,
    available: set[str],
    scan_limit: int,
) -> list[dict[str, Any]]:
    if column not in available:
        return []

    identifier = _quote_identifier(column)
    cursor.execute(
        f"""
        SELECT
            COALESCE(NULLIF(btrim({identifier}::text), ''), '<empty>') AS value,
            COUNT(*)::integer AS count
        FROM (
            SELECT {identifier}
            FROM {relation_sql}
            LIMIT %s
        ) inspected_rows
        GROUP BY 1
        ORDER BY count DESC, value
        LIMIT 20
        """,
        (scan_limit,),
    )
    return [
        {"value": str(row[0]), "count": int(row[1])}
        for row in cursor.fetchall()
    ]


def _fetch_samples(
    cursor: Any,
    *,
    relation_sql: str,
    column_names: set[str],
    sample_limit: int,
) -> list[dict[str, Any]]:
    selected = safe_sample_columns(column_names)
    if not selected or sample_limit <= 0:
        return []

    selection = ", ".join(
        _quote_identifier(column) for column in selected
    )
    cursor.execute(
        f"SELECT {selection} FROM {relation_sql} LIMIT %s",
        (min(sample_limit, 10),),
    )
    return [
        dict(zip(selected, row, strict=False))
        for row in cursor.fetchall()
    ]


def report_exit_code(report: dict[str, Any]) -> int:
    if not report.get("exists"):
        return 1
    contract = report.get("contract")
    return 0 if isinstance(contract, dict) and contract.get("valid") else 1


def print_human_report(report: dict[str, Any]) -> None:
    print("reviews_enriched all-row inspection")
    print("===================================")
    print("relation:", report["relation"])
    print("exists:", report["exists"])
    print("relation_type:", report.get("relation_type") or "not_found")
    print("report_scope:", report.get("report_scope", "all_rows"))
    print("scanned_row_count:", report.get("scanned_row_count", 0))
    print("scan_limit:", report.get("scan_limit", 0))
    print("scan_limit_reached:", report.get("scan_limit_reached", False))

    contract = report["contract"]
    print("contract:", "PASS" if contract["valid"] else "FAIL")
    if contract["missing_required_columns"]:
        print(
            "missing_required_columns:",
            ", ".join(contract["missing_required_columns"]),
        )
    print(
        "optional_columns_present:",
        ", ".join(contract["optional_columns_present"]) or "none",
    )

    print("columns:")
    for column in report.get("columns", []):
        nullable = "NULL" if column["nullable"] else "NOT NULL"
        print(
            f"  - {column['name']}: {column['data_type']} "
            f"({nullable}, position {column['position']})"
        )

    for label, key in (
        ("platform_distribution", "platform_distribution"),
        ("sentiment_label_distribution", "sentiment_distribution"),
    ):
        print(f"{label}:")
        values = report.get(key, [])
        if not values:
            print("  - none")
        for item in values:
            print(f"  - {item['value']}: {item['count']}")

    print("safe_samples:")
    samples = report.get("samples", [])
    if not samples:
        print("  - none")
    for index, sample in enumerate(samples, start=1):
        print(
            f"  - {index}: "
            f"{json.dumps(sample, ensure_ascii=False, default=str)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect all rows in public.reviews_enriched through DATABASE_URL "
            "without printing reviewer names, review text, or connection secrets."
        )
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=3,
        help="Number of sanitized sample rows to show (0-10, default: 3).",
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=10_000,
        help="Maximum rows scanned for counts/distributions (1-100000).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    args = parser.parse_args()

    try:
        report = inspect_reviews_enriched(
            sample_limit=max(0, min(args.sample_limit, 10)),
            scan_limit=max(1, min(args.scan_limit, 100_000)),
        )
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False,
            )
            if args.json
            else f"inspection failed: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print_human_report(report)
    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
