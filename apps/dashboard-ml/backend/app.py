from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles


APP_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = APP_ROOT / "frontend"
DEFAULT_CORE_API_URL = "http://127.0.0.1:8000"

app = FastAPI(
    title="BI-RMP Dashboard ML",
    version="0.1.0",
    description="Read-only Dashboard frontend host for the BI-RMP Core API.",
)


def _core_api_base_url() -> str:
    configured = os.getenv("BI_RMP_CORE_API_URL", DEFAULT_CORE_API_URL).strip()
    parsed = urlparse(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=500, detail="Core API URL is not configured")
    return configured.rstrip("/")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "dashboard-ml",
        "core_api_configured": bool(_core_api_base_url()),
    }


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
