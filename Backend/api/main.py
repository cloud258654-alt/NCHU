from __future__ import annotations

import asyncio
import hmac
import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from api.client_recognition import (
    ClientRecognitionRepository,
    ClientRecognitionRequest,
)
from api.reputation_crawl import ReputationCrawlJobService, ReputationCrawlResult
from api.enriched_reputation import EnrichedReputationSummaryService
from api.line_flex import build_reputation_flex_message, build_registration_flex_message
from api.line_registration_notification import LineRegistrationNotificationService
from api.liff_registration import (
    LiffAuthenticationError,
    LiffBusinessRegisterRequest,
    LiffConfigurationError,
    LiffProviderError,
    LiffTokenVerifier,
)
from api.message_router import extract_business_name
from api.models import (
    ReputationCrawlJobStatusRequest,
    ReputationCrawlRequest,
    ReputationSummaryRequest,
)
from api.quantitative_report import attach_quantitative_metrics
from api.reputation import DatabaseConfigurationError
from api.reviews_enriched import ReviewsEnrichedRepository
from api.business import (
    BusinessRepository,
    BusinessCheckDuplicateRequest,
    BusinessRegisterRequest,
)
from api.client_messages_log import MessageLogRequest, ClientMessagesLogRepository
from api.dashboard import (
    get_dashboard_review,
    get_dashboard_summary,
    list_dashboard_businesses,
    list_dashboard_reviews,
)

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIFF_REGISTRATION_PAGE = PROJECT_ROOT / "Frontend" / "register" / "index.html"

app = FastAPI(
    title="BI-RMP Integration API",
    version="0.3.1",
    description="Backend endpoints used by n8n and LINE Messaging API workflows.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8010", "http://localhost:8010"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)
app.add_api_route(
    "/api/dashboard/businesses",
    list_dashboard_businesses,
    methods=["GET"],
    tags=["dashboard"],
)
app.add_api_route(
    "/api/dashboard/summary",
    get_dashboard_summary,
    methods=["GET"],
    tags=["dashboard"],
)
app.add_api_route(
    "/api/dashboard/reviews",
    list_dashboard_reviews,
    methods=["GET"],
    tags=["dashboard"],
)
app.add_api_route(
    "/api/dashboard/reviews/{review_id}",
    get_dashboard_review,
    methods=["GET"],
    tags=["dashboard"],
)


@lru_cache(maxsize=1)
def get_client_recognition_repository() -> ClientRecognitionRepository:
    return ClientRecognitionRepository()


@lru_cache(maxsize=1)
def get_business_repository() -> BusinessRepository:
    return BusinessRepository()


@lru_cache(maxsize=1)
def get_liff_token_verifier() -> LiffTokenVerifier:
    return LiffTokenVerifier()


@lru_cache(maxsize=1)
def get_line_registration_notification_service() -> LineRegistrationNotificationService:
    return LineRegistrationNotificationService()



@lru_cache(maxsize=1)
def get_reputation_repository() -> ReviewsEnrichedRepository:
    return ReviewsEnrichedRepository()


@lru_cache(maxsize=1)
def get_reputation_service() -> EnrichedReputationSummaryService:
    return EnrichedReputationSummaryService(get_reputation_repository())


@lru_cache(maxsize=1)
def get_reputation_crawl_job_service() -> ReputationCrawlJobService:
    return ReputationCrawlJobService()


def verify_internal_api_key(
    x_bi_rmp_api_key: str | None = Header(default=None, alias="X-BI-RMP-API-Key"),
) -> None:
    expected = os.getenv("BI_RMP_INTERNAL_API_KEY", "").strip()
    if not expected:
        return
    if not x_bi_rmp_api_key or not hmac.compare_digest(x_bi_rmp_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/register", response_class=HTMLResponse)
def liff_registration_page() -> HTMLResponse:
    try:
        content = LIFF_REGISTRATION_PAGE.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIFF registration page is unavailable",
        ) from exc
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/liff/config")
def liff_config() -> dict[str, str]:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LINE_LIFF_ID is not configured",
        )
    return {"liff_id": liff_id}


