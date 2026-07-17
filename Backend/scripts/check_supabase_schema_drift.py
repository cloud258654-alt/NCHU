from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_ALLOWLIST = BACKEND_ROOT / "config" / "schema_allowlist.json"


def load_allowlist(path: Path = DEFAULT_ALLOWLIST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_objects(allowlist: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "table": set(allowlist.get("tables", [])),
        "view": set(allowlist.get("views", [])),
    }


def is_protected_table(name: str, allowlist: dict[str, Any]) -> bool:
    if name in set(allowlist.get("protected_tables", [])):
        return True
    patterns = [pattern.replace("%", "*") for pattern in allowlist.get("protected_table_patterns", [])]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def diff_schema_objects(
    actual_objects: list[tuple[str, str]],
    allowlist: dict[str, Any],
) -> dict[str, list[str]]:
    expected = expected_objects(allowlist)
    actual = {"table": set(), "view": set()}
    unexpected_types: list[str] = []
    for name, object_type in actual_objects:
        if object_type in actual:
            if object_type == "table" and is_protected_table(name, allowlist):
                continue
            actual[object_type].add(name)
        else:
            unexpected_types.append(f"{name}:{object_type}")

    return {
        "extra_tables": sorted(actual["table"] - expected["table"]),
        "missing_tables": sorted(expected["table"] - actual["table"]),
        "extra_views": sorted(actual["view"] - expected["view"]),
        "missing_views": sorted(expected["view"] - actual["view"]),
        "unexpected_object_types": sorted(unexpected_types),
    }


def fetch_schema_objects(schema: str) -> list[tuple[str, str]]:
    from core.supabase import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  c.relname,
                  CASE c.relkind
                    WHEN 'r' THEN 'table'
                    WHEN 'p' THEN 'table'
                    WHEN 'v' THEN 'view'
                    WHEN 'm' THEN 'view'
                    ELSE c.relkind::text
                  END AS object_type
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relkind IN ('r', 'p', 'v', 'm')
                ORDER BY c.relname
                """,
                (schema,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]
    finally:
        conn.close()


def print_report(diff: dict[str, list[str]]) -> None:
    has_drift = any(diff.values())
    print("Supabase schema drift check")
    print("===========================")
    for key in ("extra_tables", "missing_tables", "extra_views", "missing_views", "unexpected_object_types"):
        values = diff[key]
        status = "OK" if not values else "DRIFT"
        print(f"{key}: {status}")
        for value in values:
            print(f"  - {value}")
    print("result:", "DRIFT" if has_drift else "PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Supabase public schema against BI-RMP allowlist.")
    parser.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST), help="Path to schema allowlist JSON.")
    args = parser.parse_args()

    allowlist = load_allowlist(Path(args.allowlist))
    schema = allowlist.get("schema", "public")
    actual = fetch_schema_objects(schema)
    diff = diff_schema_objects(actual, allowlist)
    print_report(diff)
    return 1 if any(diff.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
