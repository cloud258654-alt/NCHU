import copy
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from api.line_flex import (
    build_registration_complete_flex_message,
    build_registration_flex_message,
    build_reputation_flex_message,
)


def test_flex_message_contains_friendly_quantitative_report_card() -> None:
    summary = _summary()

    messages = build_reputation_flex_message(summary)

    assert isinstance(messages, list)
    assert messages[0]["type"] == "flex"
    assert messages[0]["altText"] == "文章牛肉湯網路評價量化報告"
    assert len(messages[0]["altText"]) <= 400
    assert messages[0]["contents"]["type"] == "bubble"
    assert messages[0]["contents"]["size"] == "mega"

    serialized = str(messages[0]["contents"])
    assert "🌟 網路評價量化報告" in serialized
    assert "夥伴提醒" in serialized
    assert "風險分數" in serialized
    assert "負評率" in serialized
    assert "分析覆蓋率" in serialized
    assert "評價情緒分布" in serialized
    assert "評論總數" in serialized
    assert "資料更新時間" in serialized
    assert "下次點選「查詢進度」" in serialized
    assert "Google Maps" in serialized
    assert "42.5 / 100" in serialized
    assert "11.6%" in serialized
    assert "95.0%" in serialized
    assert "未分類：5 則" in serialized


def test_partner_reminder_uses_low_risk_positive_copy() -> None:
    summary = _summary(
        overview={
            "positive": 80,
            "neutral": 15,
            "negative": 5,
            "risk_level": "low",
        }
    )

    serialized = str(build_reputation_flex_message(summary))

    assert "整體評價偏正向" in serialized


def test_partner_reminder_uses_medium_or_mixed_copy() -> None:
    summary = _summary(
        overview={
            "positive": 30,
            "neutral": 47,
            "negative": 18,
            "risk_level": "medium",
        }
    )

    serialized = str(build_reputation_flex_message(summary))

    assert "中立或混合意見為主" in serialized


def test_partner_reminder_uses_high_risk_copy() -> None:
    summary = _summary(
        overview={
            "positive": 30,
            "neutral": 40,
            "negative": 30,
            "risk_level": "high",
        }
    )

    serialized = str(build_reputation_flex_message(summary))

    assert "負面訊號比較明顯" in serialized


def test_partner_reminder_uses_low_coverage_copy() -> None:
    summary = _summary(
        overview={
            "total_reviews": 100,
            "analyzed_reviews": 20,
            "positive": 10,
            "neutral": 8,
            "negative": 2,
        }
    )

    serialized = str(build_reputation_flex_message(summary))

    assert "資料量還不多" in serialized
    assert "初步參考" in serialized


def test_flex_message_preserves_source_numbers() -> None:
    summary = _summary()
    original_overview = copy.deepcopy(summary["overview"])
    original_platforms = copy.deepcopy(summary["platforms"])

    messages = build_reputation_flex_message(summary)
    serialized = str(messages[0]["contents"])

    assert summary["overview"]["total_reviews"] == original_overview["total_reviews"]
    assert summary["overview"]["analyzed_reviews"] == original_overview["analyzed_reviews"]
    assert summary["overview"]["positive_pct"] == 62.1
    assert summary["overview"]["neutral_pct"] == 26.3
    assert summary["overview"]["negative_pct"] == 11.6
    assert "PTT" in serialized
    assert "Threads" in serialized
    assert "Google Maps" in serialized
    for platform in original_platforms:
        assert str(platform["positive"]) in serialized
        assert str(platform["neutral"]) in serialized
        assert str(platform["negative"]) in serialized
        assert str(platform["total"]) in serialized


def test_flex_json_uses_supported_types_colors_and_progress_widths() -> None:
    messages = build_reputation_flex_message(_summary())
    contents = messages[0]["contents"]
    nodes = list(_walk(contents))
    supported_types = {"bubble", "box", "button", "separator", "text"}

    assert {node["type"] for node in nodes if "type" in node} <= supported_types
    assert "http://" not in str(contents)
    assert "https://" not in str(contents)
    assert "html" not in str(contents).lower()
    assert "css" not in str(contents).lower()
    assert "svg" not in str(contents).lower()

    for node in nodes:
        for key in ("color", "backgroundColor"):
            if key in node:
                assert re.fullmatch(r"#[0-9A-Fa-f]{6}", node[key])
        width = node.get("width")
        if isinstance(width, str) and width.endswith("%"):
            width_value = float(width.removesuffix("%"))
            assert 2 <= width_value <= 100


