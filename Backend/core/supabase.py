from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from core.crawled_post_models import (
    extract_comment_metrics,
    extract_comments,
    extract_post_metrics,
    standardize_crawled_post,
)
from core.runtime_settings import (
    validate_database_writes_enabled,
    validate_staging_database_target,
)

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

try:
    import psycopg2
    from psycopg2.extras import Json
except ModuleNotFoundError:
    psycopg2 = None

    class Json:  # type: ignore[no-redef]
        def __init__(self, value: Any) -> None:
            self.value = value


logger = logging.getLogger("core.supabase")

DEFAULT_POST_BATCH_SIZE = 200
DEFAULT_METRIC_BATCH_SIZE = 500
DEFAULT_COMMENT_BATCH_SIZE = 500


@dataclass(frozen=True)
class ExistingReviewRecord:
    crawl_comment_id: str
    review_id: str | None
    dedupe_key: str
    content_hash: str
    metric_hash: str
    lightweight_hash: str
    author_name: str
    rating: float | None
    published_at: datetime | None
    content: str
    like_count: int
    reply_count: int
    reaction_count: int


@dataclass(frozen=True)
class ExistingGoogleReviewIndex:
    by_place: dict[str, dict[str, ExistingReviewRecord]]
    available: bool
    source: str
    records_loaded: int
    error_message: str | None = None


@dataclass(frozen=True)
class PersistenceStageResult:
    stage: str
    success: bool
    rows_attempted: int
    rows_written: int
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class PersistenceResult:
    stages: list[PersistenceStageResult]

    @property
    def canonical_posts_written(self) -> int:
        return self.rows_written("canonical_posts")

    @property
    def canonical_comments_written(self) -> int:
        return self.rows_written("canonical_comments")

    @property
    def failed_stages(self) -> list[str]:
        return [stage.stage for stage in self.stages if not stage.success]

    @property
    def success(self) -> bool:
        return not self.failed_stages

    @property
    def status(self) -> str:
        if self.success:
            return "success"
        if any(stage in self.failed_stages for stage in ("canonical_posts", "canonical_comments")):
            return "failed"
        return "partial_success"

    @property
    def error_type(self) -> str | None:
        if self.success:
            return None
        return "db_write_failed" if self.status == "failed" else "persistence_partial_failure"

    @property
    def error_message(self) -> str | None:
        failures = [stage for stage in self.stages if not stage.success]
        if not failures:
            return None
        return "; ".join(f"{stage.stage}: {stage.error_message or stage.error_type or 'failed'}" for stage in failures)

    def rows_written(self, stage_name: str) -> int:
        return sum(stage.rows_written for stage in self.stages if stage.stage == stage_name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_posts_written": self.rows_written("canonical_posts"),
            "canonical_comments_written": self.rows_written("canonical_comments"),
            "post_metric_snapshots_written": self.rows_written("post_metric_snapshots"),
            "comment_metric_snapshots_written": self.rows_written("comment_metric_snapshots"),
            "failed_stages": self.failed_stages,
            "stages": [
                {
                    "stage": stage.stage,
                    "success": stage.success,
                    "rows_attempted": stage.rows_attempted,
                    "rows_written": stage.rows_written,
                    "error_type": stage.error_type,
                    "error_message": stage.error_message,
                }
                for stage in self.stages
            ],
        }


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw_value, default)
        return default
    if value < 1:
        logger.warning("Invalid %s=%r; using default %s", name, raw_value, default)
        return default
    return value


def _post_batch_size() -> int:
    return _positive_int_env("BI_RMP_DB_POST_BATCH_SIZE", DEFAULT_POST_BATCH_SIZE)


def _metric_batch_size() -> int:
    return _positive_int_env("BI_RMP_DB_METRIC_BATCH_SIZE", DEFAULT_METRIC_BATCH_SIZE)


def _comment_batch_size() -> int:
    return _positive_int_env("BI_RMP_DB_COMMENT_BATCH_SIZE", DEFAULT_COMMENT_BATCH_SIZE)


