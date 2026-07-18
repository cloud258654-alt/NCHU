from __future__ import annotations

import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import Page, expect, sync_playwright


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from backend.app import app as dashboard_app  # noqa: E402


@dataclass
class FakeCoreState:
    businesses: list[dict[str, Any]] = field(default_factory=list)
    reviews_empty: bool = False
    summary_error: bool = False
    detail_404: bool = False
    requests: list[str] = field(default_factory=list)


class UvicornThread:
    def __init__(self, app: FastAPI, port: int) -> None:
        self.port = port
        self.server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "UvicornThread":
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError(f"server on port {self.port} did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            raise RuntimeError(f"server on port {self.port} did not stop")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _fake_core_app(state: FakeCoreState) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/dashboard/businesses")
    def businesses() -> list[dict[str, Any]]:
        state.requests.append("/api/dashboard/businesses")
        return state.businesses

    @app.get("/api/dashboard/summary")
    def summary(business_id: int | None = Query(default=None)) -> dict[str, Any]:
        suffix = f"?business_id={business_id}" if business_id else ""
        state.requests.append(f"/api/dashboard/summary{suffix}")
        if state.summary_error:
            raise HTTPException(status_code=503, detail="fake summary unavailable")
        return {
            "total_businesses": len(state.businesses),
            "total_items": 9,
            "total_reviews": 5,
            "total_comments": 4,
            "analyzed_items": 7,
            "positive": 4,
            "neutral": 2,
            "negative": 1,
            "unclassified": 2,
            "risk_level": "medium",
            "updated_at": "2026-07-18T00:00:00Z",
        }

    @app.get("/api/dashboard/reviews")
    def reviews(
        page: int = Query(default=1),
        page_size: int = Query(default=20),
        business_id: int | None = Query(default=None),
        platform: str | None = Query(default=None),
    ) -> dict[str, Any]:
        parts = [f"page={page}", f"page_size={page_size}"]
        if business_id:
            parts.append(f"business_id={business_id}")
        if platform:
            parts.append(f"platform={platform}")
        state.requests.append("/api/dashboard/reviews?" + "&".join(parts))
        if state.reviews_empty:
            return {"items": [], "page": page, "page_size": page_size, "total": 0}
        review_id = 101 if page == 1 else 102
        return {
            "items": [
                {
                    "id": review_id,
                    "business_id": business_id or 7,
                    "business_name": "Demo Shop",
                    "platform": platform or "google_maps",
                    "title": f"Useful review {review_id}",
                    "author_name": "Alice",
                    "content": "Fixed fake review content for browser acceptance.",
                    "link": f"https://example.test/reviews/{review_id}",
                    "published_at": "2026-07-17T00:00:00Z",
                    "updated_at": "2026-07-18T00:00:00Z",
                    "sentiment": "positive",
                    "risk_level": "high",
                    "summary": "Customer liked the service.",
                    "critical": True,
                    "critical_signals": ["medical escalation"],
                    "escalation_level": "critical",
                    "human_review_required": True,
                }
            ],
            "page": page,
            "page_size": page_size,
            "total": 41,
        }

    @app.get("/api/dashboard/reviews/{review_id}")
    def review_detail(review_id: int) -> dict[str, Any]:
        state.requests.append(f"/api/dashboard/reviews/{review_id}")
        if state.detail_404 or review_id == 404:
            raise HTTPException(status_code=404, detail="missing fake review")
        return {
            "id": review_id,
            "business_id": 7,
            "business_name": "Demo Shop",
            "platform": "google_maps",
            "title": f"Useful review {review_id}",
            "content": "Full fake review detail body.",
            "sentiment": "positive",
            "risk_level": "high",
            "recommendation": "Follow up with the customer.",
            "critical": True,
            "critical_signals": ["medical escalation"],
            "escalation_level": "critical",
            "human_review_required": True,
            "link": f"https://example.test/reviews/{review_id}",
        }

    return app


