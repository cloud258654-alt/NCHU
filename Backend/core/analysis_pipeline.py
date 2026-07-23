from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any, Callable, Protocol

from core.logger import get_logger


logger = get_logger("core.analysis_pipeline")
RULES_BASELINE_METHOD = "rule_based"
RULES_BASELINE_VERSION = "rules-v1"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_LEASE_SECONDS = 600
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class AnalysisJob:
    id: int
    target_type: str
    target_id: int
    content: str
    attempt_count: int
    worker_id: str
    claim_token: str


@dataclass(frozen=True)
class ProcessResult:
    status: str
    job_id: int | None = None
    retry_scheduled: bool = False


class AnalysisQueue(Protocol):
    def claim_next(
        self,
        *,
        max_attempts: int,
        worker_id: str,
        lease_seconds: int,
    ) -> AnalysisJob | None: ...

    def heartbeat(self, job: AnalysisJob, *, lease_seconds: int) -> bool: ...

    def complete(self, job: AnalysisJob, result: dict[str, Any]) -> bool: ...

    def fail(self, job: AnalysisJob, *, error_code: str, retry: bool) -> bool: ...


def analysis_idempotency_key(*, target_type: str, target_id: int, content: str) -> str:
    """Return a stable key for one target/content/rules-version combination."""

    digest = hashlib.sha256(
        f"{RULES_BASELINE_VERSION}|{target_type}|{target_id}|{content}".encode("utf-8")
    ).hexdigest()
    return f"{RULES_BASELINE_METHOD}:{digest}"