def _iter_batches(items: Iterable[dict], batch_size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    if psycopg2 is None:
        raise ValueError("psycopg2 is required for Supabase/PostgreSQL writes")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required for PostgreSQL writes")
    validate_database_writes_enabled()
    validate_staging_database_target()
    conn = psycopg2.connect(database_url)
    conn.set_client_encoding("UTF8")
    return conn


def save_threads_posts(posts: list[dict]) -> int:
    return save_threads_posts_with_result(posts).canonical_posts_written


def save_threads_posts_with_result(posts: list[dict]) -> PersistenceResult:
    return _save_platform_posts_with_result(posts, platform="threads")


def save_ptt_posts(posts: list[dict]) -> int:
    return save_ptt_posts_with_result(posts).canonical_posts_written


def save_ptt_posts_with_result(posts: list[dict]) -> PersistenceResult:
    return _save_platform_posts_with_result(posts, platform="ptt")


def save_google_reviews(posts: list[dict]) -> int:
    return save_google_reviews_with_result(posts).canonical_posts_written


def save_google_reviews_with_result(posts: list[dict]) -> PersistenceResult:
    return _save_platform_posts_with_result(posts, platform="google_maps")


def load_existing_google_review_index(
    place_urls: list[str],
    *,
    window_start: datetime,
    window_end: datetime,
) -> ExistingGoogleReviewIndex:
    """Load canonical Google Maps reviews for delta comparison."""

    try:
        return _load_existing_google_review_index_postgres(place_urls, window_start=window_start, window_end=window_end)
    except Exception as exc:
        logger.warning("Existing Google review index unavailable: %s", exc)
        return ExistingGoogleReviewIndex(
            by_place={},
            available=False,
            source="unavailable",
            records_loaded=0,
            error_message=str(exc),
        )


def load_existing_ptt_index(
    window_start: datetime,
    window_end: datetime,
    candidate_urls: list[str] | None = None,
):
    from adapters.ptt.delta import ExistingPttIndex

    try:
        return _load_existing_ptt_index_postgres(
            window_start=window_start,
            window_end=window_end,
            candidate_urls=candidate_urls,
        )
    except Exception as exc:
        logger.warning("Existing PTT index unavailable: %s", exc)
        return ExistingPttIndex(
            by_external_id={},
            by_normalized_url={},
            available=False,
            source="unavailable",
            records_loaded=0,
            error_message=str(exc),
        )


def load_existing_threads_index(
    window_start: datetime,
    window_end: datetime,
    candidate_urls: list[str] | None = None,
):
    from adapters.threads.delta import ExistingThreadsIndex

    try:
        return _load_existing_threads_index_postgres(
            window_start=window_start,
            window_end=window_end,
            candidate_urls=candidate_urls,
        )
    except Exception as exc:
        logger.warning("Existing Threads index unavailable: %s", exc)
        return ExistingThreadsIndex(
            by_post_id={},
            by_normalized_url={},
            available=False,
            source="unavailable",
            records_loaded=0,
            error_message=str(exc),
        )


def save_crawled_posts(posts: list[dict]) -> int:
    normalized = (
        standardize_crawled_post(
            post,
            platform=post.get("platform") or post.get("source") or "web",
            keyword=post.get("keyword"),
            crawl_job_id=post.get("crawl_job_id") or os.getenv("BI_RMP_CRAWL_JOB_ID"),
            service_task_id=post.get("service_task_id") or os.getenv("BI_RMP_SERVICE_TASK_ID"),
            parsed_time=post.get("post_time") or post.get("posted_at"),
        )
        for post in posts
    )
    return save_crawled_post_records(normalized)


def _load_existing_google_review_index_postgres(
    place_urls: list[str],
    *,
    window_start: datetime,
    window_end: datetime,
) -> ExistingGoogleReviewIndex:
    from adapters.google_maps.delta import normalize_place_url

    normalized_urls = [normalize_place_url(url) for url in place_urls if normalize_place_url(url)]
    if not normalized_urls:
        return ExistingGoogleReviewIndex(by_place={}, available=True, source="postgres", records_loaded=0)

    query = """
    SELECT
        cp.link,
        cc.id,
        cc.platform_comment_id,
        cc.dedupe_key,
        cc.author_name,
        cc.content,
        cc.published_at,
        cc.like_count,
        cc.reply_count,
        cc.reaction_count,
        cc.extra_data
    FROM crawl_posts cp
    JOIN crawl_comments cc ON cc.crawl_post_id = cp.id
    WHERE cp.link = ANY(%s)
      AND (cc.published_at IS NULL OR (cc.published_at >= %s AND cc.published_at <= %s))
    """
    rows: list[dict[str, Any]] = []
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (normalized_urls, window_start, window_end))
            for row in cur.fetchall():
                rows.append(
                    {
                        "place_url": row[0],
                        "id": row[1],
                        "platform_comment_id": row[2],
                        "dedupe_key": row[3],
                        "author_name": row[4],
                        "content": row[5],
                        "published_at": row[6],
                        "like_count": row[7],
                        "reply_count": row[8],
                        "reaction_count": row[9],
                        "extra_data": row[10] or {},
                    }
                )
    finally:
        conn.close()
    return _existing_google_review_index_from_rows(rows, source="postgres")