@pytest.fixture()
def dashboard_browser():
    core_port = _free_port()
    dashboard_port = _free_port()
    state = FakeCoreState(
        businesses=[
            {
                "id": 7,
                "name": "Demo Shop",
                "branch_name": "Main",
                "industry": "restaurant",
                "status": "active",
                "review_count": 2,
                "latest_review_at": "2026-07-18T00:00:00Z",
            }
        ]
    )
    old_core_api_url = os.environ.get("BI_RMP_CORE_API_URL")
    os.environ["BI_RMP_CORE_API_URL"] = f"http://127.0.0.1:{core_port}"
    try:
        with UvicornThread(_fake_core_app(state), core_port), UvicornThread(dashboard_app, dashboard_port):
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.add_init_script("window.__BI_RMP_DASHBOARD_TEST_MODE__ = true;")
                browser_requests: list[str] = []
                page.on("request", lambda request: browser_requests.append(request.url))
                yield page, state, browser_requests, f"http://127.0.0.1:{dashboard_port}"
                browser.close()
    finally:
        if old_core_api_url is None:
            os.environ.pop("BI_RMP_CORE_API_URL", None)
        else:
            os.environ["BI_RMP_CORE_API_URL"] = old_core_api_url


def _open(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/dashboard", wait_until="networkidle")


def _assert_no_direct_supabase(browser_requests: list[str]) -> None:
    forbidden = (
        "supabase" + ".co/rest/v1",
        "/api/" + "supabase-query",
        "SUPABASE" + "_SERVICE_ROLE_KEY",
        "DATABASE" + "_URL",
    )
    assert all(token not in url for url in browser_requests for token in forbidden)


def test_dashboard_loads_data_and_uses_core_api_only(dashboard_browser) -> None:
    page, state, browser_requests, base_url = dashboard_browser

    _open(page, base_url)

    expect(page.get_by_text("Reputation Dashboard")).to_be_visible()
    expect(page.locator("#connectionStatus")).to_have_text("Connected")
    expect(page.locator("#businessFilter")).to_contain_text("Demo Shop - Main")
    expect(page.locator("#metricTotalItems")).to_have_text("9")
    expect(page.locator("#metricRisk")).to_have_text("medium")
    expect(page.get_by_text("Useful review 101")).to_be_visible()
    expect(page.locator("#reviewsTable")).to_contain_text("Manual review")
    assert "/api/dashboard/businesses" in state.requests
    assert any(request.startswith("/api/dashboard/reviews?page=1") for request in state.requests)
    _assert_no_direct_supabase(browser_requests)


def test_dashboard_empty_businesses_and_reviews(dashboard_browser) -> None:
    page, state, browser_requests, base_url = dashboard_browser
    state.businesses = []
    state.reviews_empty = True

    _open(page, base_url)

    expect(page.locator("#businessFilter option")).to_have_count(1)
    expect(page.locator("#emptyState")).to_be_visible()
    expect(page.locator("#reviewsTable tr")).to_have_count(0)
    _assert_no_direct_supabase(browser_requests)


def test_dashboard_summary_error_and_core_unavailable_state(dashboard_browser) -> None:
    page, state, browser_requests, base_url = dashboard_browser
    state.summary_error = True

    _open(page, base_url)

    expect(page.locator("#connectionStatus")).to_have_text("Error")
    expect(page.locator("#errorState")).to_contain_text("Dashboard data is unavailable")
    _assert_no_direct_supabase(browser_requests)


def test_dashboard_pagination_and_filters(dashboard_browser) -> None:
    page, state, browser_requests, base_url = dashboard_browser

    _open(page, base_url)
    page.locator("#nextPage").click()
    expect(page.get_by_text("Useful review 102")).to_be_visible()
    page.locator("#businessFilter").select_option("7")
    page.locator("#platformFilter").select_option("ptt")
    expect(page.locator("#reviewsTable")).to_contain_text("ptt")

    assert any("page=2" in request for request in state.requests)
    assert any("business_id=7" in request for request in state.requests)
    assert any("platform=ptt" in request for request in state.requests)
    _assert_no_direct_supabase(browser_requests)


def test_dashboard_review_detail_200_and_404(dashboard_browser) -> None:
    page, state, browser_requests, base_url = dashboard_browser

    _open(page, base_url)
    page.get_by_text("Useful review 101").click()
    expect(page.locator("#reviewDialog")).to_contain_text("Full fake review detail body.")
    expect(page.locator("#reviewDialog")).to_contain_text("Follow up with the customer.")
    expect(page.locator("#reviewDialog")).to_contain_text("Critical incident")
    expect(page.locator("#reviewDialog")).to_contain_text("Critical signals")

    state.detail_404 = True
    page.evaluate("window.__BI_RMP_DASHBOARD_TEST__.openReview(404)")
    expect(page.locator("#errorState")).to_contain_text("selected review no longer exists")
    _assert_no_direct_supabase(browser_requests)
