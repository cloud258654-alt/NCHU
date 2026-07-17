import asyncio
import time

import pytest

from core.anti_block import CircuitBreaker, CircuitOpenError, CrawlPolicy, DelayStrategy, RateLimiter, RiskDetector


def test_crawl_policy_loads_platform_defaults():
    policy = CrawlPolicy.load()
    threads = policy.for_platform("threads")

    assert threads.min_delay == 1
    assert threads.max_delay == 4
    assert threads.max_scroll == 10
    assert threads.stop_on_login is True


def test_delay_strategy_within_policy_range():
    policy = CrawlPolicy.load().for_platform("ptt")

    delay = DelayStrategy.next_delay(policy)

    assert 0.5 <= delay <= 2


def test_risk_detector_detects_captcha():
    signal = asyncio.run(RiskDetector.check("captcha verification required"))

    assert signal.detected is True
    assert signal.reason == "captcha"


def test_circuit_breaker_opens_and_raises():
    breaker = CircuitBreaker()
    breaker.open("threads", "captcha")

    assert breaker.is_open("threads") is True
    try:
        breaker.raise_if_open("threads")
    except CircuitOpenError as exc:
        assert "captcha" in str(exc)
    else:
        raise AssertionError("CircuitOpenError was not raised")


@pytest.mark.asyncio
async def test_rate_limiter_serializes_concurrent_request_start_times(monkeypatch):
    limiter = RateLimiter()
    monkeypatch.setattr(DelayStrategy, "next_delay", lambda policy: 0.02)
    waits = []
    original_sleep = asyncio.sleep

    async def record_sleep(seconds):
        waits.append(seconds)
        await original_sleep(0)

    monkeypatch.setattr("core.anti_block.rate_limiter.asyncio.sleep", record_sleep)

    async def acquire_once():
        await limiter.acquire("ptt")
        return time.monotonic()

    await asyncio.gather(acquire_once(), acquire_once())

    assert len(waits) == 1
    assert waits[0] >= 0.015

