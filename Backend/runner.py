from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from datetime import datetime, timezone

from adapters.registry import CrawlerRegistry, load_builtin_crawlers
from core.anti_block import CircuitBreaker, HealthMonitor, RateLimiter, RiskDetector
from core.cli import build_runner_parser
from core.crawl_scheduler import CrawlScheduler, PlatformWork
from core.logger import get_logger, current_service_task_id
from core.post_crawl_analysis import enqueue_post_crawl_analysis
from core.query import build_search_query
from core.run_summary import summarize_results
from core.source_discovery import discover_platform_urls
from core.task_repositories import CrawlJobRepository, ServiceTaskRepository


logger = get_logger("runner")
DEFAULT_MVP_PLATFORMS = ("ptt", "google_maps", "threads")
URL_REQUIRED_PLATFORMS = {"google_maps"}
GOOGLE_MAPS_MIN_CRAWL_SECONDS = 5.0


async def run_platform(platform: str, args) -> dict:
    crawler = CrawlerRegistry.create(platform)
    search_query = getattr(args, "search_query", None) or getattr(args, "keyword", "") or ""
    input_keyword = getattr(args, "input_keyword", None) or None
    health = HealthMonitor(platform=platform, keyword=search_query)
    circuit_breaker = CircuitBreaker()
    rate_limiter = RateLimiter()
    job_repo = CrawlJobRepository()
    service_task_id = getattr(args, "service_task_id", None)
    job_id = getattr(args, "crawl_job_id", None)
    if job_id is None:
        job_id = await asyncio.to_thread(
            job_repo.create,
            platform=platform,
            keyword=input_keyword,
            query=search_query,
            service_task_id=service_task_id,
            target_url=getattr(args, "url", None),
        )
    args.crawl_job_id = job_id
    await asyncio.to_thread(job_repo.mark_started, job_id)
    if getattr(args, "respect_policy", False):
        await rate_limiter.acquire(platform, action="task_start")
    risk_signal = await RiskDetector.check(getattr(args, "url", "") or "")
    if getattr(args, "stop_on_risk", False) and risk_signal.detected:
        circuit_breaker.open(platform, risk_signal.reason or "risk_detected")
        health.record_blocked(risk_signal.reason or "risk_detected")
        result = {
            "platform": platform,
            "status": "failed",
            "inserted": 0,
            "cards_found": 0,
            "elapsed": 0.0,
            "error_message": circuit_breaker.reason(platform),
        }
    else:
        try:
            soft_budget_seconds = max(0.1, float(getattr(args, "max_minutes", 10.0))) * 60
            persistence_grace_seconds = max(
                0.0,
                float(getattr(args, "persistence_grace_seconds", 30.0) or 0.0),
            )
            async with asyncio.timeout(soft_budget_seconds + persistence_grace_seconds):
                result = await crawler.run(args)
        except TimeoutError:
            hard_budget_seconds = (
                max(0.1, float(getattr(args, "max_minutes", 10.0))) * 60
                + max(0.0, float(getattr(args, "persistence_grace_seconds", 30.0) or 0.0))
            )
            result = {
                "platform": platform,
                "status": "failed",
                "inserted": 0,
                "cards_found": 0,
                "comments_found": 0,
                "elapsed": hard_budget_seconds,
                "error_type": "timeout",
                "error_message": f"{platform} crawler exceeded its hard time budget",
            }
        except Exception as exc:
            logger.exception("%s crawler failed without cancelling other platforms", platform)
            result = {
                "platform": platform,
                "status": "failed",
                "inserted": 0,
                "cards_found": 0,
                "comments_found": 0,
                "elapsed": 0.0,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        if result.get("status") == "success":
            health.record_success(result.get("cards_found", 1) or 1)
        else:
            health.record_failure()
    if getattr(args, "risk_report", False):
        result["risk_report"] = health.snapshot().as_dict()
    result["service_task_id"] = service_task_id
    result["crawl_job_id"] = job_id
    success_like = result["status"] == "success" or (
        result["status"] == "partial_success"
        and result.get("error_type") != "persistence_partial_failure"
    )
    if success_like:
        result_summary = _result_summary(result)
        await asyncio.to_thread(
            job_repo.mark_finished,
            job_id,
            total_posts=int(result_summary.get("canonical_posts_written") or 0),
            total_comments=int(result_summary.get("canonical_comments_written") or 0),
            result_summary=result_summary,
        )
        if platform != "search" and not getattr(args, "dry_run", False) and not getattr(args, "skip_ai", False):
            if "ai_items_enqueued" not in result or int(result.get("ai_items_enqueued") or 0) > 0:
                await enqueue_post_crawl_analysis(
                    platform=platform,
                    keyword=search_query,
                    crawl_job_id=job_id,
                )
    else:
        error_message = result.get("error_message") or "Unknown error"
        await asyncio.to_thread(job_repo.mark_failed, job_id, error_message)
    return result


async def _run_selected_platform(
    platform: str,
    args,
    *,
    scheduler: CrawlScheduler,
    crawl_job_id: str | None,
) -> dict:
    platform_args = copy.copy(args)
    platform_args.max_minutes = _platform_max_minutes(platform, args)
    platform_args.crawl_job_id = crawl_job_id
    platform_args.url = None
    source_discovery_diagnostics: dict = {}
    source_discovery_seconds = 0.0
    google_maps_budget_seconds = platform_args.max_minutes * 60
    google_maps_deadline = None

    if platform == "google_maps":
        source_discovery_started = time.monotonic()
        google_maps_deadline = source_discovery_started + google_maps_budget_seconds
        try:
            source_urls = await discover_platform_urls(
                business_name=args.business_name,
                keyword=None,
                platforms=["google_maps"],
                deadline=google_maps_deadline,
                diagnostics=source_discovery_diagnostics,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            source_urls = await discover_platform_urls(
                business_name=args.business_name,
                keyword=getattr(args, "input_keyword", None),
            )
        source_discovery_seconds = time.monotonic() - source_discovery_started
        platform_args.url = source_urls.get("google_maps")
        if crawl_job_id is not None:
            await asyncio.to_thread(
                CrawlJobRepository().merge_execution_config,
                crawl_job_id,
                {
                    "target_url": platform_args.url,
                    "source_discovery": source_discovery_diagnostics,
                    "source_discovery_seconds": round(source_discovery_seconds, 3),
                },
            )

    if platform in URL_REQUIRED_PLATFORMS and not platform_args.url:
        result = {
            "platform": platform,
            "status": "failed",
            "inserted": 0,
            "cards_found": 0,
            "comments_found": 0,
            "elapsed": 0.0,
            "error_type": "source_url_missing",
            "error_message": "required source URL was not discovered",
        }
        logger.warning("Failing %s preflight: %s", platform, result["error_message"])
        result["source_discovery"] = source_discovery_diagnostics
        result["source_discovery_seconds"] = round(source_discovery_seconds, 3)
        return await _record_preflight_failure(platform, platform_args, result)

    if platform == "google_maps" and google_maps_deadline is not None:
        remaining = max(0.0, google_maps_deadline - time.monotonic())
        if remaining <= 0:
            return await _record_preflight_failure(platform, platform_args, {
                "platform": "google_maps",
                "status": "failed",
                "inserted": 0,
                "cards_found": 0,
                "comments_found": 0,
                "elapsed": google_maps_budget_seconds,
                "error_type": "timeout",
                "error_message": "Google Maps deadline expired during source discovery",
                "source_discovery": source_discovery_diagnostics,
                "source_discovery_seconds": round(source_discovery_seconds, 3),
            })
        if remaining < GOOGLE_MAPS_MIN_CRAWL_SECONDS:
            return await _record_preflight_failure(platform, platform_args, {
                "platform": "google_maps",
                "status": "failed",
                "inserted": 0,
                "cards_found": 0,
                "comments_found": 0,
                "elapsed": google_maps_budget_seconds - remaining,
                "error_type": "timeout",
                "error_message": "Google Maps deadline has insufficient remaining time for crawler startup",
                "source_discovery": source_discovery_diagnostics,
                "source_discovery_seconds": round(source_discovery_seconds, 3),
            })
        logger.info("Google Maps crawler deadline remaining: %.2f seconds", remaining)
        platform_args.max_minutes = remaining / 60

    async def run_adapter() -> dict:
        return await run_platform(platform, platform_args)

    result = await scheduler.run_with_resources(platform, run_adapter)
    if platform == "google_maps":
        result["source_discovery"] = source_discovery_diagnostics
        result["source_discovery_seconds"] = round(source_discovery_seconds, 3)
        result["source_url"] = platform_args.url
    return result


async def _run_selected_platform_guarded(
    platform: str,
    args,
    *,
    scheduler: CrawlScheduler,
    crawl_job_id: str | None,
) -> dict:
    try:
        return await _run_selected_platform(
            platform,
            args,
            scheduler=scheduler,
            crawl_job_id=crawl_job_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Platform pipeline failed before returning a result: platform=%s", platform)
        platform_args = copy.copy(args)
        platform_args.crawl_job_id = crawl_job_id
        platform_args.url = None
        return await _record_preflight_failure(
            platform,
            platform_args,
            {
                "platform": platform,
                "status": "failed",
                "inserted": 0,
                "cards_found": 0,
                "comments_found": 0,
                "elapsed": 0.0,
                "error_type": type(exc).__name__,
                "error_message": str(exc) or type(exc).__name__,
            },
        )


async def _record_preflight_failure(platform: str, args, result: dict) -> dict:
    """Persist a platform that failed before its adapter could safely start."""

    job_repo = CrawlJobRepository()
    job_id = getattr(args, "crawl_job_id", None)
    if job_id is None:
        job_id = await asyncio.to_thread(
            job_repo.create,
            platform=platform,
            keyword=getattr(args, "input_keyword", None),
            query=getattr(args, "search_query", None) or getattr(args, "keyword", "") or "",
            service_task_id=getattr(args, "service_task_id", None),
            target_url=getattr(args, "url", None),
        )
    await asyncio.to_thread(job_repo.mark_started, job_id)
    await asyncio.to_thread(
        job_repo.mark_failed,
        job_id,
        result.get("error_message") or "platform preflight failed",
    )
    result["service_task_id"] = getattr(args, "service_task_id", None)
    result["crawl_job_id"] = job_id
    return result


async def _prepare_platform_jobs(
    platforms: list[str],
    args,
    service_task_id: str | None,
) -> dict[str, str | None]:
    job_repo = CrawlJobRepository()
    job_ids: dict[str, str | None] = {}
    for platform in platforms:
        job_ids[platform] = await asyncio.to_thread(
            job_repo.create,
            platform=platform,
            keyword=getattr(args, "input_keyword", None),
            query=getattr(args, "search_query", None) or getattr(args, "keyword", "") or "",
            service_task_id=service_task_id,
            target_url=None,
        )
    return job_ids


def _cleanup_temp_files() -> None:
    import shutil
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent

    paths_to_clean = [
        backend_dir / "adapters" / "ptt" / "buffer",
        backend_dir / "adapters" / "ptt" / "debug_html",
        root_dir / "debug" / "threads",
    ]

    for path in paths_to_clean:
        if path.exists():
            try:
                shutil.rmtree(path)
                logger.info("Cleaned up temporary directory: %s", path)
            except Exception as exc:
                logger.warning("Failed to clean up temporary directory %s: %s", path, exc)


async def main() -> None:
    load_builtin_crawlers()
    parser = build_runner_parser()
    args = parser.parse_args()
    _validate_runner_args(args, parser)
    _apply_internal_defaults(args)
    _prepare_query_args(args, parser)
    try:
        started = datetime.now(timezone.utc)
        platforms = _selected_platforms(
            requested_platform=getattr(args, "platform", "all"),
            available_platforms=CrawlerRegistry.available(),
        )

        task_repo = ServiceTaskRepository()
        service_task_id = getattr(args, "service_task_id", None)
        if service_task_id is None:
            service_task_id = await asyncio.to_thread(
                task_repo.create,
                service_type=getattr(args, "service_type", "reputation_monitoring"),
                schedule_type=getattr(args, "schedule_type", "once"),
                channel=getattr(args, "channel", "cli"),
                client_id=getattr(args, "client_id", None),
                business_id=getattr(args, "business_id", None),
                client_name=args.client_name,
                business_name=args.business_name,
                line_user_id=getattr(args, "line_user_id", None),
                source_message_id=getattr(args, "source_message_id", None),
                request_payload={
                    "platforms": platforms,
                    "keyword": getattr(args, "input_keyword", None),
                    "query": getattr(args, "search_query", None),
                    "source_discovery": {"google_maps": "pending"} if "google_maps" in platforms else {},
                    "platform_max_minutes": {
                        platform: _platform_max_minutes(platform, args)
                        for platform in platforms
                    },
                    "browser_concurrency": args.browser_concurrency,
                    "persistence_grace_seconds": args.persistence_grace_seconds,
                    "dry_run": getattr(args, "dry_run", False),
                },
            )
        args.service_task_id = service_task_id
        current_service_task_id.set(service_task_id)
        await asyncio.to_thread(task_repo.mark_running, service_task_id)
        platform_job_ids = await _prepare_platform_jobs(platforms, args, service_task_id)
        scheduler = CrawlScheduler(browser_concurrency=args.browser_concurrency)

        logger.info(
            "Enterprise crawler started: client=%s business=%s platforms=%s keyword=%s",
            args.client_name,
            args.business_name,
            platforms,
            getattr(args, "search_query", None) or args.keyword,
        )
        work_items = [
            PlatformWork(
                platform=platform,
                operation=lambda platform=platform: _run_selected_platform_guarded(
                    platform,
                    args,
                    scheduler=scheduler,
                    crawl_job_id=platform_job_ids.get(platform),
                ),
            )
            for platform in platforms
        ]
        results = await scheduler.gather(work_items)
        summary = summarize_results(results, started_at=started)
        summary["source_discovery_seconds"] = round(
            sum(float(result.get("source_discovery_seconds") or 0.0) for result in results),
            3,
        )
        failed = [
            result
            for result in results
            if result.get("status") not in {"success", "skipped"}
            and not (result.get("status") == "partial_success" and result.get("error_type") != "persistence_partial_failure")
        ]
        if failed:
            await asyncio.to_thread(
                task_repo.mark_failed,
                service_task_id,
                "; ".join(result.get("error_message") or result.get("platform", "unknown") for result in failed),
            )
        else:
            await asyncio.to_thread(task_repo.mark_finished, service_task_id)
        logger.info("Enterprise crawler finished: %s", summary)
        if getattr(args, "json_summary", False):
            print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False))
    finally:
        _cleanup_temp_files()



def _prepare_query_args(args, parser) -> None:
    input_keyword = getattr(args, "keyword", None) or None
    search_query = build_search_query(
        business_name=getattr(args, "business_name", None),
        keyword=input_keyword,
    )
    if not getattr(args, "business_name", None):
        parser.error("--business-name is required.")
    if not search_query:
        parser.error("--business-name is required for crawler search.")
    args.input_keyword = input_keyword
    args.search_query = search_query
    args.keyword = search_query


def _validate_runner_args(args, parser) -> None:
    lookback_days = getattr(args, "lookback_days", None)
    if lookback_days is not None and int(lookback_days) < 0:
        parser.error("--lookback-days must be >= 0. Use 0 for an unlimited crawl window.")
    if float(getattr(args, "max_minutes", 0.0) or 0.0) <= 0:
        parser.error("--max-minutes must be > 0.")
    for option in ("ptt_max_minutes", "google_maps_max_minutes", "threads_max_minutes"):
        value = getattr(args, option, None)
        if value is not None and float(value) <= 0:
            parser.error(f"--{option.replace('_', '-')} must be > 0.")
    if int(getattr(args, "browser_concurrency", 0) or 0) <= 0:
        parser.error("--browser-concurrency must be > 0.")
    if float(getattr(args, "persistence_grace_seconds", -1.0)) < 0:
        parser.error("--persistence-grace-seconds must be >= 0.")


def _platform_max_minutes(platform: str, args) -> float:
    option_name = {
        "ptt": "ptt_max_minutes",
        "google_maps": "google_maps_max_minutes",
        "threads": "threads_max_minutes",
    }.get(platform)
    platform_value = getattr(args, option_name, None) if option_name else None
    fallback = getattr(args, "max_minutes", 10.0)
    return max(0.1, float(platform_value if platform_value is not None else fallback))


def _selected_platforms(*, requested_platform: str | None, available_platforms) -> list[str]:
    available = set(available_platforms)
    if requested_platform in (None, "all", "service"):
        requested = DEFAULT_MVP_PLATFORMS
    else:
        requested = (requested_platform,)
    return [platform for platform in requested if platform in available]


def _apply_internal_defaults(args) -> None:
    if not hasattr(args, "platform"):
        args.platform = "all"
    args.url = None
    args.board = None
    args.date_range = "all"
    lookback_days = getattr(args, "lookback_days", None)
    # No option means no date filter. ``0`` is also the explicit unlimited mode;
    # it must not become ``since_days=0`` (which means "from right now").
    args.since_days = None if lookback_days in (None, 0) else int(lookback_days)
    args.start_date = None
    args.end_date = None
    args.headless = "True"
    args.keep_unknown_time = True
    args.channel = "line_bot" if getattr(args, "service_task_id", None) else "cli"
    if not hasattr(args, "source_message_id"):
        args.source_message_id = None
    args.engine = _configured_search_engine()
    args.site = None
    args.searxng_url = os.getenv("SEARXNG_BASE_URL") or None
    args.parse_target = False
    args.store_search_results = False
    args.export_jsonl = None
    args.include_search = False
    args.respect_policy = True
    args.stop_on_risk = True
    args.risk_report = False
    if not hasattr(args, "skip_ai"):
        args.skip_ai = False
    args.fetch_comments = True


def _configured_search_engine() -> str:
    engine = os.getenv("SEARCH_ENGINE", "auto").strip().casefold() or "auto"
    return engine if engine in {"auto", "duckduckgo", "bing", "searxng", "all"} else "auto"


def _result_summary(result: dict) -> dict:
    canonical_posts_written = int(result.get("canonical_posts_written") or result.get("inserted") or 0)
    canonical_comments_written = int(result.get("canonical_comments_written") or 0)
    outcome = result.get("outcome") or _infer_outcome(
        status=result.get("status"),
        error_type=result.get("error_type"),
        discovered_count=int(result.get("cards_found") or 0),
        parsed_count=int(result.get("comments_found") or result.get("cards_found") or 0),
        canonical_posts_written=canonical_posts_written,
        canonical_comments_written=canonical_comments_written,
    )
    technical_success = bool(
        result.get("technical_success")
        if "technical_success" in result
        else result.get("status") in {"success", "partial_success"}
    )
    data_yield_success = bool(
        result.get("data_yield_success")
        if "data_yield_success" in result
        else canonical_posts_written > 0 or canonical_comments_written > 0
    )
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    rolling = diagnostics.get("rolling_delta") if isinstance(diagnostics.get("rolling_delta"), dict) else {}
    return {
        "outcome": outcome,
        "technical_success": technical_success,
        "data_yield_success": data_yield_success,
        "discovered_count": int(result.get("discovered_count") or result.get("cards_found") or 0),
        "fetched_count": int(result.get("fetched_count") or rolling.get("items_scanned") or result.get("cards_found") or 0),
        "parsed_count": int(result.get("parsed_count") or result.get("reviews_scanned") or result.get("comments_found") or result.get("cards_found") or 0),
        "matched_count": int(result.get("matched_count") or rolling.get("items_in_window") or result.get("comments_found") or 0),
        "filtered_count": int(
            result.get("filtered_count")
            or result.get("older_reviews_skipped")
            or rolling.get("older_items_skipped")
            or rolling.get("unknown_time_skipped")
            or 0
        ),
        "cards_found": int(result.get("cards_found") or 0),
        "comments_found": int(result.get("comments_found") or 0),
        "canonical_posts_written": canonical_posts_written,
        "canonical_comments_written": canonical_comments_written,
        "post_metric_snapshots_written": int(result.get("post_metric_snapshots_written") or 0),
        "comment_metric_snapshots_written": int(result.get("comment_metric_snapshots_written") or 0),
        "elapsed": float(result.get("elapsed") or 0.0),
        "source_discovery_seconds": float(result.get("source_discovery_seconds") or 0.0),
        "deadline_reached": bool(
            result.get("deadline_reached")
            or diagnostics.get("deadline_reached")
        ),
        "filter_reasons": _filter_reasons(result, rolling),
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
    }


def _infer_outcome(
    *,
    status: str | None,
    error_type: str | None,
    discovered_count: int,
    parsed_count: int,
    canonical_posts_written: int,
    canonical_comments_written: int,
) -> str:
    if status == "failed":
        return "failed"
    if error_type in {"captcha", "blocked", "restricted", "timeout"}:
        return "blocked"
    if status == "partial_success":
        return "partial_success"
    if canonical_posts_written > 0 or canonical_comments_written > 0:
        return "success_with_data"
    if discovered_count > 0 or parsed_count > 0:
        return "success_no_changes"
    return "success_no_results"


def _filter_reasons(result: dict, rolling: dict) -> dict[str, int]:
    reasons = {}
    outside_lookback = int(result.get("older_reviews_skipped") or rolling.get("older_items_skipped") or 0)
    unknown_time = int(rolling.get("unknown_time_skipped") or 0)
    if outside_lookback:
        reasons["outside_lookback"] = outside_lookback
    if unknown_time:
        reasons["unknown_time"] = unknown_time
    return reasons


if __name__ == "__main__":
    asyncio.run(main())
