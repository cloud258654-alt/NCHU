from __future__ import annotations

import asyncio
import importlib
import os
import sys
import time
from argparse import Namespace
from dataclasses import dataclass
from typing import Any, Protocol

from core.logger import get_logger
from core.retry import retry_async


class Crawler(Protocol):
    platform: str

    async def run(self, args: Namespace) -> dict[str, Any]:
        """Run one platform crawler and return a normalized task summary."""


@dataclass(slots=True)
class CrawlResult:
    platform: str
    status: str
    inserted: int = 0
    cards_found: int = 0
    elapsed: float = 0.0
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "status": self.status,
            "inserted": self.inserted,
            "cards_found": self.cards_found,
            "elapsed": self.elapsed,
            "error_message": self.error_message,
        }


class CommandModuleCrawler:
    """Registry adapter for platform modules that still expose a CLI-style main()."""

    platform: str
    module_name: str
    _legacy_invoke_lock = asyncio.Lock()

    def __init__(self, platform: str, module_name: str) -> None:
        self.platform = platform
        self.module_name = module_name
        self.logger = get_logger(f"crawler.{platform}")

    async def run(self, args: Namespace) -> dict[str, Any]:
        started = time.time()
        argv = self._build_argv(args)
        module = importlib.import_module(self.module_name)
        run_from_args = getattr(module, "run_from_args", None)

        async def _invoke() -> dict[str, Any] | None:
            if run_from_args is not None:
                result = run_from_args(args)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            async with self._legacy_invoke_lock:
                previous_argv = sys.argv[:]
                previous_task_id = os.environ.get("BI_RMP_SERVICE_TASK_ID")
                previous_job_id = os.environ.get("BI_RMP_CRAWL_JOB_ID")
                previous_task_type = os.environ.get("BI_RMP_SERVICE_TYPE")
                previous_input_keyword = os.environ.get("BI_RMP_INPUT_KEYWORD")
                sys.argv = [self.module_name, *argv]
                if getattr(args, "service_task_id", None):
                    os.environ["BI_RMP_SERVICE_TASK_ID"] = str(args.service_task_id)
                if getattr(args, "crawl_job_id", None):
                    os.environ["BI_RMP_CRAWL_JOB_ID"] = str(args.crawl_job_id)
                if getattr(args, "service_type", None):
                    os.environ["BI_RMP_SERVICE_TYPE"] = str(args.service_type)
                if getattr(args, "input_keyword", None) is not None:
                    os.environ["BI_RMP_INPUT_KEYWORD"] = str(args.input_keyword)
                try:
                    main = getattr(module, "main")
                    result = main()
                    if asyncio.iscoroutine(result):
                        result = await result
                    return result
                finally:
                    sys.argv = previous_argv
                    if previous_task_id is None:
                        os.environ.pop("BI_RMP_SERVICE_TASK_ID", None)
                    else:
                        os.environ["BI_RMP_SERVICE_TASK_ID"] = previous_task_id
                    if previous_job_id is None:
                        os.environ.pop("BI_RMP_CRAWL_JOB_ID", None)
                    else:
                        os.environ["BI_RMP_CRAWL_JOB_ID"] = previous_job_id
                    if previous_task_type is None:
                        os.environ.pop("BI_RMP_SERVICE_TYPE", None)
                    else:
                        os.environ["BI_RMP_SERVICE_TYPE"] = previous_task_type
                    if previous_input_keyword is None:
                        os.environ.pop("BI_RMP_INPUT_KEYWORD", None)
                    else:
                        os.environ["BI_RMP_INPUT_KEYWORD"] = previous_input_keyword

        try:
            result = (
                await _invoke()
                if run_from_args is not None
                else await retry_async(_invoke, logger=self.logger)
            )
            if isinstance(result, dict):
                result.setdefault("platform", self.platform)
                result.setdefault("status", "success")
                result.setdefault("elapsed", time.time() - started)
                return result
            return CrawlResult(
                platform=self.platform,
                status="success",
                elapsed=time.time() - started,
            ).as_dict()
        except SystemExit as exc:
            self.logger.error("Platform %s exited before completing: %s", self.platform, exc)
            return CrawlResult(
                platform=self.platform,
                status="failed",
                elapsed=time.time() - started,
                error_message=f"platform exited with code {exc.code}",
            ).as_dict()
        except Exception as exc:
            self.logger.exception("Platform %s failed", self.platform)
            return CrawlResult(
                platform=self.platform,
                status="failed",
                elapsed=time.time() - started,
                error_message=str(exc),
            ).as_dict()

    def _build_argv(self, args: Namespace) -> list[str]:
        argv = [
            "--headless",
            str(args.headless),
            "--max-scroll",
            str(args.max_scroll),
            "--max-minutes",
            str(args.max_minutes),
            "--date-range",
            args.date_range,
            "--service-type",
            getattr(args, "service_type", "reputation_query"),
            "--schedule-type",
            getattr(args, "schedule_type", "once"),
            "--channel",
            getattr(args, "channel", "cli"),
            "--engine",
            getattr(args, "engine", "duckduckgo"),
            "--max-results",
            str(getattr(args, "max_results", 50)),
        ]
        optional_values = {
            "--lookback-days": getattr(args, "lookback_days", None),
            "--client-name": getattr(args, "client_name", None),
            "--business-name": getattr(args, "business_name", None),
            "--keyword": getattr(args, "keyword", None),
            "--client-id": getattr(args, "client_id", None),
            "--business-id": getattr(args, "business_id", None),
            "--since-days": getattr(args, "since_days", None),
            "--start-date": getattr(args, "start_date", None),
            "--end-date": getattr(args, "end_date", None),
            "--url": getattr(args, "url", None),
            "--board": getattr(args, "board", None),
            "--service-task-id": getattr(args, "service_task_id", None),
            "--crawl-job-id": getattr(args, "crawl_job_id", None),
            "--line-user-id": getattr(args, "line_user_id", None),
            "--source-message-id": getattr(args, "source_message_id", None),
            "--site": getattr(args, "site", None),
            "--searxng-url": getattr(args, "searxng_url", None),
            "--export-jsonl": getattr(args, "export_jsonl", None),
            "--platform-max-results": getattr(args, "platform_max_results", None),
            "--platform-max-scroll": getattr(args, "platform_max_scroll", None),
        }
        if self.platform == "google_maps":
            argv.extend(
                [
                    "--google-maps-diff-mode",
                    getattr(args, "google_maps_diff_mode", "fast"),
                ]
            )
            optional_values["--google-maps-lookback-days"] = getattr(args, "google_maps_lookback_days", None)
            optional_values["--google-maps-max-reviews"] = getattr(args, "google_maps_max_reviews", None)
            optional_values["--google-maps-max-scroll"] = getattr(args, "google_maps_max_scroll", None)
        if self.platform == "ptt":
            optional_values["--ptt-max-posts"] = getattr(args, "ptt_max_posts", None)
            optional_values["--ptt-max-pages"] = getattr(args, "ptt_max_pages", None)
        if self.platform == "threads":
            optional_values["--threads-max-posts"] = getattr(args, "threads_max_posts", None)
            optional_values["--threads-max-scroll"] = getattr(args, "threads_max_scroll", None)
        for option, value in optional_values.items():
            if value is not None:
                argv.extend([option, str(value)])
        if getattr(args, "keep_unknown_time", False):
            argv.append("--keep-unknown-time")
        if getattr(args, "dry_run", False):
            argv.append("--dry-run")
        if getattr(args, "skip_ai", False):
            argv.append("--skip-ai")
        if getattr(args, "fetch_comments", False):
            argv.append("--fetch-comments")
        return argv
