from pathlib import Path
import re


MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[3]
    / "database"
    / "migrations"
)


def test_no_bi_rmp_copy_of_reviews_enriched_is_created() -> None:
    assert not (
        MIGRATIONS_DIR
        / "20260711_create_bi_rmp_reviews_enriched.sql"
    ).exists()


def test_migrations_never_modify_shared_reviews_enriched() -> None:
    destructive_patterns = (
        r"\bDROP\s+(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+EXISTS\s+)?"
        r"PUBLIC\.REVIEWS_ENRICHED\b",
        r"\bALTER\s+(?:MATERIALIZED\s+)?VIEW\s+"
        r"PUBLIC\.REVIEWS_ENRICHED\b",
        r"\bCREATE\s+OR\s+REPLACE\s+VIEW\s+"
        r"PUBLIC\.REVIEWS_ENRICHED\b",
    )

    for migration in MIGRATIONS_DIR.glob("*.sql"):
        sql = migration.read_text(encoding="utf-8").upper()
        for pattern in destructive_patterns:
            assert re.search(pattern, sql) is None, (
                f"{migration.name} must not modify public.reviews_enriched"
            )