def test_registration_flex_message_uses_configured_public_url(monkeypatch) -> None:
    monkeypatch.delenv("LINE_LIFF_ID", raising=False)
    monkeypatch.setenv(
        "BI_RMP_REGISTRATION_URL",
        "https://register.example.com/store?source=line#form",
    )

    messages = build_registration_flex_message("U+123/測試")

    assert messages[0]["type"] == "flex"
    assert messages[0]["altText"] == "店家註冊邀請"
    action_url = messages[0]["contents"]["footer"]["contents"][0]["action"]["uri"]
    parsed = urlsplit(action_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "register.example.com"
    assert parsed.path == "/store"
    assert parsed.fragment == "form"
    assert parse_qs(parsed.query) == {
        "source": ["line"],
        "line_user_id": ["U+123/測試"],
    }


def test_registration_flex_message_omits_button_without_public_url(monkeypatch) -> None:
    monkeypatch.delenv("BI_RMP_REGISTRATION_URL", raising=False)
    monkeypatch.delenv("LINE_LIFF_ID", raising=False)

    messages = build_registration_flex_message("U123")

    bubble = messages[0]["contents"]
    assert "footer" not in bubble
    assert "註冊入口尚未開放" in str(bubble["body"])


def test_registration_flex_message_prefers_liff_without_exposing_line_user_id(monkeypatch) -> None:
    monkeypatch.setenv("BI_RMP_REGISTRATION_URL", "https://register.example.com/store")
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-AbcdEfgh")

    messages = build_registration_flex_message("U-private-user-id")

    action_url = messages[0]["contents"]["footer"]["contents"][0]["action"]["uri"]
    assert action_url == "https://liff.line.me/1234567890-AbcdEfgh"
    assert "U-private-user-id" not in action_url


def test_registration_complete_message_includes_business_and_getting_started_action() -> None:
    messages = build_registration_complete_flex_message("快樂小店", "總店")

    assert messages[0]["type"] == "flex"
    assert messages[0]["altText"] == "店家註冊完成：快樂小店｜總店"
    bubble = messages[0]["contents"]
    assert "接下來這樣使用" in str(bubble["body"])
    assert bubble["footer"]["contents"][0]["action"] == {
        "type": "message",
        "label": "開始分析",
        "text": "快樂小店",
    }


def _summary(overview: dict[str, Any] | None = None) -> dict[str, Any]:
    base_overview = {
        "total_reviews": 100,
        "analyzed_reviews": 95,
        "positive": 59,
        "neutral": 25,
        "negative": 11,
        "unclassified": 5,
        "risk_score": 42.5,
        "risk_points": 18,
        "risk_level": "medium",
        "summary": "目前整體評價偏正面。",
        "updated_at": "2026-07-11T10:30:00+08:00",
    }
    if overview:
        base_overview.update(overview)
    return {
        "business": {"name": "文章牛肉湯", "display_name": "文章牛肉湯｜安平總店"},
        "overview": base_overview,
        "overall": {"score_status": "provisional"},
        "platforms": [
            {
                "platform": "ptt",
                "label": "PTT",
                "positive": 5,
                "neutral": 8,
                "negative": 3,
                "unclassified": 0,
                "analyzed": 16,
                "total": 16,
            },
            {
                "platform": "threads",
                "label": "Threads",
                "positive": 3,
                "neutral": 10,
                "negative": 5,
                "unclassified": 0,
                "analyzed": 18,
                "total": 18,
            },
            {
                "platform": "google_maps",
                "label": "Google Maps",
                "positive": 51,
                "neutral": 7,
                "negative": 3,
                "unclassified": 5,
                "analyzed": 61,
                "total": 66,
            },
        ],
    }


def _walk(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        nodes.append(value)
        for item in value.values():
            nodes.extend(_walk(item))
    elif isinstance(value, list):
        for item in value:
            nodes.extend(_walk(item))
    return nodes