def _existing_google_review_index_from_rows(rows: list[dict[str, Any]], *, source: str) -> ExistingGoogleReviewIndex:
    from adapters.google_maps.delta import existing_record_from_review, google_review_identity, normalize_place_url

    by_place: dict[str, dict[str, ExistingReviewRecord]] = {}
    loaded = 0
    for row in rows:
        post_row = row.get("crawl_posts") if isinstance(row.get("crawl_posts"), dict) else {}
        place_url = row.get("place_url") or post_row.get("link") or (row.get("extra_data") or {}).get("source_url")
        normalized_place = normalize_place_url(place_url)
        if not normalized_place:
            continue
        extra_data = row.get("extra_data") if isinstance(row.get("extra_data"), dict) else {}
        review = {
            "crawl_comment_id": row.get("id"),
            "id": row.get("platform_comment_id") or extra_data.get("external_id"),
            "dedupe_key": row.get("dedupe_key"),
            "author_name": row.get("author_name"),
            "content": row.get("content"),
            "published_at": row.get("published_at"),
            "rating": extra_data.get("rating_value"),
            "like_count": row.get("like_count"),
            "reply_count": row.get("reply_count"),
            "reaction_count": row.get("reaction_count"),
        }
        identity_key, _ = google_review_identity(review, place_url=normalized_place)
        by_place.setdefault(normalized_place, {})[identity_key] = existing_record_from_review(
            review,
            place_url=normalized_place,
        )
        loaded += 1
    return ExistingGoogleReviewIndex(
        by_place=by_place,
        available=True,
        source=source,
        records_loaded=loaded,
    )


def _load_existing_ptt_index_postgres(
    *,
    window_start: datetime,
    window_end: datetime,
    candidate_urls: list[str] | None,
):
    from adapters.ptt.delta import ExistingPttIndex, existing_ptt_record_from_row, normalize_ptt_url

    candidate_urls = [normalize_ptt_url(url) for url in candidate_urls or [] if normalize_ptt_url(url)]
    rows = _load_existing_platform_post_rows_postgres(
        platform="ptt",
        window_start=window_start,
        window_end=window_end,
        candidate_urls=candidate_urls,
    )
    by_external_id = {}
    by_normalized_url = {}
    for row in rows:
        record = existing_ptt_record_from_row(row, row.get("comments") or [])
        if record.external_id:
            by_external_id[record.external_id] = record
        if record.normalized_url:
            by_normalized_url[record.normalized_url] = record
    return ExistingPttIndex(
        by_external_id=by_external_id,
        by_normalized_url=by_normalized_url,
        available=True,
        source="postgres",
        records_loaded=len(rows),
    )


