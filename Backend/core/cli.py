import argparse


def add_common_crawler_args(parser: argparse.ArgumentParser) -> None:
    """Add adapter-level debug arguments.

    Public service runs should use ``build_runner_parser``. Platform modules still
    use this helper for direct maintenance runs until each adapter has a focused
    CLI of its own.
    """

    parser.add_argument(
        "--client-name",
        default="default-line-id",
        help="Client name for crawl context.",
    )
    parser.add_argument(
        "--client-id",
        default=None,
        help="Existing clients.id. When omitted, the backend can resolve/create one from --client-name.",
    )
    parser.add_argument(
        "--business-name",
        default=None,
        help="Business name for crawl context.",
    )
    parser.add_argument(
        "--business-id",
        default=None,
        help="Existing business.id. When omitted, the backend can resolve/create one from --business-name.",
    )
    parser.add_argument(
        "--keyword",
        "--purpose",
        dest="keyword",
        default="",
        help="Optional extra keyword, product, or service intent. The business name is used as the base query.",
    )
    parser.add_argument(
        "--service-type",
        default="reputation_monitoring",
        help="Service task type.",
    )
    parser.add_argument(
        "--schedule-type",
        default="once",
        choices=["once", "hourly", "daily", "weekly", "scheduled", "recurring"],
        help="Service task schedule type.",
    )
    parser.add_argument(
        "--channel",
        default="cli",
        help="Request channel, e.g. cli, line_bot, scheduler.",
    )
    parser.add_argument(
        "--line-user-id",
        default=None,
        help="LINE user id when the task originates from Line Bot.",
    )
    parser.add_argument(
        "--source-message-id",
        default=None,
        help="Upstream message/event id for idempotency.",
    )
    parser.add_argument(
        "--service-task-id",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--crawl-job-id",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--max-scroll", type=int, default=10, help="Maximum scroll count.")
    parser.add_argument("--max-minutes", type=float, default=10.0, help="Maximum crawl minutes.")
    parser.add_argument("--lookback-days", type=int, default=None, help="Optional rolling crawl window in days.")
    parser.add_argument(
        "--board",
        default=None,
        help="Optional legacy/debug board filter for board-based platforms such as PTT.",
    )
    parser.add_argument(
        "--date-range",
        default="all",
        choices=["week", "month", "year", "all"],
        help="Date range filter: week/month/year/all.",
    )
    parser.add_argument("--since-days", type=int, default=None, help="Collect content since N days ago.")
    parser.add_argument("--start-date", default=None, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="End date, YYYY-MM-DD.")
    parser.add_argument("--headless", default="True", help="Run browser in headless mode.")
    parser.add_argument("--keep-unknown-time", action="store_true", help="Keep posts with unknown time.")
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "duckduckgo", "bing", "searxng", "all"],
        help="Search engine for adapter-level discovery runs.",
    )
    parser.add_argument("--site", default=None, help="Limit search results to a site/domain.")
    parser.add_argument("--max-results", type=int, default=50, help="Maximum search results to collect.")
    parser.add_argument("--platform-max-results", type=int, default=None, help="Platform-specific result limit; 0 means no user cap.")
    parser.add_argument("--platform-max-scroll", type=int, default=None, help="Platform-specific scroll/page limit; 0 means no user cap.")
    parser.add_argument("--ptt-max-posts", type=int, default=None, help="PTT post limit; 0 means no user cap.")
    parser.add_argument("--ptt-max-pages", type=int, default=None, help="PTT board index page limit; 0 means no user cap.")
    parser.add_argument("--threads-max-posts", type=int, default=None, help="Threads post limit; 0 means no user cap.")
    parser.add_argument("--threads-max-scroll", type=int, default=None, help="Threads scroll limit; 0 means stable-round/deadline stop.")
    parser.add_argument("--searxng-url", default=None, help="SearXNG base URL, e.g. http://localhost:8080.")
    parser.add_argument("--parse-target", action="store_true", help="Call routed platform parser for each URL.")
    parser.add_argument("--store-search-results", action="store_true", help="Write search results to Supabase.")
    parser.add_argument("--export-jsonl", default=None, help="Export search results to a JSONL file.")
    parser.add_argument("--include-search", action="store_true", help="Include search aggregator in legacy adapter batches.")
    parser.add_argument("--respect-policy", action="store_true", help="Apply compliant crawl policy delays and limits.")
    parser.add_argument("--stop-on-risk", action="store_true", help="Stop a platform task when risk signals are detected.")
    parser.add_argument("--risk-report", action="store_true", help="Include anti-block health data in runner results.")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to Supabase.")
    parser.add_argument("--skip-ai", action="store_true", help="Skip the post-crawl AI pipeline.")
    parser.add_argument(
        "--fetch-comments",
        action="store_true",
        help="Fetch comments/replies from individual post detail pages when supported.",
    )


