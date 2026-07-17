from pathlib import Path

from api.reputation_crawl import ReputationCrawlService, _parse_runner_summary
from api.main import app


def test_reputation_crawler_route_is_registered() -> None:
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/api/line/reputation-crawler/jobs", "POST") in routes
    assert ("/api/line/reputation-crawler/jobs/{task_id}/run", "POST") in routes
    assert ("/api/line/reputation-crawler/jobs/{task_id}/status", "POST") in routes
    assert ("/api/line/reputation-crawler/jobs/status/latest", "POST") in routes


def test_build_command_uses_store_and_line_user() -> None:
    service = ReputationCrawlService(
        runner_path=Path("/tmp/runner.py"),
        timeout_seconds=10,
        max_minutes=1.5,
        max_results=20,
        platform="all",
    )

    command = service.build_command(
        business_name="文章牛肉湯",
        line_user_id="U123",
        service_task_id="42",
        source_message_id="evt-1",
    )

    assert Path(command[1]) == Path("/tmp/runner.py")
    assert command[command.index("--business-name") + 1] == "文章牛肉湯"
    assert command[command.index("--line-user-id") + 1] == "U123"
    assert command[command.index("--max-results") + 1] == "20"
    assert command[command.index("--keyword") + 1] == "店家特色"
    assert command[command.index("--lookback-days") + 1] == "0"
    assert command[command.index("--google-maps-lookback-days") + 1] == "0"
    assert command[command.index("--ptt-max-minutes") + 1] == "1.5"
    assert command[command.index("--google-maps-max-minutes") + 1] == "3.0"
    assert command[command.index("--threads-max-minutes") + 1] == "3.0"
    assert command[command.index("--browser-concurrency") + 1] == "2"
    assert command[command.index("--persistence-grace-seconds") + 1] == "30.0"
    assert command[command.index("--service-task-id") + 1] == "42"
    assert command[command.index("--source-message-id") + 1] == "evt-1"
    assert "--json-summary" in command


def test_reputation_crawl_service_uses_reputation_crawl_env_names(monkeypatch) -> None:
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_MAX_MINUTES", "3")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_PTT_MAX_MINUTES", "2")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_GOOGLE_MAPS_MAX_MINUTES", "4")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_THREADS_MAX_MINUTES", "5")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_BROWSER_CONCURRENCY", "1")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_PERSISTENCE_GRACE_SECONDS", "45")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_MAX_RESULTS", "12")
    monkeypatch.setenv("BI_RMP_REPUTATION_CRAWL_PLATFORM", "ptt")

    service = ReputationCrawlService(runner_path=Path("/tmp/runner.py"))

    command = service.build_command(business_name="Example", line_user_id="U123")

    assert command[command.index("--max-minutes") + 1] == "3.0"
    assert command[command.index("--ptt-max-minutes") + 1] == "2.0"
    assert command[command.index("--google-maps-max-minutes") + 1] == "4.0"
    assert command[command.index("--threads-max-minutes") + 1] == "5.0"
    assert command[command.index("--browser-concurrency") + 1] == "1"
    assert command[command.index("--persistence-grace-seconds") + 1] == "45.0"
    assert command[command.index("--max-results") + 1] == "12"
    assert command[command.index("--platform") + 1] == "ptt"
    assert command[command.index("--lookback-days") + 1] == "0"


def test_parse_runner_summary_counts_crawled_items() -> None:
    payload = (
        b"noise\n"
        b'{"results":[{"cards_found":2,"comments_found":5,"canonical_posts_written":1},'
        b'{"cards_found":3,"comments_found":7,"canonical_comments_written":4}]}\n'
    )

    summary = _parse_runner_summary(payload)

    assert summary["articles_found"] == 5
    assert summary["comments_found"] == 12
    assert summary["canonical_posts_written"] == 1
    assert summary["canonical_comments_written"] == 4