def _load_existing_threads_index_postgres(
    *,
    window_start: datetime,
    window_end: datetime,
    candidate_urls: list[str] | None,
):
    from adapters.threads.delta import ExistingThreadsIndex, existing_threads_record_from_row, normalize_threads_url

    candidate_urls = [normalize_threads_url(url) for url in candidate_urls or [] if normalize_threads_url(url)]
    rows = _load_existing_platform_post_rows_postgres(
        platform="threads",
        window_start=window_start,
        window_end=window_end,
        candidate_urls=candidate_urls,
    )
    by_post_id = {}
    by_normalized_url = {}
    for row in rows:
        record = existing_threads_record_from_row(row, row.get("comments") or [])
        if record.post_id:
            by_post_id[record.post_id] = record
        if record.normalized_url:
            by_normalized_url[record.normalized_url] = record
    return ExistingThreadsIndex(
        by_post_id=by_post_id,
        by_normalized_url=by_normalized_url,
        available=True,
        source="postgres",
        records_loaded=len(rows),
    )


def _load_existing_platform_post_rows_postgres(
    *,
    platform: str,
    window_start: datetime,
    window_end: datetime,
    candidate_urls: list[str] | None,
) -> list[dict[str, Any]]:
    post_query = """
    SELECT
        id,
        platform_post_id,
        link,
        title,
        author_id,
        author_name,
        content,
        published_at,
        like_count,
        comment_count,
        share_count,
        view_count,
        reaction_count,
        extra_data
    FROM crawl_posts
    WHERE COALESCE(extra_data->>'platform', '') = %s
      AND (published_at IS NULL OR (published_at >= %s AND published_at <= %s))
    """
    params: list[Any] = [platform, window_start, window_end]
    if candidate_urls:
        post_query += " AND link = ANY(%s)"
        params.append(candidate_urls)

    comment_query = """
    SELECT
        crawl_post_id,
        platform_comment_id,
        dedupe_key,
        author_id,
        author_name,
        content,
        published_at,
        like_count,
        reply_count,
        reaction_count,
        extra_data
    FROM crawl_comments
    WHERE crawl_post_id = ANY(%s)
    """
    rows: list[dict[str, Any]] = []
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(post_query, params)
            for row in cur.fetchall():
                rows.append(
                    {
                        "id": row[0],
                        "platform_post_id": row[1],
                        "link": row[2],
                        "title": row[3],
                        "author_id": row[4],
                        "author_name": row[5],
                        "content": row[6],
                        "published_at": row[7],
                        "like_count": row[8],
                        "comment_count": row[9],
                        "share_count": row[10],
                        "view_count": row[11],
                        "reaction_count": row[12],
                        "extra_data": row[13] or {},
                        "comments": [],
                    }
                )
            post_ids = [row["id"] for row in rows]
            if post_ids:
                by_post_id = {row["id"]: row for row in rows}
                cur.execute(comment_query, (post_ids,))
                for row in cur.fetchall():
                    target = by_post_id.get(row[0])
                    if target is None:
                        continue
                    extra_data = row[10] or {}
                    target["comments"].append(
                        {
                            "external_id": row[1] or extra_data.get("external_id"),
                            "dedupe_key": row[2],
                            "author_id": row[3],
                            "author_name": row[4],
                            "content": row[5],
                            "commented_at": row[6],
                            "published_at": row[6],
                            "like_count": row[7],
                            "reply_count": row[8],
                            "reaction_count": row[9],
                            "source_url": extra_data.get("source_url"),
                            "comment_type": extra_data.get("comment_type"),
                            "comment_time_raw": extra_data.get("comment_time_raw"),
                            "raw_json": extra_data.get("raw_json") or extra_data,
                        }
                    )
    finally:
        conn.close()
    return rows


def save_search_results(results: list[dict]) -> int:
    """Search aggregator storage is not part of the MVP clean schema."""

    if results:
        logger.info("search_results table retired in MVP clean schema; skipped %s rows", len(results))
    return 0


