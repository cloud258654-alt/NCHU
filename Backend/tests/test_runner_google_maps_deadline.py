import asyncio
import sys
import time as wall_time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import runner


class FakeServiceTaskRepository:
    def __init__(self, calls, created_tasks):
        self.calls = calls
        self.created_tasks = created_tasks

    def create(self, **kwargs):
        self.created_tasks.append(kwargs)
        return "service-task-1"

    def mark_running(self, task_id):
        self.calls.append(("task_running", task_id))

    def mark_finished(self, task_id):
        self.calls.append(("task_finished", task_id))

    def mark_failed(self, task_id, error_message):
        self.calls.append(("task_failed", task_id, error_message))


class FakeCrawlJobRepository:
    def __init__(self, calls):
        self.calls = calls
        self.created = 0

    def create(self, **kwargs):
        self.created += 1
        job_id = f"crawl-job-{self.created}"
        self.calls.append(("crawl_job_created", kwargs["platform"], job_id))
        return job_id

    def merge_execution_config(self, job_id, values):
        self.calls.append(("crawl_job_config", job_id, values))

    def mark_started(self, job_id):
        self.calls.append(("crawl_job_started", job_id))

    def mark_failed(self, job_id, error_message):
        self.calls.append(("crawl_job_failed", job_id, error_message))


def _patch_runner_repositories(monkeypatch, calls, created_tasks):
    monkeypatch.setattr(
        runner,
        "ServiceTaskRepository",
        lambda: FakeServiceTaskRepository(calls, created_tasks),
    )
    crawl_jobs = FakeCrawlJobRepository(calls)
    monkeypatch.setattr(runner, "CrawlJobRepository", lambda: crawl_jobs)


def test_no_platform_keeps_default_mvp_platforms():
    selected = runner._selected_platforms(
        requested_platform="all",
        available_platforms=("google_maps", "ptt", "threads", "web"),
    )

    assert selected == ["ptt", "google_maps", "threads"]


@pytest.mark.asyncio
async def test_google_maps_deadline_is_shared_and_platform_args_are_copied(monkeypatch):
    calls = []
    created_tasks = []
    monotonic_ticks = iter([100.0, 102.0, 102.0, 102.0])

    class FakeDateTime:
        @classmethod
        def now(cls, tz):
            calls.append(("started_at", tz))
            return datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def fake_discover_platform_urls(*, business_name, keyword=None, platforms=None, deadline=None, diagnostics=None):
        calls.append(("discover", business_name, keyword, platforms, deadline))
        diagnostics["selected_source"] = "duckduckgo"
        return {"google_maps": "https://www.google.com/maps/place/Example"}

    async def fake_run_platform(platform, args):
        calls.append(("run_platform", platform, args.url, args.max_minutes))
        return {
            "platform": platform,
            "status": "success",
            "inserted": 0,
            "cards_found": 1,
            "comments_found": 0,
            "elapsed": 0.1,
        }

    def fake_summarize_results(results, *, started_at):
        calls.append(("summary", started_at))
        return {"total": len(results)}

    monkeypatch.setattr(runner, "datetime", FakeDateTime)
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: next(monotonic_ticks)))
    monkeypatch.setattr(runner, "load_builtin_crawlers", lambda: None)
    monkeypatch.setattr(runner.CrawlerRegistry, "available", lambda: ("ptt", "google_maps", "threads"))
    monkeypatch.setattr(runner, "discover_platform_urls", fake_discover_platform_urls)
    monkeypatch.setattr(runner, "run_platform", fake_run_platform)
    monkeypatch.setattr(runner, "summarize_results", fake_summarize_results)
    _patch_runner_repositories(monkeypatch, calls, created_tasks)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner.py",
            "--platform",
            "all",
            "--business-name",
            "Example Store",
            "--keyword",
            "ramen",
            "--max-minutes",
            "1",
            "--dry-run",
        ],
    )

    await runner.main()

    assert calls[0][0] == "started_at"
    discover_call = next(call for call in calls if call[0] == "discover")
    assert discover_call[2] is None
    assert discover_call[4] == pytest.approx(160.0)
    platform_calls = [call for call in calls if call[0] == "run_platform"]
    platform_call_by_name = {call[1]: call for call in platform_calls}
    assert platform_call_by_name["ptt"][2:] == (None, pytest.approx(1.0))
    assert platform_call_by_name["google_maps"][2:] == (
        "https://www.google.com/maps/place/Example",
        pytest.approx(58.0 / 60.0),
    )
    assert platform_call_by_name["threads"][2:] == (None, pytest.approx(1.0))
    config_call = next(call for call in calls if call[0] == "crawl_job_config")
    assert config_call[2]["source_discovery"]["selected_source"] == "duckduckgo"
    assert created_tasks[0]["request_payload"]["source_discovery"] == {"google_maps": "pending"}
    assert ("task_finished", "service-task-1") in calls


