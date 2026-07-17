import asyncio
import sys
from argparse import Namespace
from types import SimpleNamespace

import pytest

import runner
from core.cli import build_runner_parser
from core.task_repositories import CrawlJobRepository


def test_no_platform_keeps_default_mvp_platforms():
    selected = runner._selected_platforms(
        requested_platform="all",
        available_platforms=("google_maps", "ptt", "threads", "web"),
    )

    assert selected == ["ptt", "google_maps", "threads"]


@pytest.mark.asyncio
async def test_runner_platform_google_maps_runs_only_google_maps(monkeypatch):
    calls = []
    created_tasks = []

    class FakeServiceTaskRepository:
        def create(self, **kwargs):
            created_tasks.append(kwargs)
            return "service-task-1"

        def mark_running(self, task_id):
            calls.append(("task_running", task_id))

        def mark_finished(self, task_id):
            calls.append(("task_finished", task_id))

        def mark_failed(self, task_id, error_message):
            calls.append(("task_failed", task_id, error_message))

    class FakeCrawlJobRepository:
        def create(self, **kwargs):
            return "crawl-job-1"

        def merge_execution_config(self, job_id, values):
            calls.append(("crawl_job_config", job_id, values))

    async def fake_discover_platform_urls(*, business_name, keyword=None):
        return {"google_maps": "https://www.google.com/maps/search/example"}

    async def fake_run_platform(platform, args):
        calls.append(("run_platform", platform, args.service_task_id, args.url))
        return {
            "platform": platform,
            "status": "success",
            "inserted": 1,
            "cards_found": 1,
            "comments_found": 3,
            "elapsed": 0.1,
        }

    monkeypatch.setattr(runner, "load_builtin_crawlers", lambda: None)
    monkeypatch.setattr(runner.CrawlerRegistry, "available", lambda: ("google_maps", "ptt", "threads"))
    monkeypatch.setattr(runner, "discover_platform_urls", fake_discover_platform_urls)
    monkeypatch.setattr(runner, "ServiceTaskRepository", FakeServiceTaskRepository)
    monkeypatch.setattr(runner, "CrawlJobRepository", FakeCrawlJobRepository)
    monkeypatch.setattr(runner, "run_platform", fake_run_platform)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner.py",
            "--platform",
            "google_maps",
            "--client-name",
            "demo-client",
            "--business-name",
            "天津苟不理湯包",
            "--keyword",
            "天津苟不理湯包",
            "--skip-ai",
        ],
    )

    await runner.main()

    assert ("run_platform", "google_maps", "service-task-1", "https://www.google.com/maps/search/example") in calls
    assert [call[1] for call in calls if call[0] == "run_platform"] == ["google_maps"]
    assert created_tasks[0]["request_payload"]["platforms"] == ["google_maps"]


def test_invalid_platform_is_rejected():
    parser = build_runner_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--business-name", "Example", "--platform", "web"])


def test_configured_search_engine_defaults_to_auto(monkeypatch):
    monkeypatch.delenv("SEARCH_ENGINE", raising=False)

    assert runner._configured_search_engine() == "auto"


def test_configured_search_engine_uses_valid_env(monkeypatch):
    monkeypatch.setenv("SEARCH_ENGINE", "searxng")

    assert runner._configured_search_engine() == "searxng"


def test_configured_search_engine_rejects_invalid_env(monkeypatch):
    monkeypatch.setenv("SEARCH_ENGINE", "google")

    assert runner._configured_search_engine() == "auto"


def test_result_summary_example_separates_source_counts_from_write_counts():
    summary = runner._result_summary(
        {
            "platform": "google_maps",
            "status": "success",
            "outcome": "success_no_changes",
            "cards_found": 1,
            "comments_found": 0,
            "reviews_scanned": 110,
            "older_reviews_skipped": 110,
            "canonical_posts_written": 0,
            "canonical_comments_written": 0,
        }
    )

    assert summary == {
        "outcome": "success_no_changes",
        "technical_success": True,
        "data_yield_success": False,
        "discovered_count": 1,
        "fetched_count": 1,
        "parsed_count": 110,
        "matched_count": 0,
        "filtered_count": 110,
        "cards_found": 1,
        "comments_found": 0,
        "canonical_posts_written": 0,
        "canonical_comments_written": 0,
        "post_metric_snapshots_written": 0,
        "comment_metric_snapshots_written": 0,
        "elapsed": 0.0,
        "source_discovery_seconds": 0.0,
        "deadline_reached": False,
        "filter_reasons": {"outside_lookback": 110},
        "error_type": None,
        "error_message": None,
    }