def build_runner_parser() -> argparse.ArgumentParser:
    """Build the service-oriented runner CLI parser."""

    parser = argparse.ArgumentParser(
        description="BI-RMP business reputation crawler service",
        epilog=(
            "The service always crawls currently supported MVP platforms. "
            "The business name is required and is used as the base query."
        ),
    )
    parser.add_argument("--business-name", required=True, help="Business/store name to monitor.")
    parser.add_argument(
        "--keyword",
        "--purpose",
        dest="keyword",
        default="",
        help="Optional extra monitoring intent, product, or issue.",
    )
    parser.add_argument("--client-name", default="default-line-id", help="Client display name for demo/dev runs.")
    parser.add_argument("--client-id", default=None, help="Existing clients.id when known.")
    parser.add_argument("--business-id", default=None, help="Existing business.id when known.")
    parser.add_argument("--line-user-id", default=None, help="LINE user id when available.")
    parser.add_argument("--service-task-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--source-message-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--service-type",
        default="reputation_monitoring",
        choices=["reputation_monitoring", "reservation_management", "business_insight"],
        help="Service task type.",
    )
    parser.add_argument(
        "--schedule-type",
        default="once",
        choices=["once", "hourly", "daily", "weekly"],
        help="Service task schedule type.",
    )
    parser.add_argument("--max-scroll", type=int, default=10, help="Developer crawl limit.")
    parser.add_argument("--max-minutes", type=float, default=10.0, help="Developer crawl time limit.")
    parser.add_argument("--ptt-max-minutes", type=float, default=None, help="PTT-specific time budget in minutes.")
    parser.add_argument(
        "--google-maps-max-minutes",
        type=float,
        default=None,
        help="Google Maps-specific time budget in minutes, including source discovery.",
    )
    parser.add_argument(
        "--threads-max-minutes",
        type=float,
        default=None,
        help="Threads-specific time budget in minutes.",
    )
    parser.add_argument(
        "--browser-concurrency",
        type=int,
        default=2,
        help="Maximum concurrent Chromium-backed platform crawlers.",
    )
    parser.add_argument(
        "--persistence-grace-seconds",
        type=float,
        default=30.0,
        help="Extra hard-timeout grace for cleanup and persistence after a platform crawl budget.",
    )
    parser.add_argument("--max-results", type=int, default=50, help="Developer result limit.")
    parser.add_argument("--lookback-days", type=int, default=None, help="Optional rolling crawl window in days.")
    parser.add_argument("--platform-max-results", type=int, default=None, help="Platform result limit; 0 means no user cap.")
    parser.add_argument("--platform-max-scroll", type=int, default=None, help="Platform scroll/page limit; 0 means no user cap.")
    parser.add_argument("--ptt-max-posts", type=int, default=None, help="PTT post limit; 0 means no user cap.")
    parser.add_argument("--ptt-max-pages", type=int, default=None, help="PTT board index page limit; 0 means no user cap.")
    parser.add_argument("--threads-max-posts", type=int, default=None, help="Threads post limit; 0 means no user cap.")
    parser.add_argument("--threads-max-scroll", type=int, default=None, help="Threads scroll limit; 0 means stable-round/deadline stop.")
    parser.add_argument("--skip-ai", action="store_true", help="Skip post-crawl AI analysis enqueue.")
    parser.add_argument("--google-maps-lookback-days", type=int, default=None, help="Optional Google Maps rolling review window in days.")
    parser.add_argument(
        "--google-maps-diff-mode",
        choices=["fast", "strict"],
        default="fast",
        help="Google Maps review delta comparison mode.",
    )
    parser.add_argument("--google-maps-max-reviews", type=int, default=None, help="Maximum Google Maps reviews to scan.")
    parser.add_argument("--google-maps-max-scroll", type=int, default=None, help="Google Maps-specific scroll limit.")
    parser.add_argument(
        "--platform",
        default="all",
        choices=["ptt", "google_maps", "threads", "all"],
        help="Developer platform selection. The public service default remains all MVP platforms.",
    )
    parser.add_argument("--json-summary", action="store_true", help="Print a machine-readable run summary to stdout.")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing crawled rows to Supabase.")
    return parser
