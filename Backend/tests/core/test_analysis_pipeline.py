from __future__ import annotations

from threading import Event

from core.analysis_pipeline import AnalysisJob, PostgresAnalysisQueue, analysis_idempotency_key, process_next


def _job(*, attempt_count: int = 1) -> AnalysisJob:
    return AnalysisJob(
        id=8,
        target_type="crawl_post",
        target_id=4,
        content="bad service",
        attempt_count=attempt_count,
        worker_id="worker-a",
        claim_token="token-a",
    )


class FakeQueue:
    def __init__(
        self,
        job: AnalysisJob | None,
        *,
        complete_result: bool = True,
        heartbeat_result: bool = True,
    ) -> None:
        self.job = job
        self.complete_result = complete_result
        self.heartbeat_result = heartbeat_result
        self.completed: list[tuple[AnalysisJob, dict]] = []
        self.failures: list[tuple[AnalysisJob, str, bool]] = []
        self.claims: list[tuple[int, str, int]] = []
        self.heartbeats: list[tuple[AnalysisJob, int]] = []
        self.heartbeat_called = Event()

    def claim_next(self, *, max_attempts: int, worker_id: str, lease_seconds: int) -> AnalysisJob | None:
        self.claims.append((max_attempts, worker_id, lease_seconds))
        claimed, self.job = self.job, None
        return claimed

    def heartbeat(self, job: AnalysisJob, *, lease_seconds: int) -> bool:
        self.heartbeats.append((job, lease_seconds))
        self.heartbeat_called.set()
        return self.heartbeat_result

    def complete(self, job: AnalysisJob, result: dict) -> bool:
        self.completed.append((job, result))
        return self.complete_result

    def fail(self, job: AnalysisJob, *, error_code: str, retry: bool) -> bool:
        self.failures.append((job, error_code, retry))
        return True


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.queries.append((query, params))

    def fetchone(self):
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def cursor(self):
        return self.cursor_instance

    def close(self) -> None:
        return None


def test_idempotency_key_is_stable_for_same_target_content_and_version():
    first = analysis_idempotency_key(target_type="crawl_post", target_id=12, content="same review")
    second = analysis_idempotency_key(target_type="crawl_post", target_id=12, content="same review")

    assert first == second
    assert first != analysis_idempotency_key(target_type="crawl_post", target_id=12, content="changed review")


def test_worker_completes_rules_baseline_without_exposing_source_content():
    queue = FakeQueue(_job())

    result = process_next(queue, worker_id="worker-a")

    assert result.status == "completed"
    assert queue.completed[0][1]["analysis_status"] == "completed"
    assert queue.completed[0][1]["sentiment"] == "negative"
    assert queue.failures == []


def test_worker_heartbeats_a_claim_while_analysis_is_running():
    queue = FakeQueue(_job())

    def analyzer(_content: str) -> dict:
        assert queue.heartbeat_called.wait(timeout=1)
        return {"analysis_status": "completed"}

    result = process_next(
        queue,
        analyzer=analyzer,
        worker_id="worker-a",
        lease_seconds=2,
        heartbeat_interval_seconds=0.01,
    )

    assert result.status == "completed"
    assert queue.heartbeats == [(_job(), 2)]


def test_worker_does_not_complete_after_losing_claim_fence():
    queue = FakeQueue(_job(), complete_result=False)

    result = process_next(queue, worker_id="worker-a")

    assert result.status == "lost"
    assert len(queue.completed) == 1
    assert queue.failures == []


def test_worker_does_not_write_after_heartbeat_loses_claim():
    queue = FakeQueue(_job(), heartbeat_result=False)

    def analyzer(_content: str) -> dict:
        assert queue.heartbeat_called.wait(timeout=1)
        return {"analysis_status": "completed"}

    result = process_next(
        queue,
        analyzer=analyzer,
        worker_id="worker-a",
        lease_seconds=2,
        heartbeat_interval_seconds=0.01,
    )

    assert result.status == "lost"
    assert queue.completed == []
    assert queue.failures == []