@app.post("/api/liff/business/register")
async def liff_register_business(
    payload: LiffBusinessRegisterRequest,
    verifier: LiffTokenVerifier = Depends(get_liff_token_verifier),
    repo: BusinessRepository = Depends(get_business_repository),
    notifier: LineRegistrationNotificationService = Depends(
        get_line_registration_notification_service
    ),
) -> dict[str, object]:
    try:
        identity = await asyncio.to_thread(verifier.verify, payload.id_token)
    except LiffConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except LiffAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except LiffProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    try:
        registration = await asyncio.to_thread(
            repo.register,
            line_user_id=identity.line_user_id,
            name=payload.name,
            branch_name=payload.branch_name,
            industry=payload.industry,
            address=payload.address,
            client_name=payload.client_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DatabaseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    notification_sent = await asyncio.to_thread(
        notifier.send_registration_completed,
        line_user_id=identity.line_user_id,
        business_name=str(registration["name"]),
        branch_name=payload.branch_name,
    )
    return {**registration, "registration_notification_sent": notification_sent}


@app.post(
    "/api/line/client-recognition",
    dependencies=[Depends(verify_internal_api_key)],
)
async def line_client_recognition(
    payload: ClientRecognitionRequest,
) -> dict[str, object]:
    try:
        result = await asyncio.to_thread(
            get_client_recognition_repository().recognize,
            payload.line_user_id,
        )
    except DatabaseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    res_dict = result.to_dict()
    if not result.business_found:
        res_dict["registration_flex_message"] = build_registration_flex_message(
            payload.line_user_id
        )
    return res_dict


@app.post(
    "/api/line/business/check-duplicate",
    dependencies=[Depends(verify_internal_api_key)],
)
async def check_business_duplicate(
    payload: BusinessCheckDuplicateRequest,
    repo: BusinessRepository = Depends(get_business_repository),
) -> dict[str, object]:
    try:
        is_dup = await asyncio.to_thread(
            repo.check_duplicate,
            payload.name,
        )
        return {"is_duplicate": is_dup}
    except DatabaseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc




@app.post(
    "/api/line/reputation-crawler/jobs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_internal_api_key)],
)
async def create_line_reputation_crawler_job(
    payload: ReputationCrawlRequest,
) -> dict[str, object]:
    try:
        return await get_reputation_crawl_job_service().create_job(
            business_name=payload.business_name,
            line_user_id=payload.line_user_id,
            source_message_id=payload.webhook_event_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/line/reputation-crawler/jobs/{task_id}/run",
    dependencies=[Depends(verify_internal_api_key)],
)
async def run_line_reputation_crawler_job(task_id: int) -> dict[str, object]:
    try:
        return await get_reputation_crawl_job_service().run_job(str(task_id))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crawl task not found") from exc


@app.post(
    "/api/line/reputation-crawler/jobs/{task_id}/status",
    dependencies=[Depends(verify_internal_api_key)],
)
async def get_line_reputation_crawler_job_status(
    task_id: int,
    payload: ReputationCrawlJobStatusRequest,
) -> dict[str, object]:
    try:
        return await get_reputation_crawl_job_service().status(
            str(task_id),
            line_user_id=payload.line_user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crawl task not found") from exc


@app.post(
    "/api/line/reputation-crawler/jobs/status/latest",
    dependencies=[Depends(verify_internal_api_key)],
)
async def get_latest_line_reputation_crawler_job_status(
    payload: ReputationCrawlJobStatusRequest,
) -> dict[str, object]:
    try:
        return await get_reputation_crawl_job_service().latest_status(
            line_user_id=payload.line_user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crawl task not found") from exc


@app.post(
    "/api/line/reputation-summary",
    dependencies=[Depends(verify_internal_api_key)],
)
async def line_reputation_summary(payload: ReputationSummaryRequest) -> dict:
    requested_business_name = (
        payload.business_name or extract_business_name(payload.message_text)
    )
    report_scope = get_reputation_repository().resolve_business(
        line_user_id=payload.line_user_id,
        business_name=requested_business_name,
        business_id=payload.business_id,
    )

    reputation_crawl_result = ReputationCrawlResult(
        status="skipped",
        business_name=report_scope.name,
        duration_seconds=0.0,
        reason="global reviews_enriched report uses existing rows",
    )

    try:
        result = await asyncio.to_thread(
            get_reputation_service().build_summary,
            line_user_id=payload.line_user_id,
            business_name=requested_business_name,
            business_id=payload.business_id,
        )
    except DatabaseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    attach_quantitative_metrics(result)
    result["ok"] = True
    result["request"] = {
        "message_text": payload.message_text,
        "requested_business_name": requested_business_name,
        "business_name": report_scope.name,
        "business_id": report_scope.id,
        "webhook_event_id": payload.webhook_event_id,
        "requested_refresh": payload.refresh,
        "refresh": False,
        "report_scope": "all_rows",
    }
    result["data_contract"]["report_scope"] = "all_rows"
    result["refresh"] = reputation_crawl_result.to_dict()
    result["line_messages"] = build_reputation_flex_message(result)
    return result


@app.post(
    "/api/line/messages/log",
    dependencies=[Depends(verify_internal_api_key)],
)
async def log_line_message(payload: MessageLogRequest) -> dict[str, object]:
    repo = ClientMessagesLogRepository()
    try:
        return await asyncio.to_thread(
            repo.log_message,
            line_user_id=payload.line_user_id,
            message_text=payload.message_text,
            direction=payload.direction,
            intent=payload.intent,
            session_state=payload.session_state,
        )
    except DatabaseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