def save_search_parsed_platform_posts(results: list[dict], *, keyword: str, date_range: str) -> int:
    posts = (
        post
        for post in (standardize_search_result(result, keyword=keyword) for result in results)
        if post is not None
    )
    return save_crawled_post_records(posts)


def save_crawled_post_records(posts: Iterable[dict]) -> int:
    return save_crawled_post_records_with_result(posts).canonical_posts_written


def save_crawled_post_records_with_result(posts: Iterable[dict]) -> PersistenceResult:
    """Upsert the latest canonical state and its producing crawl job."""

    stages: list[PersistenceStageResult] = []
    source_posts = (post for post in posts if post.get("source_url"))

    for posts_batch in _iter_batches(source_posts, _post_batch_size()):
        db_rows = _dedupe_crawled_post_rows([_crawled_post_row(post) for post in posts_batch])
        id_map = _upsert_crawled_post_rows(db_rows)
        stages.append(_stage_from_mapping("canonical_posts", rows_attempted=len(db_rows), rows_written=len(id_map)))
        if not id_map:
            continue

        captured_at = _utc_now_iso()
        metric_rows: list[dict[str, Any]] = []
        comment_rows: list[dict[str, Any]] = []

        for post in posts_batch:
            post_id = id_map.get(post["source_url"])
            if not post_id:
                continue
            raw_payload = post.get("raw_json") if isinstance(post.get("raw_json"), dict) else post
            for metric in extract_post_metrics(raw_payload or post, captured_at=captured_at):
                metric_rows.append({"crawl_post_id": post_id, **metric})
            for comment in extract_comments(raw_payload or post, platform=post["platform"], post_source_url=post["source_url"]):
                comment_rows.append(
                    {
                        "crawl_post_id": post_id,
                        "keyword": post.get("keyword"),
                        **comment,
                    }
                )

        for metric_batch in _iter_batches(metric_rows, _metric_batch_size()):
            stages.append(_coerce_stage_result(_insert_post_metrics(metric_batch), "post_metric_snapshots", len(metric_batch)))

        comment_id_map: dict[str, str] = {}
        for comment_batch in _iter_batches(comment_rows, _comment_batch_size()):
            batch_id_map = _upsert_comments(comment_batch)
            comment_id_map.update(batch_id_map)
            stages.append(
                _stage_from_mapping(
                    "canonical_comments",
                    rows_attempted=len({row["dedupe_key"] for row in comment_batch}),
                    rows_written=len(batch_id_map),
                )
            )

        collected_at = _utc_now_iso()
        comment_metric_rows: list[dict[str, Any]] = []
        for comment in comment_rows:
            comment_id = comment_id_map.get(comment["dedupe_key"])
            if not comment_id:
                continue

            metric = extract_comment_metrics(comment, collected_at=collected_at)
            if metric is not None:
                comment_metric_rows.append(
                    {
                        "crawl_comment_id": comment_id,
                        **metric,
                    }
                )

        for comment_metric_batch in _iter_batches(comment_metric_rows, _metric_batch_size()):
            stages.append(_coerce_stage_result(_insert_comment_metrics(comment_metric_batch), "comment_metric_snapshots", len(comment_metric_batch)))

        del posts_batch, db_rows, id_map, metric_rows, comment_rows
        del comment_metric_rows

    return PersistenceResult(stages=stages)


def _save_platform_posts(posts: list[dict], *, platform: str) -> int:
    service_task_id = os.getenv("BI_RMP_SERVICE_TASK_ID")
    crawl_job_id = os.getenv("BI_RMP_CRAWL_JOB_ID")
    normalized = (
        standardize_crawled_post(
            post,
            platform=platform,
            keyword=post.get("keyword"),
            crawl_job_id=post.get("crawl_job_id") or crawl_job_id,
            service_task_id=post.get("service_task_id") or service_task_id,
            parsed_time=post.get("post_time"),
        )
        for post in posts
    )
    return save_crawled_post_records(normalized)


