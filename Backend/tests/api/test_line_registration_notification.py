from __future__ import annotations

import json
from urllib.error import URLError

from api.line_registration_notification import (
    LINE_PUSH_URL,
    LineRegistrationNotificationService,
)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


def test_registration_notification_posts_completion_flex_message() -> None:
    captured: dict[str, object] = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    sent = LineRegistrationNotificationService(
        channel_access_token="test-token",
        opener=opener,
    ).send_registration_completed(
        line_user_id="U-verified",
        business_name="快樂小店",
        branch_name="總店",
    )

    assert sent is True
    assert captured["url"] == LINE_PUSH_URL
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["timeout"] == 10
    assert captured["payload"]["to"] == "U-verified"
    assert captured["payload"]["messages"][0]["altText"] == "店家註冊完成：快樂小店｜總店"


def test_registration_notification_skips_without_token() -> None:
    service = LineRegistrationNotificationService(channel_access_token="")

    assert service.send_registration_completed(
        line_user_id="U-verified",
        business_name="快樂小店",
        branch_name=None,
    ) is False


def test_registration_notification_does_not_fail_registration_when_line_is_unavailable() -> None:
    def failing_opener(request, timeout):
        raise URLError("temporary LINE outage")

    service = LineRegistrationNotificationService(
        channel_access_token="test-token",
        opener=failing_opener,
    )

    assert service.send_registration_completed(
        line_user_id="U-verified",
        business_name="快樂小店",
        branch_name=None,
    ) is False