def test_worker_retries_malformed_model_result_before_max_attempts():
    queue = FakeQueue(_job(attempt_count=1))

    result = process_next(queue, analyzer=lambda _content: {"analysis_status": "failed"}, worker_id="worker-a")

    assert result.status == "retry"
    assert queue.failures == [(_job(attempt_count=1), "ValueError", True)]


def test_worker_retries_second_attempt_before_max_attempts():
    queue = FakeQueue(_job(attempt_count=2))

    result = process_next(queue, analyzer=lambda _content: {"analysis_status": "failed"}, worker_id="worker-a")

    assert result.status == "retry"
    assert queue.failures == [(_job(attempt_count=2), "ValueError", True)]


def test_worker_marks_terminal_failure_at_attempt_limit():
    queue = FakeQueue(_job(attempt_count=3))

    result = process_next(queue, analyzer=lambda _content: {"analysis_status": "failed"}, worker_id="worker-a")

    assert result.status == "failed"
    assert queue.failures == [(_job(attempt_count=3), "ValueError", False)]


def test_worker_sanitizes_analyzer_exception_content(caplog):
    source_content = "private review text must not reach logs"
    queue = FakeQueue(
        AnalysisJob(8, "crawl_post", 4, source_content, 1, "worker-a", "token-a")
    )

    def analyzer(_content: str) -> dict:
        raise RuntimeError(source_content)

    result = process_next(queue, analyzer=analyzer, worker_id="worker-a")

    assert result.status == "retry"
    assert source_content not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "token-a" not in caplog.text


def test_worker_is_idle_when_no_job_is_available():
    assert process_next(FakeQueue(None), worker_id="worker-a").status == "idle"


def test_postgres_claim_recovery_fences_queue_rows_and_fails_exhausted_attempts(monkeypatch):
    connection = RecordingConnection()
    monkeypatch.setattr("core.supabase.get_connection", lambda: connection)

    result = PostgresAnalysisQueue().claim_next(max_attempts=3, worker_id="worker-a", lease_seconds=600)

    assert result is None
    recovery_sql, recovery_params = connection.cursor_instance.queries[0]
    claim_sql, claim_params = connection.cursor_instance.queries[1]
    assert "CASE WHEN attempt_count >= %s THEN 'failed' ELSE 'pending' END" in recovery_sql
    assert "idempotency_key IS NOT NULL" in recovery_sql
    assert "lease_expires_at <= NOW()" in recovery_sql
    assert recovery_params == (3, 3)
    assert "FOR UPDATE SKIP LOCKED" in claim_sql
    assert "attempt_count < %s" in claim_sql
    assert claim_params == (3,)


def test_postgres_fenced_mutations_require_worker_claim_token_and_live_lease(monkeypatch):
    connection = RecordingConnection()
    monkeypatch.setattr("core.supabase.get_connection", lambda: connection)
    job = _job()

    assert PostgresAnalysisQueue().heartbeat(job, lease_seconds=600) is False
    heartbeat_sql, heartbeat_params = connection.cursor_instance.queries[-1]
    assert "worker_id = %s AND claim_token = %s AND lease_expires_at > NOW()" in heartbeat_sql
    assert heartbeat_params == (600, job.id, job.worker_id, job.claim_token)

    assert PostgresAnalysisQueue().complete(job, {"topic": []}) is False
    complete_sql, complete_params = connection.cursor_instance.queries[-1]
    assert "worker_id = %s AND claim_token = %s AND lease_expires_at > NOW()" in complete_sql
    assert complete_params[-3:] == (job.id, job.worker_id, job.claim_token)

    assert PostgresAnalysisQueue().fail(job, error_code="RuntimeError", retry=True) is False
    fail_sql, fail_params = connection.cursor_instance.queries[-1]
    assert "worker_id = %s AND claim_token = %s AND lease_expires_at > NOW()" in fail_sql
    assert fail_params[-3:] == (job.id, job.worker_id, job.claim_token)