def _save_platform_posts_with_result(posts: list[dict], *, platform: str) -> PersistenceResult:
    service_task_id = os.getenv("BI_RMP_SERVICE_TASK_ID")
    crawl_job_id = os.getenv("BI_RMP_CRAWL_JOB_ID")
    normalized = (
        standardize_crawled_post(
            post,
            platform=platform,
            keyword=post.get("keyword"),
            crawl_job_id=post.get("crawl_job_id") or crawl_job_id,
            service_task_id=post.get("service_task_id") or service_task_id,
            parsed_time=post.get("post_time"),
        )
        for post in posts
    )
    return save_crawled_post_records_with_result(normalized)


def _stage_from_mapping(stage: str, *, rows_attempted: int, rows_written: int) -> PersistenceStageResult:
    success = rows_attempted == rows_written
    return PersistenceStageResult(
        stage=stage,
        success=success,
        rows_attempted=rows_attempted,
        rows_written=rows_written,
        error_type=None if success else "db_write_failed",
        error_message=None if success else f"wrote {rows_written} of {rows_attempted} rows",
    )


def _coerce_stage_result(value: Any, stage: str, rows_attempted: int) -> PersistenceStageResult:
    if isinstance(value, PersistenceStageResult):
        return value
    return PersistenceStageResult(
        stage=stage,
        success=True,
        rows_attempted=rows_attempted,
        rows_written=rows_attempted,
    )