@pytest.mark.asyncio
async def test_google_maps_does_not_run_crawler_after_discovery_exhausts_deadline(monkeypatch):
    calls = []
    created_tasks = []
    monotonic_ticks = iter([100.0, 106.1, 106.1, 106.1])

    async def fake_discover_platform_urls(*, business_name, keyword=None, platforms=None, deadline=None, diagnostics=None):
        diagnostics["selected_source"] = "generated_fallback"
        return {"google_maps": "https://www.google.com/maps/search/Example"}

    async def fake_run_platform(platform, args):
        raise AssertionError("Google Maps crawler should not run after discovery consumes the deadline")

    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: next(monotonic_ticks)))
    monkeypatch.setattr(runner, "load_builtin_crawlers", lambda: None)
    monkeypatch.setattr(runner.CrawlerRegistry, "available", lambda: ("google_maps",))
    monkeypatch.setattr(runner, "discover_platform_urls", fake_discover_platform_urls)
    monkeypatch.setattr(runner, "run_platform", fake_run_platform)
    _patch_runner_repositories(monkeypatch, calls, created_tasks)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner.py",
            "--platform",
            "google_maps",
            "--business-name",
            "Example Store",
            "--max-minutes",
            "0.1",
            "--dry-run",
        ],
    )

    await runner.main()

    failed = [call for call in calls if call[0] == "task_failed"]
    assert len(failed) == 1
    assert "Google Maps deadline expired during source discovery" in failed[0][2]
    assert created_tasks[0]["request_payload"]["platforms"] == ["google_maps"]


@pytest.mark.asyncio
async def test_google_maps_does_not_start_crawler_with_too_little_remaining_time(monkeypatch):
    calls = []
    created_tasks = []
    monotonic_ticks = iter([100.0, 102.5, 102.5, 102.5])

    async def fake_discover_platform_urls(*, business_name, keyword=None, platforms=None, deadline=None, diagnostics=None):
        diagnostics["selected_source"] = "generated_fallback"
        return {"google_maps": "https://www.google.com/maps/search/Example"}

    async def fake_run_platform(platform, args):
        raise AssertionError("Google Maps crawler should not start with too little remaining time")

    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: next(monotonic_ticks)))
    monkeypatch.setattr(runner, "load_builtin_crawlers", lambda: None)
    monkeypatch.setattr(runner.CrawlerRegistry, "available", lambda: ("google_maps",))
    monkeypatch.setattr(runner, "discover_platform_urls", fake_discover_platform_urls)
    monkeypatch.setattr(runner, "run_platform", fake_run_platform)
    _patch_runner_repositories(monkeypatch, calls, created_tasks)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner.py",
            "--platform",
            "google_maps",
            "--business-name",
            "Example Store",
            "--max-minutes",
            "0.1",
            "--dry-run",
        ],
    )

    await runner.main()

    failed = [call for call in calls if call[0] == "task_failed"]
    assert len(failed) == 1
    assert "insufficient remaining time" in failed[0][2]
    config_call = next(call for call in calls if call[0] == "crawl_job_config")
    assert config_call[2]["target_url"].endswith("/Example")


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["ptt", "threads"])
async def test_non_google_maps_platforms_skip_source_discovery(monkeypatch, platform):
    calls = []
    created_tasks = []

    async def fail_discover_platform_urls(**kwargs):
        raise AssertionError("Google Maps source discovery should not run")

    async def fake_run_platform(platform_name, args):
        calls.append(("run_platform", platform_name, args.url))
        return {
            "platform": platform_name,
            "status": "success",
            "inserted": 0,
            "cards_found": 1,
            "comments_found": 0,
            "elapsed": 0.1,
        }

    monkeypatch.setattr(runner, "load_builtin_crawlers", lambda: None)
    monkeypatch.setattr(runner.CrawlerRegistry, "available", lambda: ("ptt", "google_maps", "threads"))
    monkeypatch.setattr(runner, "discover_platform_urls", fail_discover_platform_urls)
    monkeypatch.setattr(runner, "run_platform", fake_run_platform)
    _patch_runner_repositories(monkeypatch, calls, created_tasks)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner.py",
            "--platform",
            platform,
            "--business-name",
            "Example Store",
            "--keyword",
            "ramen",
            "--dry-run",
        ],
    )

    await runner.main()

    assert ("run_platform", platform, None) in calls
    assert created_tasks[0]["request_payload"]["source_discovery"] == {}


