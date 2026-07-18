from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ml.rules_baseline import ReviewAnalysisInput, analyze_batch, analyze_review, model_info, suggest_response

APP_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = APP_ROOT / "frontend"
DEFAULT_CORE_API_URL = "http://127.0.0.1:8000"
MAX_BATCH_SIZE = 50

app = FastAPI(
    title="BI-RMP Dashboard ML",
    version="0.1.0",
    description="Read-only Dashboard frontend host for the BI-RMP Core API.",
)


class AnalyzeReviewRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    review_id: str | None = Field(default=None, max_length=128)
    business_id: str | None = Field(default=None, max_length=128)
    platform: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=512)
    language: str | None = Field(default=None, max_length=32)


class AnalyzeBatchRequest(BaseModel):
    items: list[AnalyzeReviewRequest] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class SuggestResponseRequest(BaseModel):
    review_text: str = Field(min_length=1, max_length=8000)
    business_name: str | None = Field(default=None, max_length=256)
    sentiment: str | None = Field(default=None, max_length=32)
    risk_level: str | None = Field(default=None, max_length=32)
    tone: str | None = Field(default=None, max_length=32)


def _core_api_base_url() -> str:
    configured = os.getenv("BI_RMP_CORE_API_URL", DEFAULT_CORE_API_URL).strip()
    parsed = urlparse(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=500, detail="Core API URL is not configured")
    return configured.rstrip("/")


def _analysis_input(payload: AnalyzeReviewRequest) -> ReviewAnalysisInput:
    return ReviewAnalysisInput(
        content=payload.content,
        review_id=payload.review_id,
        business_id=payload.business_id,
        platform=payload.platform,
        title=payload.title,
        language=payload.language,
    )


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "dashboard-ml",
        "core_api_configured": bool(_core_api_base_url()),
    }


@app.get("/api/ml/health")
def ml_health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "dashboard-ml-offline-analysis",
        "model_kind": "deterministic_rules_baseline",
        "trained_model_available": False,
    }


@app.get("/api/ml/info")
def ml_info() -> dict[str, Any]:
    return model_info()


@app.post("/api/ml/analyze-review")
def analyze_review_endpoint(payload: AnalyzeReviewRequest) -> dict[str, Any]:
    return analyze_review(_analysis_input(payload))


@app.post("/api/ml/analyze-batch")
def analyze_batch_endpoint(payload: AnalyzeBatchRequest) -> dict[str, Any]:
    return analyze_batch([_analysis_input(item) for item in payload.items])


@app.post("/api/ai/suggest-response")
def suggest_response_endpoint(payload: SuggestResponseRequest) -> dict[str, Any]:
    return suggest_response(
        review_text=payload.review_text,
        business_name=payload.business_name,
        sentiment=payload.sentiment,
        risk_level=payload.risk_level,
        tone=payload.tone,
    )


@app.get("/api/config")
def config() -> dict[str, str]:
    return {
        "coreApiBaseUrl": _core_api_base_url(),
        "dashboardApiPrefix": "/api/dashboard",
    }


@app.get("/config.js")
def config_js() -> Response:
    body = "window.__BI_RMP_DASHBOARD_CONFIG__ = " + json.dumps(config(), separators=(",", ":")) + ";\n"
    return Response(content=body, media_type="application/javascript")


@app.get("/")
@app.get("/dashboard")
def index() -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_ROOT),
    name="dashboard-static",
)

app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_ROOT),
    name="dashboard-assets",
)