def _dedupe_crawled_post_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last non-null value for duplicate links within one write batch."""

    by_link: dict[str, dict[str, Any]] = {}
    for row in rows:
        link = row["link"]
        if link not in by_link:
            by_link[link] = dict(row)
            continue

        latest = by_link[link]
        for key, value in row.items():
            if value is not None:
                latest[key] = value
    return list(by_link.values())


def _upsert_crawled_post_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    return _upsert_crawled_post_rows_postgres(rows)


def _upsert_crawled_post_rows_postgres(rows: list[dict[str, Any]]) -> dict[str, str]:
    query = """
    INSERT INTO crawl_posts (
        crawl_job_id, platform_post_id, link, title, author_id, author_name, content, published_at,
        like_count, comment_count, share_count, view_count, reaction_count,
        dedupe_key, extra_data
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s
    )
    ON CONFLICT (link) DO UPDATE SET
        crawl_job_id = EXCLUDED.crawl_job_id,
        platform_post_id = EXCLUDED.platform_post_id,
        title = EXCLUDED.title,
        author_id = EXCLUDED.author_id,
        author_name = EXCLUDED.author_name,
        content = EXCLUDED.content,
        published_at = EXCLUDED.published_at,
        last_seen_at = NOW(),
        like_count = EXCLUDED.like_count,
        comment_count = EXCLUDED.comment_count,
        share_count = EXCLUDED.share_count,
        view_count = EXCLUDED.view_count,
        reaction_count = EXCLUDED.reaction_count,
        crawl_count = crawl_posts.crawl_count + 1,
        dedupe_key = COALESCE(EXCLUDED.dedupe_key, crawl_posts.dedupe_key),
        extra_data = EXCLUDED.extra_data,
        updated_at = NOW()
    RETURNING id, link;
    """

    id_map: dict[str, str] = {}
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        query,
                        (
                            row["crawl_job_id"],
                            row.get("platform_post_id"),
                            row["link"],
                            row.get("title"),
                            row.get("author_id"),
                            row.get("author_name"),
                            row.get("content"),
                            row.get("published_at"),
                            row.get("like_count", 0),
                            row.get("comment_count", 0),
                            row.get("share_count", 0),
                            row.get("view_count", 0),
                            row.get("reaction_count", 0),
                            row.get("dedupe_key"),
                            Json(_json_safe(row.get("extra_data", {}))),
                        ),
                    )
                    post_id, link = cur.fetchone()
                    id_map[link] = str(post_id)
        conn.close()
    except Exception as exc:
        logger.error("crawl_posts database write failed: %s", exc)
    return id_map


def _insert_post_metrics(rows: list[dict[str, Any]]) -> PersistenceStageResult:
    if not rows:
        return PersistenceStageResult("post_metric_snapshots", True, 0, 0)
    rows = [{**row, "like_count": _safe_int(row.get("like_count")), "comment_count": _safe_int(row.get("comment_count")), "share_count": _safe_int(row.get("share_count")), "view_count": _safe_int(row.get("view_count")), "reaction_count": _safe_int(row.get("reaction_count"))} for row in rows]
    query = """
    INSERT INTO post_metric_snapshots (
        crawl_post_id, like_count, comment_count, share_count,
        view_count, reaction_count, average_rating, rating_count, extra_data, collected_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
    """
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(query, (row["crawl_post_id"], row.get("like_count"), row.get("comment_count"), row.get("share_count"), row.get("view_count"), row.get("reaction_count"), row.get("average_rating"), row.get("rating_count"), Json(_json_safe(row.get("extra_data", {}))), row.get("collected_at")))
        conn.close()
        return PersistenceStageResult("post_metric_snapshots", True, len(rows), len(rows))
    except Exception as exc:
        logger.error("post_metrics database write failed: %s", exc)
        return PersistenceStageResult("post_metric_snapshots", False, len(rows), 0, "db_write_failed", str(exc))


def _upsert_comments(rows: list[dict[str, Any]]) -> dict[str, str]:
    if not rows:
        return {}
    db_rows = [_comment_row(row) for row in rows]
    query = """
    INSERT INTO crawl_comments (
        crawl_post_id, platform_comment_id, dedupe_key, author_id, author_name,
        content, published_at, like_count, reply_count, reaction_count, extra_data
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (dedupe_key) DO UPDATE SET
        crawl_post_id = EXCLUDED.crawl_post_id,
        platform_comment_id = EXCLUDED.platform_comment_id,
        author_id = EXCLUDED.author_id,
        author_name = EXCLUDED.author_name,
        content = EXCLUDED.content,
        published_at = EXCLUDED.published_at,
        last_seen_at = NOW(),
        like_count = EXCLUDED.like_count,
        reply_count = EXCLUDED.reply_count,
        reaction_count = EXCLUDED.reaction_count,
        crawl_count = crawl_comments.crawl_count + 1,
        extra_data = EXCLUDED.extra_data,
        updated_at = NOW()
    RETURNING id, dedupe_key;
    """
    id_map: dict[str, str] = {}
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                for row in db_rows:
                    cur.execute(query, (row["crawl_post_id"], row.get("platform_comment_id"), row["dedupe_key"], row.get("author_id"), row.get("author_name"), row["content"], row.get("published_at"), row.get("like_count", 0), row.get("reply_count", 0), row.get("reaction_count", 0), Json(_json_safe(row.get("extra_data", {})))))
                    comment_id, dedupe_key = cur.fetchone()
                    id_map[dedupe_key] = str(comment_id)
        conn.close()
    except Exception as exc:
        logger.error("comments database write failed: %s", exc)
    return id_map


def _insert_comment_metrics(rows: list[dict[str, Any]]) -> PersistenceStageResult:
    if not rows:
        return PersistenceStageResult("comment_metric_snapshots", True, 0, 0)
    rows = [{**row, "like_count": _safe_int(row.get("like_count")), "reply_count": _safe_int(row.get("reply_count")), "reaction_count": _safe_int(row.get("reaction_count")), "rating_value": _safe_float(row.get("rating_value"))} for row in rows]
    query = """
    INSERT INTO comment_metric_snapshots (
        crawl_comment_id, like_count, reply_count, reaction_count, rating_value, collected_at
    ) VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()))
    """
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(query, (row["crawl_comment_id"], row.get("like_count"), row.get("reply_count"), row.get("reaction_count"), row.get("rating_value"), row.get("collected_at")))
        conn.close()
        return PersistenceStageResult("comment_metric_snapshots", True, len(rows), len(rows))
    except Exception as exc:
        logger.error("comment_metrics database write failed: %s", exc)
        return PersistenceStageResult("comment_metric_snapshots", False, len(rows), 0, "db_write_failed", str(exc))


def _search_result_row(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "crawl_job_id": result.get("crawl_job_id") or os.getenv("BI_RMP_CRAWL_JOB_ID"),
        "engine": result["engine"],
        "query": result["query"],
        "title": result.get("title", ""),
        "snippet": result.get("snippet", ""),
        "url": result["url"],
        "domain": result.get("domain"),
        "detected_platform": result.get("detected_platform") or result.get("platform", "web"),
        "rank": result["rank"],
        "raw_json": result.get("raw_json", {}),
    }


def _crawled_post_row(post: dict[str, Any]) -> dict[str, Any]:
    raw_json = post.get("raw_json", {})
    metric = _latest_post_metric(raw_json if isinstance(raw_json, dict) else post)
    extra_data = {"platform": post.get("platform"), "keyword": post.get("keyword"), "post_time_raw": post.get("post_time_raw"), "raw_json": raw_json}
    if isinstance(raw_json, dict):
        for key in ("board", "ptt_metrics", "threads_metrics"):
            if raw_json.get(key) is not None:
                extra_data[key] = raw_json[key]
        google_maps_summary = {
            key: raw_json.get(key)
            for key in ("place_url", "place_id", "cid")
            if raw_json.get(key) is not None
        }
        if google_maps_summary:
            extra_data["google_maps_summary"] = google_maps_summary
    return {
        "crawl_job_id": post.get("crawl_job_id") or os.getenv("BI_RMP_CRAWL_JOB_ID"),
        "link": post["source_url"],
        "platform_post_id": post.get("external_id"),
        "title": post.get("title"),
        "author_id": post.get("author_id"),
        "author_name": post.get("author_name"),
        "content": post.get("content"),
        "published_at": post.get("posted_at"),
        "like_count": metric.get("like_count", 0),
        "comment_count": metric.get("comment_count", 0),
        "share_count": metric.get("share_count", 0),
        "view_count": metric.get("view_count", 0),
        "reaction_count": metric.get("reaction_count", 0),
        "dedupe_key": post.get("dedupe_key"),
        "extra_data": extra_data,
    }


def _comment_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "crawl_post_id": row["crawl_post_id"],
        "platform_comment_id": row.get("external_id"),
        "dedupe_key": row["dedupe_key"],
        "author_id": row.get("author_id"),
        "author_name": row.get("author_name"),
        "content": row["content"],
        "published_at": row.get("commented_at"),
        "like_count": _safe_int(row.get("like_count")),
        "reply_count": _safe_int(row.get("reply_count")),
        "reaction_count": _safe_int(row.get("reaction_count")),
        "extra_data": _comment_extra_data(row),
    }


def _comment_extra_data(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": row.get("platform"),
        "source_url": row.get("source_url"),
        "external_id": row.get("external_id"),
        "rating_value": row.get("rating_value"),
        "sentiment_label": row.get("sentiment_label"),
        "comment_type": row.get("comment_type"),
        "comment_time_raw": row.get("comment_time_raw"),
        "identity_key": row.get("identity_key"),
        "identity_confidence": row.get("identity_confidence"),
        "delta_status": row.get("delta_status"),
        "changed_fields": row.get("changed_fields"),
        "content_hash": row.get("content_hash"),
        "metric_hash": row.get("metric_hash"),
        "lightweight_hash": row.get("lightweight_hash"),
        "raw_json": row.get("raw_json", {}),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _latest_post_metric(item: dict[str, Any]) -> dict[str, int]:
    metric: dict[str, Any] = {}
    for field in ("like_count", "comment_count", "share_count", "view_count", "reaction_count"):
        metric[field] = _safe_int(item.get(field))
    metric["average_rating"] = _safe_float(item.get("average_rating"))
    rating_count = item.get("rating_count")
    if rating_count is None:
        rating_count = item.get("review_count_official")
    metric["rating_count"] = _safe_int(rating_count) if rating_count is not None else None
    return metric


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
