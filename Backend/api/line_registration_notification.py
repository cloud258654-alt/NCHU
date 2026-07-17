from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from api.line_flex import build_registration_complete_flex_message


LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


class LineRegistrationNotificationService:
    def __init__(
        self,
        channel_access_token: str | None = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.channel_access_token = (
            channel_access_token
            if channel_access_token is not None
            else os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        )
        self.opener = opener

    def send_registration_completed(
        self,
        *,
        line_user_id: str,
        business_name: str,
        branch_name: str | None,
    ) -> bool:
        if not self.channel_access_token:
            return False

        payload = {
            "to": line_user_id,
            "messages": build_registration_complete_flex_message(
                business_name,
                branch_name,
            ),
        }
        request = Request(
            LINE_PUSH_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.channel_access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=10) as response:
                response.read()
        except (HTTPError, URLError, OSError):
            return False
        return True