def test_crawl_job_mark_finished_merges_result_summary_without_replacing_config(monkeypatch):
    captured = {}

    def fake_execute(self, query, params):
        captured["query"] = query
        captured["params"] = params

    monkeypatch.setattr(CrawlJobRepository, "_execute", fake_execute)

    CrawlJobRepository().mark_finished(
        "crawl-job-1",
        total_posts=0,
        total_comments=0,
        result_summary={"outcome": "success_no_changes"},
    )

    assert "execution_config = COALESCE(execution_config, '{}'::jsonb) || %s::jsonb" in captured["query"]
    assert captured["params"][4] == {"result_summary": {"outcome": "success_no_changes"}}
    assert captured["params"][-1] == "crawl-job-1"


@pytest.mark.asyncio
async def test_run_platform_creates_crawl_job_for_selected_platform(monkeypatch):
    created_jobs = []
    transitions = []

    class FakeCrawler:
        async def run(self, args):
            return {
                "platform": "google_maps",
                "status": "success",
                "inserted": 1,
                "cards_found": 1,
                "comments_found": 2,
                "elapsed": 0.1,
            }

    class FakeCrawlJobRepository:
        def create(self, **kwargs):
            created_jobs.append(kwargs)
            return "crawl-job-1"

        def mark_started(self, job_id):
            transitions.append(("started", job_id))

        def mark_finished(self, job_id, *, total_posts=None, total_comments=None, result_summary=None):
            transitions.append(("finished", job_id, total_posts, total_comments, result_summary))

        def mark_failed(self, job_id, error_message):
            transitions.append(("failed", job_id, error_message))

    async def fake_risk_check(value):
        return SimpleNamespace(detected=False, reason=None)

    monkeypatch.setattr(runner.CrawlerRegistry, "create", lambda platform: FakeCrawler())
    monkeypatch.setattr(runner, "CrawlJobRepository", FakeCrawlJobRepository)
    monkeypatch.setattr(runner.RiskDetector, "check", fake_risk_check)

    args = Namespace(
        service_task_id="service-task-1",
        search_query="天津苟不理湯包",
        keyword="天津苟不理湯包",
        input_keyword="天津苟不理湯包",
        url="https://www.google.com/maps/search/example",
        respect_policy=False,
        stop_on_risk=False,
        risk_report=False,
        dry_run=False,
        skip_ai=True,
    )

    result = await runner.run_platform("google_maps", args)

    assert result["status"] == "success"
    assert result["crawl_job_id"] == "crawl-job-1"
    assert created_jobs == [
        {
            "platform": "google_maps",
            "keyword": "天津苟不理湯包",
            "query": "天津苟不理湯包",
            "service_task_id": "service-task-1",
            "target_url": "https://www.google.com/maps/search/example",
        }
    ]
    assert ("started", "crawl-job-1") in transitions
    finished = [transition for transition in transitions if transition[0] == "finished"][0]
    assert finished[1:4] == ("crawl-job-1", 1, 0)
    assert finished[4]["cards_found"] == 1
    assert finished[4]["comments_found"] == 2
    assert finished[4]["canonical_posts_written"] == 1


@pytest.mark.asyncio
async def test_run_platform_marks_persistence_partial_failure_as_failed(monkeypatch):
    transitions = []
    enqueued = []

    class FakeCrawler:
        async def run(self, args):
            return {
                "platform": "google_maps",
                "status": "partial_success",
                "error_type": "persistence_partial_failure",
                "error_message": "post_metric_snapshots: write failed",
                "inserted": 1,
                "cards_found": 1,
                "comments_found": 1,
                "ai_items_enqueued": 1,
                "elapsed": 0.1,
            }

    class FakeCrawlJobRepository:
        def create(self, **kwargs):
            return "crawl-job-1"

        def mark_started(self, job_id):
            transitions.append(("started", job_id))

        def mark_finished(self, job_id, *, total_posts=None, total_comments=None, result_summary=None):
            transitions.append(("finished", job_id, total_posts, total_comments))

        def mark_failed(self, job_id, error_message):
            transitions.append(("failed", job_id, error_message))

    async def fake_risk_check(value):
        return SimpleNamespace(detected=False, reason=None)

    async def fake_enqueue(**kwargs):
        enqueued.append(kwargs)

    monkeypatch.setattr(runner.CrawlerRegistry, "create", lambda platform: FakeCrawler())
    monkeypatch.setattr(runner, "CrawlJobRepository", FakeCrawlJobRepository)
    monkeypatch.setattr(runner.RiskDetector, "check", fake_risk_check)
    monkeypatch.setattr(runner, "enqueue_post_crawl_analysis", fake_enqueue)

    args = Namespace(
        service_task_id="service-task-1",
        search_query="Example",
        keyword="Example",
        input_keyword="Example",
        url="https://www.google.com/maps/search/example",
        respect_policy=False,
        stop_on_risk=False,
        risk_report=False,
        dry_run=False,
        skip_ai=False,
    )

    result = await runner.run_platform("google_maps", args)

    assert result["status"] == "partial_success"
    assert ("failed", "crawl-job-1", "post_metric_snapshots: write failed") in transitions
    assert not any(transition[0] == "finished" for transition in transitions)
    assert enqueued == []


