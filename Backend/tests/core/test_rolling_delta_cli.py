import pytest

import runner
from core.cli import build_runner_parser


def test_runner_parser_accepts_ptt_threads_delta_limits():
    parser = build_runner_parser()

    args = parser.parse_args(
        [
            "--business-name",
            "Example",
            "--lookback-days",
            "30",
            "--platform-max-results",
            "0",
            "--platform-max-scroll",
            "0",
            "--ptt-max-posts",
            "0",
            "--ptt-max-pages",
            "0",
            "--threads-max-posts",
            "0",
            "--threads-max-scroll",
            "0",
        ]
    )

    assert args.lookback_days == 30
    assert args.platform_max_results == 0
    assert args.ptt_max_posts == 0
    assert args.threads_max_scroll == 0


def test_runner_omitted_lookback_does_not_apply_date_filter():
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example"])

    assert args.lookback_days is None
    runner._apply_internal_defaults(args)

    assert args.since_days is None


def test_runner_validation_accepts_unlimited_lookback_days():
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example", "--lookback-days", "0"])

    runner._validate_runner_args(args, parser)


def test_runner_unlimited_lookback_does_not_become_since_zero():
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example", "--lookback-days", "0"])

    runner._apply_internal_defaults(args)

    assert args.since_days is None


def test_runner_positive_lookback_becomes_since_days():
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example", "--lookback-days", "30"])

    runner._apply_internal_defaults(args)

    assert args.since_days == 30


def test_runner_validation_rejects_negative_lookback_days():
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example", "--lookback-days", "-1"])

    with pytest.raises(SystemExit):
        runner._validate_runner_args(args, parser)


def test_runner_validation_rejects_non_positive_max_minutes():
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example", "--max-minutes", "0"])

    with pytest.raises(SystemExit):
        runner._validate_runner_args(args, parser)


def test_runner_async_resource_defaults():
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example"])

    assert args.browser_concurrency == 2
    assert args.persistence_grace_seconds == 30.0
    runner._validate_runner_args(args, parser)


@pytest.mark.parametrize(
    "option,value",
    [
        ("--browser-concurrency", "0"),
        ("--persistence-grace-seconds", "-1"),
    ],
)
def test_runner_validation_rejects_invalid_async_resource_limits(option, value):
    parser = build_runner_parser()
    args = parser.parse_args(["--business-name", "Example", option, value])

    with pytest.raises(SystemExit):
        runner._validate_runner_args(args, parser)
