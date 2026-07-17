from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPUTATION_CRAWL_KEYWORD = "店家特色"


@dataclass(frozen=True)
class ReputationCrawlResult:
    status: str
    business_name: str | None
    duration_seconds: float
    keyword: str = DEFAULT_REPUTATION_CRAWL_KEYWORD
    lookback_days: int = 0
    articles_found: int | None = None
    comments_found: int | None = None
    canonical_posts_written: int | None = None
    canonical_comments_written: int | None = None
    return_code: int | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None
    reason: str | None = None
    task_id: str | None = None
    platform_results: list[dict[str, Any]] | None = None
    timings: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration_seconds"] = round(self.duration_seconds, 2)
        return data


class ReputationCrawlService:
    """Run the registered business reputation crawler before building a report."""

    def __init__(
        self,
        *,
        runner_path: Path | None = None,
        timeout_seconds: float | None = None,
        max_minutes: float | None = None,
        ptt_max_minutes: float | None = None,
        google_maps_max_minutes: float | None = None,
        threads_max_minutes: float | None = None,
        browser_concurrency: int | None = None,
        persistence_grace_seconds: float | None = None,
        max_results: int | None = None,
        platform: str | None = None,
        keyword: str | None = None,
        lookback_days: int | None = None,
    ) -> None:
        backend_dir = Path(__file__).resolve().parents[1]
        self._runner_path = runner_path or backend_dir / "runner.py"
        self._repo_root = backend_dir.parent
        self._timeout_seconds = timeout_seconds or _positive_float_env(
            "BI_RMP_REPUTATION_CRAWL_TIMEOUT_SECONDS", 600.0
        )
        self._max_minutes = max_minutes or _positive_float_env(
            "BI_RMP_REPUTATION_CRAWL_MAX_MINUTES", 2.0
        )
        self._ptt_max_minutes = ptt_max_minutes or _positive_float_env(
            "BI_RMP_REPUTATION_CRAWL_PTT_MAX_MINUTES", self._max_minutes
        )
        self._google_maps_max_minutes = google_maps_max_minutes or _positive_float_env(
            "BI_RMP_REPUTATION_CRAWL_GOOGLE_MAPS_MAX_MINUTES", 3.0
        )
        self._threads_max_minutes = threads_max_minutes or _positive_float_env(
            "BI_RMP_REPUTATION_CRAWL_THREADS_MAX_MINUTES", 3.0
        )
        self._browser_concurrency = browser_concurrency or _positive_int_env(
            "BI_RMP_REPUTATION_CRAWL_BROWSER_CONCURRENCY", 2
        )
        self._persistence_grace_seconds = (
            persistence_grace_seconds
            if persistence_grace_seconds is not None
            else _nonnegative_float_env(
                "BI_RMP_REPUTATION_CRAWL_PERSISTENCE_GRACE_SECONDS", 30.0
            )
        )
        self._max_results = max_results or _positive_int_env(
            "BI_RMP_REPUTATION_CRAWL_MAX_RESULTS", 50
        )
        self._platform = platform or os.getenv("BI_RMP_REPUTATION_CRAWL_PLATFORM", "all").strip() or "all"
        self._keyword = keyword or DEFAULT_REPUTATION_CRAWL_KEYWORD
        self._lookback_days = lookback_days if lookback_days is not None else 0

    async def crawl(
        self,
        *,
        business_name: str,
        line_user_id: str,
        service_task_id: str | None = None,
        source_message_id: str | None = None,
    ) -> ReputationCrawlResult:
        if not _bool_env("BI_RMP_REPUTATION_CRAWL_ENABLED", True):
            return ReputationCrawlResult(
                status="skipped",
                business_name=business_name,
                duration_seconds=0.0,
                keyword=self._keyword,
                lookback_days=self._lookback_days,
                reason="reputation crawl is disabled",
            )
        if not self._runner_path.exists():
            return ReputationCrawlResult(
                status="failed",
                business_name=business_name,
                duration_seconds=0.0,
                keyword=self._keyword,
                lookback_days=self._lookback_days,
                reason=f"crawler runner not found: {self._runner_path}",
            )

        command = self.build_command(
            business_name=business_name,
            line_user_id=line_user_id,
            service_task_id=service_task_id,
            source_message_id=source_message_id,
        )
        started = time.monotonic()
        process_kwargs: dict[str, Any] = {}
        if os.name != "nt":
            process_kwargs["start_new_session"] = True

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self._repo_root),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **process_kwargs,
            )
        except OSError as exc:
            return ReputationCrawlResult(
                status="failed",
                business_name=business_name,
                duration_seconds=time.monotonic() - started,
                keyword=self._keyword,
                lookback_days=self._lookback_days,
                reason=f"unable to start crawler: {exc}",
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except asyncio.CancelledError:
            await _terminate_process(process)
            raise
        except TimeoutError:
            await _terminate_process(process)
            return ReputationCrawlResult(
                status="timeout",
                business_name=business_name,
                duration_seconds=time.monotonic() - started,
                keyword=self._keyword,
                lookback_days=self._lookback_days,
                return_code=process.returncode,
                reason=f"crawler exceeded {self._timeout_seconds:g} seconds",
            )

        parsed_summary = _parse_runner_summary(stdout)
        return ReputationCrawlResult(
            status=(
                parsed_summary["status"]
                if process.returncode == 0
                else "failed"
            ),
            business_name=business_name,
            duration_seconds=time.monotonic() - started,
            keyword=self._keyword,
            lookback_days=self._lookback_days,
            articles_found=parsed_summary["articles_found"],
            comments_found=parsed_summary["comments_found"],
            canonical_posts_written=parsed_summary["canonical_posts_written"],
            canonical_comments_written=parsed_summary["canonical_comments_written"],
            return_code=process.returncode,
            stdout_tail=_decode_tail(stdout),
            stderr_tail=_decode_tail(stderr),
            reason=(
                parsed_summary.get("reason")
                if process.returncode == 0
                else "crawler process returned a non-zero exit code"
            ),
            task_id=service_task_id,
            platform_results=parsed_summary["platform_results"],
            timings=parsed_summary["timings"],
        )

    def build_command(
        self,
        *,
        business_name: str,
        line_user_id: str,
        service_task_id: str | None = None,
        source_message_id: str | None = None,
    ) -> list[str]:
        command = [
            sys.executable,
            str(self._runner_path),
            "--business-name",
            business_name,
            "--keyword",
            self._keyword,
            "--client-name",
            line_user_id,
            "--line-user-id",
            line_user_id,
            "--max-minutes",
            str(self._max_minutes),
            "--ptt-max-minutes",
            str(self._ptt_max_minutes),
            "--google-maps-max-minutes",
            str(self._google_maps_max_minutes),
            "--threads-max-minutes",
            str(self._threads_max_minutes),
            "--browser-concurrency",
            str(self._browser_concurrency),
            "--persistence-grace-seconds",
            str(self._persistence_grace_seconds),
            "--max-results",
            str(self._max_results),
            "--platform",
            self._platform,
            "--lookback-days",
            str(self._lookback_days),
            "--google-maps-lookback-days",
            str(self._lookback_days),
            "--json-summary",
        ]
        if service_task_id:
            command.extend(["--service-task-id", str(service_task_id)])
        if source_message_id:
            command.extend(["--source-message-id", source_message_id])
        return command


class ReputationCrawlJobService:
    """Create, run and inspect LINE-triggered reputation crawl jobs."""

    def __init__(
        self,
        crawler: ReputationCrawlService | None = None,
        task_repository=None,
        max_active_jobs: int | None = None,
    ) -> None:
        from core.task_repositories import ServiceTaskRepository

        self._crawler = crawler or ReputationCrawlService()
        self._tasks = task_repository or ServiceTaskRepository()
        self._semaphore = asyncio.Semaphore(
            max_active_jobs
            or _positive_int_env("BI_RMP_REPUTATION_CRAWL_MAX_ACTIVE_JOBS", 1)
        )
        self._state_lock = asyncio.Lock()
        self._create_lock = asyncio.Lock()
        self._active_jobs: set[str] = set()

    async def create_job(
        self,
        *,
        business_name: str,
        line_user_id: str,
        source_message_id: str | None,
    ) -> dict[str, Any]:
        async with self._create_lock:
            existing = None
            if source_message_id:
                existing = await asyncio.to_thread(
                    self._tasks.find_reputation_job,
                    line_user_id=line_user_id,
                    source_message_id=source_message_id,
                )
            if existing is None:
                existing = await asyncio.to_thread(
                    self._tasks.find_reputation_job,
                    line_user_id=line_user_id,
                    active_only=True,
                )
            if existing is not None:
                return {**existing, "reused": True}

            task_id = await asyncio.to_thread(
                self._tasks.create,
                service_type="reputation_monitoring",
                schedule_type="once",
                channel="line_bot",
                client_name=line_user_id,
                business_name=business_name,
                line_user_id=line_user_id,
                source_message_id=source_message_id,
                request_payload={
                    "keyword": self._crawler._keyword,
                    "platforms": self._crawler._platform,
                    "lookback_days": self._crawler._lookback_days,
                    "max_results": self._crawler._max_results,
                    "browser_concurrency": getattr(
                        self._crawler,
                        "_browser_concurrency",
                        2,
                    ),
                    "persistence_grace_seconds": getattr(
                        self._crawler,
                        "_persistence_grace_seconds",
                        30.0,
                    ),
                },
            )
            if task_id is None:
                raise RuntimeError("unable to create reputation crawl task")
            created = await asyncio.to_thread(self._tasks.get_reputation_job, task_id)
            return {**(created or {"task_id": task_id, "status": "pending"}), "reused": False}

    async def run_job(self, task_id: str) -> dict[str, Any]:
        job = await asyncio.to_thread(self._tasks.get_reputation_job, task_id)
        if job is None:
            raise KeyError(task_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return await self.status(task_id)
        if job["status"] == "running":
            status = await self.status(task_id)
            return {**status, "already_running": True}

        async with self._state_lock:
            if task_id in self._active_jobs:
                status = await self.status(task_id)
                return {**status, "already_running": True}
            self._active_jobs.add(task_id)

        result: ReputationCrawlResult | None = None
        try:
            async with self._semaphore:
                claimed = await asyncio.to_thread(self._tasks.claim_pending, task_id)
                if not claimed:
                    status = await self.status(task_id)
                    return {**status, "already_running": status.get("status") == "running"}
                config = job.get("config") or {}
                result = await self._crawler.crawl(
                    business_name=job["business_name"],
                    line_user_id=job["line_user_id"],
                    service_task_id=task_id,
                    source_message_id=config.get("source_message_id"),
                )
                if result.status in {"failed", "timeout", "skipped"}:
                    await asyncio.to_thread(
                        self._tasks.mark_failed,
                        task_id,
                        result.reason or result.status,
                    )
        except Exception as exc:
            await asyncio.to_thread(self._tasks.mark_failed, task_id, str(exc))
            raise
        finally:
            async with self._state_lock:
                self._active_jobs.discard(task_id)

        status = await self.status(task_id)
        if result is not None:
            status["result"] = result.to_dict()
        return status

    async def status(
        self,
        task_id: str,
        *,
        line_user_id: str | None = None,
    ) -> dict[str, Any]:
        status = await asyncio.to_thread(
            self._tasks.get_reputation_job_status,
            task_id,
            line_user_id=line_user_id,
        )
        if status is None:
            raise KeyError(task_id)
        return status

    async def latest_status(self, *, line_user_id: str) -> dict[str, Any]:
        job = await asyncio.to_thread(
            self._tasks.find_reputation_job,
            line_user_id=line_user_id,
        )
        if job is None:
            raise KeyError(line_user_id)
        return await self.status(job["task_id"], line_user_id=line_user_id)


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name != "nt" and process.pid:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        await asyncio.wait_for(process.wait(), timeout=5)
    except (ProcessLookupError, TimeoutError):
        if process.returncode is None:
            try:
                if os.name != "nt" and process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


def _decode_tail(payload: bytes | None, limit: int = 2000) -> str | None:
    if not payload:
        return None
    text = payload.decode("utf-8", errors="replace").strip()
    return text[-limit:] or None


def _parse_runner_summary(payload: bytes | None) -> dict[str, Any]:
    empty = {
        "status": "failed",
        "articles_found": None,
        "comments_found": None,
        "canonical_posts_written": None,
        "canonical_comments_written": None,
        "platform_results": [],
        "timings": {},
        "reason": "runner summary was unavailable",
    }
    if not payload:
        return empty
    text = payload.decode("utf-8", errors="replace").strip()
    for line in reversed(text.splitlines()):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        results = data.get("results")
        if not isinstance(results, list):
            continue
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        successful = sum(
            1
            for item in results
            if isinstance(item, dict) and item.get("status") in {"success", "partial_success"}
        )
        failed = sum(
            1
            for item in results
            if isinstance(item, dict) and item.get("status") not in {"success", "partial_success", "skipped"}
        )
        status = "partial_success" if successful and failed else ("failed" if failed else "success")
        return {
            "status": status,
            "articles_found": sum(_safe_int(item.get("cards_found")) for item in results if isinstance(item, dict)),
            "comments_found": sum(_safe_int(item.get("comments_found")) for item in results if isinstance(item, dict)),
            "canonical_posts_written": sum(_safe_int(item.get("canonical_posts_written") or item.get("inserted")) for item in results if isinstance(item, dict)),
            "canonical_comments_written": sum(_safe_int(item.get("canonical_comments_written")) for item in results if isinstance(item, dict)),
            "platform_results": results,
            "timings": {
                "total_seconds": summary.get("elapsed"),
                "platform_seconds": {
                    item.get("platform", "unknown"): item.get("elapsed")
                    for item in results
                    if isinstance(item, dict)
                },
            },
            "reason": "; ".join(summary.get("recent_errors") or []) or None,
        }
    return empty


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _nonnegative_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value >= 0 else default


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default