class _LeaseHeartbeat:
    """Refresh a fenced lease while an analyzer is executing."""

    def __init__(
        self,
        queue: AnalysisQueue,
        job: AnalysisJob,
        *,
        lease_seconds: int,
        interval_seconds: float,
    ) -> None:
        self._queue = queue
        self._job = job
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self.lost = Event()
        self._thread = Thread(target=self._run, name="analysis-lease-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                if self._queue.heartbeat(self._job, lease_seconds=self._lease_seconds) is False:
                    self.lost.set()
                    return
            except Exception as exc:
                # Do not log source content or claim tokens.
                logger.warning("Analysis heartbeat failed for job %s: %s", self._job.id, type(exc).__name__)
                self.lost.set()
                return


def process_next(
    queue: AnalysisQueue,
    *,
    analyzer: Callable[[str], dict[str, Any]] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    worker_id: str = "analysis-worker",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> ProcessResult:
    """Run one fenced analysis job without exposing source text in diagnostics."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least one")
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be positive")

    job = queue.claim_next(
        max_attempts=max_attempts,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    if job is None:
        return ProcessResult(status="idle")

    heartbeat = _LeaseHeartbeat(
        queue,
        job,
        lease_seconds=lease_seconds,
        interval_seconds=min(heartbeat_interval_seconds, lease_seconds / 2),
    )
    heartbeat.start()
    try:
        result = (analyzer or _rules_baseline)(job.content)
        if heartbeat.lost.is_set():
            return ProcessResult(status="lost", job_id=job.id)
        if result.get("analysis_status") != "completed":
            raise ValueError("analysis_not_completed")
        if queue.complete(job, result) is False:
            return ProcessResult(status="lost", job_id=job.id)
        return ProcessResult(status="completed", job_id=job.id)
    except Exception as exc:
        if heartbeat.lost.is_set():
            return ProcessResult(status="lost", job_id=job.id)
        retry = job.attempt_count < max_attempts
        # Keep only a stable error class/code; model errors can contain source text.
        if queue.fail(job, error_code=type(exc).__name__, retry=retry) is False:
            return ProcessResult(status="lost", job_id=job.id)
        logger.warning("Analysis job %s failed with %s", job.id, type(exc).__name__)
        return ProcessResult(status="retry" if retry else "failed", job_id=job.id, retry_scheduled=retry)
    finally:
        heartbeat.stop()


def _rules_baseline(content: str) -> dict[str, Any]:
    """Small deterministic baseline; LLM execution remains an explicit future mode."""

    normalized = content.casefold()
    positive_terms = ("滿意", "推薦", "友善", "positive", "good")
    negative_terms = ("差勁", "失望", "投訴", "negative", "bad")
    positives = sum(term in normalized for term in positive_terms)
    negatives = sum(term in normalized for term in negative_terms)
    if positives > negatives:
        sentiment, score = "positive", 75
    elif negatives > positives:
        sentiment, score = "negative", 25
    else:
        sentiment, score = "neutral", 50
    return {
        "analysis_status": "completed",
        "analysis_method": RULES_BASELINE_METHOD,
        "sentiment": sentiment,
        "sentiment_score_normalized": score,
        "model_confidence": 0.5 if positives or negatives else 0.25,
        "topic": [],
        "risk_level": "high" if negatives >= 2 else "medium" if negatives else "low",
        "risk_signals": ["negative_language"] if negatives else [],
        "summary": f"Rules baseline classified the target as {sentiment}.",
        "recommendation": "Review the source and respond through the approved customer workflow." if negatives else None,
    }


class PostgresAnalysisQueue:
    """PostgreSQL-backed queue stored in analysis_results with lease fencing."""

    def enqueue_crawl_job(self, crawl_job_id: str) -> int:
        from core.supabase import get_connection
        from psycopg2.extras import Json

        rows = self._load_targets(crawl_job_id)
        if not rows:
            return 0
        queued = 0
        conn = get_connection()
        try:
            with conn:
                with conn.cursor() as cursor:
                    for target_type, target_id, content in rows:
                        key = analysis_idempotency_key(
                            target_type=target_type,
                            target_id=target_id,
                            content=content,
                        )
                        cursor.execute(
                            """
                            INSERT INTO analysis_results (
                                target_type, target_id, analysis_status, analysis_method,
                                idempotency_key, next_attempt_at, score_explanation, updated_at
                            ) VALUES (%s, %s, 'pending', %s, %s, NOW(), %s, NOW())
                            ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
                            RETURNING id
                            """,
                            (
                                target_type,
                                target_id,
                                RULES_BASELINE_METHOD,
                                key,
                                Json({"analysis_version": RULES_BASELINE_VERSION, "queue": "analysis"}),
                            ),
                        )
                        queued += int(cursor.fetchone() is not None)
            return queued
        finally:
            conn.close()

    def _load_targets(self, crawl_job_id: str) -> list[tuple[str, int, str]]:
        from core.supabase import get_connection

        query = """
        SELECT 'crawl_post' AS target_type, cp.id AS target_id, COALESCE(cp.content, cp.title, '') AS content
        FROM crawl_posts cp
        WHERE cp.crawl_job_id = %s AND cp.is_deleted = false
        UNION ALL
        SELECT 'crawl_comment' AS target_type, cc.id AS target_id, cc.content
        FROM crawl_comments cc
        JOIN crawl_posts cp ON cp.id = cc.crawl_post_id
        WHERE cp.crawl_job_id = %s AND cp.is_deleted = false AND cc.is_deleted = false
        """
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, (crawl_job_id, crawl_job_id))
                return [(str(row[0]), int(row[1]), str(row[2] or "")) for row in cursor.fetchall()]
        finally:
            conn.close()

    def claim_next(
        self,
        *,
        max_attempts: int,
        worker_id: str,
        lease_seconds: int,
    ) -> AnalysisJob | None:
        from core.supabase import get_connection

        conn = get_connection()
        try:
            with conn:
                with conn.cursor() as cursor:
                    self._recover_expired_claims(cursor, max_attempts=max_attempts)
                    cursor.execute(
                        """
                        SELECT id, target_type, target_id, attempt_count
                        FROM analysis_results
                        WHERE analysis_status = 'pending'
                          AND idempotency_key IS NOT NULL
                          AND next_attempt_at <= NOW()
                          AND attempt_count < %s
                        ORDER BY next_attempt_at, created_at, id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                        """,
                        (max_attempts,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    claim_token = secrets.token_urlsafe(32)
                    cursor.execute(
                        """
                        UPDATE analysis_results
                        SET analysis_status = 'processing', attempt_count = attempt_count + 1,
                            worker_id = %s, claim_token = %s, locked_at = NOW(), heartbeat_at = NOW(),
                            lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                            last_error = NULL, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (worker_id, claim_token, lease_seconds, row[0]),
                    )
                    content = self._load_target_content(cursor, target_type=str(row[1]), target_id=int(row[2]))
            return AnalysisJob(
                id=int(row[0]),
                target_type=str(row[1]),
                target_id=int(row[2]),
                content=content,
                attempt_count=int(row[3]) + 1,
                worker_id=worker_id,
                claim_token=claim_token,
            )
        finally:
            conn.close()

    @staticmethod
    def _recover_expired_claims(cursor, *, max_attempts: int) -> None:
        cursor.execute(
            """
            UPDATE analysis_results
            SET analysis_status = CASE WHEN attempt_count >= %s THEN 'failed' ELSE 'pending' END,
                next_attempt_at = CASE WHEN attempt_count >= %s THEN NULL ELSE NOW() END,
                worker_id = NULL, claim_token = NULL, locked_at = NULL, heartbeat_at = NULL,
                lease_expires_at = NULL, last_error = 'lease_expired', updated_at = NOW()
            WHERE analysis_status = 'processing'
              AND idempotency_key IS NOT NULL
              AND lease_expires_at <= NOW()
            """,
            (max_attempts, max_attempts),
        )

    @staticmethod
    def _load_target_content(cursor, *, target_type: str, target_id: int) -> str:
        table_name = "crawl_posts" if target_type == "crawl_post" else "crawl_comments"
        content_expression = "COALESCE(content, title, '')" if target_type == "crawl_post" else "content"
        cursor.execute(f"SELECT {content_expression} FROM {table_name} WHERE id = %s", (target_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("analysis_target_missing")
        return str(row[0] or "")

    def heartbeat(self, job: AnalysisJob, *, lease_seconds: int) -> bool:
        from core.supabase import get_connection

        conn = get_connection()
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE analysis_results
                        SET heartbeat_at = NOW(), lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                            updated_at = NOW()
                        WHERE id = %s AND analysis_status = 'processing'
                          AND worker_id = %s AND claim_token = %s AND lease_expires_at > NOW()
                        RETURNING id
                        """,
                        (lease_seconds, job.id, job.worker_id, job.claim_token),
                    )
                    return cursor.fetchone() is not None
        finally:
            conn.close()

    def complete(self, job: AnalysisJob, result: dict[str, Any]) -> bool:
        from core.supabase import get_connection
        from psycopg2.extras import Json

        topics = result.get("topic") or []
        topic = ",".join(str(value) for value in topics) if isinstance(topics, list) else str(topics)
        explanation = {
            "analysis_version": RULES_BASELINE_VERSION,
            "risk_signals": result.get("risk_signals") or [],
        }
        conn = get_connection()
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE analysis_results
                        SET analysis_status = 'completed', analysis_method = %s,
                            sentiment = %s, sentiment_score_normalized = %s,
                            confidence_score = %s, topic = %s, risk_level = %s,
                            summary = %s, recommendation = %s, score_explanation = %s,
                            analyzed_at = NOW(), worker_id = NULL, claim_token = NULL, locked_at = NULL,
                            heartbeat_at = NULL, lease_expires_at = NULL, next_attempt_at = NULL,
                            last_error = NULL, updated_at = NOW()
                        WHERE id = %s AND analysis_status = 'processing'
                          AND worker_id = %s AND claim_token = %s AND lease_expires_at > NOW()
                        RETURNING id
                        """,
                        (
                            result.get("analysis_method") or RULES_BASELINE_METHOD,
                            result.get("sentiment"),
                            result.get("sentiment_score_normalized"),
                            result.get("model_confidence"),
                            topic or None,
                            result.get("risk_level"),
                            result.get("summary"),
                            result.get("recommendation"),
                            Json(explanation),
                            job.id,
                            job.worker_id,
                            job.claim_token,
                        ),
                    )
                    return cursor.fetchone() is not None
        finally:
            conn.close()

    def fail(self, job: AnalysisJob, *, error_code: str, retry: bool) -> bool:
        from core.supabase import get_connection

        backoff_seconds = min(1800, 60 * (2 ** job.attempt_count))
        conn = get_connection()
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE analysis_results
                        SET analysis_status = %s,
                            next_attempt_at = CASE WHEN %s THEN NOW() + (%s * INTERVAL '1 second') ELSE NULL END,
                            worker_id = NULL, claim_token = NULL, locked_at = NULL, heartbeat_at = NULL,
                            lease_expires_at = NULL, last_error = %s, updated_at = NOW()
                        WHERE id = %s AND analysis_status = 'processing'
                          AND worker_id = %s AND claim_token = %s AND lease_expires_at > NOW()
                        RETURNING id
                        """,
                        (
                            "pending" if retry else "failed",
                            retry,
                            backoff_seconds,
                            error_code,
                            job.id,
                            job.worker_id,
                            job.claim_token,
                        ),
                    )
                    return cursor.fetchone() is not None
        finally:
            conn.close()
