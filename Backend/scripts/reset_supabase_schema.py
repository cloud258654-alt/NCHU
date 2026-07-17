from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

from core.supabase import get_connection


SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"
EXPECTED_TABLES = {
    "alerts",
    "analysis_results",
    "business",
    "client_messages_log",
    "clients",
    "comment_metric_snapshots",
    "crawl_comments",
    "crawl_jobs",
    "crawl_logs",
    "crawl_posts",
    "post_metric_snapshots",
    "reputation_score_snapshots",
    "service_tasks",
}


def main() -> int:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.autocommit = True
        protected_before = _fetch_protected_tables(conn)
        print("Protected legacy tables before reset:", _format_list(protected_before))
        with conn.cursor() as cur:
            cur.execute(sql)
        runtime_tables = _fetch_runtime_tables(conn)
        protected_after = _fetch_protected_tables(conn)
    finally:
        conn.close()

    missing = sorted(EXPECTED_TABLES - runtime_tables)
    if missing:
        print("Missing runtime tables after reset:", _format_list(missing))
        return 1

    lost_protected = sorted(set(protected_before) - set(protected_after))
    if lost_protected:
        print("Protected tables lost during reset:", _format_list(lost_protected))
        return 1

    print("Runtime tables verified:", _format_list(sorted(runtime_tables & EXPECTED_TABLES)))
    print("Protected legacy tables after reset:", _format_list(protected_after))
    print("Schema reset completed.")
    return 0


def _fetch_runtime_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            """
        )
        return {row[0] for row in cur.fetchall()}


def _fetch_protected_tables(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND (
                table_name LIKE 'review%%'
                OR table_name = 'master_reviews_enriched'
              )
            ORDER BY table_name
            """
        )
        return [row[0] for row in cur.fetchall()]


def _format_list(values: list[str] | set[str]) -> str:
    values = sorted(values)
    return ", ".join(values) if values else "<none>"


if __name__ == "__main__":
    raise SystemExit(main())
