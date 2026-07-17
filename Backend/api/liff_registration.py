from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field


LINE_ID_TOKEN_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


class LiffConfigurationError(RuntimeError):
    pass


class LiffAuthenticationError(RuntimeError):
    pass


class LiffProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiffIdentity:
    line_user_id: str
    display_name: str | None = None


class LiffBusinessRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_token: str = Field(min_length=1, max_length=10000)
    client_name: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    branch_name: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=1000)


class LiffTokenVerifier:
    def __init__(
        self,
        *,
        channel_id: str | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._channel_id = channel_id
        self._opener = opener or urlopen

    def verify(self, id_token: str) -> LiffIdentity:
        channel_id = (
            self._channel_id or os.getenv("LINE_LOGIN_CHANNEL_ID", "")
        ).strip()
        if not channel_id:
            raise LiffConfigurationError("LINE_LOGIN_CHANNEL_ID is not configured")

        body = urlencode(
            {
                "id_token": id_token.strip(),
                "client_id": channel_id,
            }
        ).encode("utf-8")
        request = Request(
            LINE_ID_TOKEN_VERIFY_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with self._opener(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if 400 <= exc.code < 500:
                raise LiffAuthenticationError(
                    "LINE 登入憑證無效或已過期，請重新開啟註冊頁。"
                ) from exc
            raise LiffProviderError("LINE 身分驗證服務暫時無法使用。") from exc
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LiffProviderError("LINE 身分驗證服務暫時無法使用。") from exc

        if not isinstance(payload, dict):
            raise LiffProviderError("LINE 身分驗證回應格式無效。")

        line_user_id = str(payload.get("sub") or "").strip()
        audience = str(payload.get("aud") or "").strip()
        if not line_user_id or audience != channel_id:
            raise LiffAuthenticationError(
                "LINE 登入憑證無效或已過期，請重新開啟註冊頁。"
            )

        display_name = str(payload.get("name") or "").strip() or None
        return LiffIdentity(
            line_user_id=line_user_id,
            display_name=display_name,
        )