@pytest.mark.asyncio
async def test_three_platforms_run_concurrently_and_use_platform_time_budgets(monkeypatch):
    calls = []
    created_tasks = []
    delays = {"ptt": 0.06, "google_maps": 0.12, "threads": 0.18}

    async def fake_discover_platform_urls(**kwargs):
        calls.append(("discover_start", wall_time.perf_counter()))
        await asyncio.sleep(0.05)
        calls.append(("discover_finish", wall_time.perf_counter()))
        return {"google_maps": "https://www.google.com/maps/place/Example"}

    async def fake_run_platform(platform, args):
        calls.append(("start", platform, wall_time.perf_counter(), args.max_minutes))
        await asyncio.sleep(delays[platform])
        calls.append(("finish", platform, wall_time.perf_counter()))
        return {
            "platform": platform,
            "status": "success",
            "inserted": 0,
            "cards_found": 1,
            "comments_found": 0,
            "elapsed": delays[platform],
        }

    monkeypatch.setattr(runner, "load_builtin_crawlers", lambda: None)
    monkeypatch.setattr(runner.CrawlerRegistry, "available", lambda: ("ptt", "google_maps", "threads"))
    monkeypatch.setattr(runner, "discover_platform_urls", fake_discover_platform_urls)
    monkeypatch.setattr(runner, "run_platform", fake_run_platform)
    _patch_runner_repositories(monkeypatch, calls, created_tasks)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner.py",
            "--platform",
            "all",
            "--business-name",
            "Example Store",
            "--max-minutes",
            "1",
            "--ptt-max-minutes",
            "2",
            "--google-maps-max-minutes",
            "3",
            "--threads-max-minutes",
            "3",
            "--dry-run",
        ],
    )

    started = wall_time.perf_counter()
    await runner.main()
    elapsed = wall_time.perf_counter() - started

    platform_starts = [call for call in calls if call[0] == "start"]
    platform_start_by_name = {call[1]: call for call in platform_starts}
    platform_finish_by_name = {call[1]: call for call in calls if call[0] == "finish"}
    discover_finish = next(call[1] for call in calls if call[0] == "discover_finish")
    assert set(platform_start_by_name) == {"ptt", "google_maps", "threads"}
    assert platform_start_by_name["ptt"][3] == 2.0
    assert platform_start_by_name["google_maps"][3] == pytest.approx((180.0 - 0.05) / 60, abs=0.01)
    assert platform_start_by_name["threads"][3] == 3.0
    assert platform_start_by_name["ptt"][2] < discover_finish
    assert platform_start_by_name["threads"][2] < discover_finish
    assert platform_start_by_name["google_maps"][2] >= discover_finish
    assert platform_start_by_name["google_maps"][2] < platform_finish_by_name["threads"][2]
    assert elapsed >= max(delays["threads"], 0.05 + delays["google_maps"])
    assert elapsed < 0.28