@pytest.mark.asyncio
async def test_run_platform_uses_canonical_write_counts_for_crawl_job(monkeypatch):
    transitions = []

    class FakeCrawler:
        async def run(self, args):
            return {
                "platform": "google_maps",
                "status": "success",
                "outcome": "success_no_changes",
                "inserted": 0,
                "cards_found": 1,
                "comments_found": 0,
                "canonical_posts_written": 0,
                "canonical_comments_written": 0,
                        "elapsed": 0.1,
            }

    class FakeCrawlJobRepository:
        def create(self, **kwargs):
            return "crawl-job-1"

        def mark_started(self, job_id):
            transitions.append(("started", job_id))

        def mark_finished(self, job_id, *, total_posts=None, total_comments=None, result_summary=None):
            transitions.append(("finished", job_id, total_posts, total_comments, result_summary))

        def mark_failed(self, job_id, error_message):
            transitions.append(("failed", job_id, error_message))

    async def fake_risk_check(value):
        return SimpleNamespace(detected=False, reason=None)

    monkeypatch.setattr(runner.CrawlerRegistry, "create", lambda platform: FakeCrawler())
    monkeypatch.setattr(runner, "CrawlJobRepository", FakeCrawlJobRepository)
    monkeypatch.setattr(runner.RiskDetector, "check", fake_risk_check)

    args = Namespace(
        service_task_id="service-task-1",
        search_query="Example",
        keyword="Example",
        input_keyword="Example",
        url="https://www.google.com/maps/search/example",
        respect_policy=False,
        stop_on_risk=False,
        risk_report=False,
        dry_run=False,
        skip_ai=True,
    )

    await runner.run_platform("google_maps", args)

    finished = [transition for transition in transitions if transition[0] == "finished"][0]
    assert finished[2] == 0
    assert finished[3] == 0
    assert finished[4]["cards_found"] == 1
    assert finished[4]["outcome"] == "success_no_changes"


@pytest.mark.asyncio
async def test_run_platform_allows_persistence_grace_after_soft_budget(monkeypatch):
    transitions = []

    class FakeCrawler:
        async def run(self, args):
            await asyncio.sleep(0.08)
            return {
                "platform": "ptt",
                "status": "success",
                "cards_found": 1,
                "comments_found": 0,
                "elapsed": 0.08,
            }

    class FakeCrawlJobRepository:
        def create(self, **kwargs):
            return "crawl-job-1"

        def mark_started(self, job_id):
            transitions.append(("started", job_id))

        def mark_finished(self, job_id, **kwargs):
            transitions.append(("finished", job_id))

        def mark_failed(self, job_id, error_message):
            transitions.append(("failed", job_id, error_message))

    async def fake_risk_check(value):
        return SimpleNamespace(detected=False, reason=None)

    monkeypatch.setattr(runner.CrawlerRegistry, "create", lambda platform: FakeCrawler())
    monkeypatch.setattr(runner, "CrawlJobRepository", FakeCrawlJobRepository)
    monkeypatch.setattr(runner.RiskDetector, "check", fake_risk_check)

    args = Namespace(
        service_task_id="service-task-1",
        search_query="Example",
        keyword="Example",
        input_keyword="Example",
        url=None,
        respect_policy=False,
        stop_on_risk=False,
        risk_report=False,
        dry_run=True,
        skip_ai=True,
        max_minutes=0.001,
        persistence_grace_seconds=0.1,
    )

    result = await runner.run_platform("ptt", args)

    assert result["status"] == "success"
    assert ("finished", "crawl-job-1") in transitions
    assert not any(transition[0] == "failed" for transition in transitions)
