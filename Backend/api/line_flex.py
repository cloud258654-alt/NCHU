from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.quantitative_report import attach_quantitative_metrics


RISK_LEVEL_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}

COLORS = {
    "text_primary": "#243024",
    "text_secondary": "#647064",
    "border": "#DDE8DD",
    "surface": "#FFFFFF",
    "green": "#35A853",
    "green_soft": "#EAF8EE",
    "yellow": "#F6B800",
    "yellow_soft": "#FFF7D9",
    "orange": "#F28C28",
    "orange_soft": "#FFF1DE",
    "pink": "#E85D75",
    "pink_soft": "#FDEBF0",
    "red": "#D94C43",
    "red_soft": "#FDECEA",
    "blue": "#3978D4",
    "blue_soft": "#EAF2FF",
    "mint": "#EAF8F2",
    "gray_soft": "#F5F7F5",
}


def build_reputation_flex_message(summary: dict[str, Any]) -> list[dict[str, Any]]:
    attach_quantitative_metrics(summary)

    business = summary["business"]
    overview = summary["overview"]
    platforms = summary.get("platforms", [])
    overall = summary.get("overall") or {}

    business_name = _truncate_text(
        business.get("display_name") or business.get("name") or "店家",
        80,
    )
    risk_score = overview.get("risk_score")
    risk_points = overview.get("risk_points")
    risk_level = overview.get("risk_level")
    negative_pct = overview.get("negative_pct", 0.0)
    coverage_pct = overview.get("analysis_coverage_pct", 0.0)
    positive_pct = overview.get("positive_pct", 0.0)
    neutral_pct = overview.get("neutral_pct", 0.0)
    unclassified_pct = overview.get("unclassified_pct", 0.0)
    partner_reminder = _truncate_text(
        _partner_reminder_text(overview=overview, overall=overall),
        220,
    )
    score_status_text = _score_status_text(overall.get("score_status"))

    risk_score_text = f"{float(risk_score):.1f} / 100" if risk_score is not None else "尚未計算"
    risk_points_text = f"{risk_points} 點" if risk_points is not None else "尚未計算"
    risk_level_text = RISK_LEVEL_LABELS.get(risk_level, "尚未判定")

    table_contents: list[dict[str, Any]] = [
        _table_row("平台", "正", "中", "負", "總", header=True)
    ]
    for item in platforms[:8]:
        table_contents.append(
            _table_row(
                _truncate_text(item.get("label") or item.get("platform") or "Unknown", 32),
                str(item.get("positive", 0)),
                str(item.get("neutral", 0)),
                str(item.get("negative", 0)),
                str(item.get("total", 0)),
            )
        )

    if platforms:
        table_contents.append({"type": "separator", "margin": "sm", "color": COLORS["border"]})
    table_contents.append(
        _table_row(
            "全部",
            str(overview.get("positive", 0)),
            str(overview.get("neutral", 0)),
            str(overview.get("negative", 0)),
            str(overview.get("total_reviews", 0)),
            header=True,
        )
    )

    bubble = {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "backgroundColor": COLORS["surface"],
            "contents": [
                {
                    "type": "text",
                    "text": "🌟 網路評價量化報告",
                    "weight": "bold",
                    "size": "xl",
                    "color": COLORS["text_primary"],
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": COLORS["mint"],
                    "cornerRadius": "14px",
                    "paddingAll": "10px",
                    "contents": [
                        {
                            "type": "text",
                            "text": business_name,
                            "weight": "bold",
                            "size": "sm",
                            "color": COLORS["text_primary"],
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": _truncate_text(overview.get("summary") or "目前沒有可顯示的摘要。", 220),
                            "size": "xs",
                            "color": COLORS["text_secondary"],
                            "wrap": True,
                            "margin": "xs",
                        },
                    ],
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": COLORS["yellow_soft"],
                    "cornerRadius": "16px",
                    "paddingAll": "14px",
                    "contents": [
                        {
                            "type": "text",
                            "text": partner_reminder,
                            "wrap": True,
                            "size": "sm",
                            "color": COLORS["text_primary"],
                        }
                    ],
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": COLORS["blue_soft"],
                    "cornerRadius": "12px",
                    "paddingAll": "10px",
                    "contents": [
                        {
                            "type": "text",
                            "text": score_status_text,
                            "size": "xs",
                            "color": COLORS["text_primary"],
                            "wrap": True,
                        }
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        _metric_box(
                            "風險分數",
                            risk_score_text,
                            icon="🛡️",
                            accent_color=COLORS["orange"],
                            background_color=COLORS["orange_soft"],
                            progress=risk_score,
                        ),
                        _metric_box(
                            "負評率",
                            _percent_text(negative_pct),
                            icon="💔",
                            accent_color=COLORS["pink"],
                            background_color=COLORS["pink_soft"],
                            progress=negative_pct,
                        ),
                        _metric_box(
                            "分析覆蓋率",
                            _percent_text(coverage_pct),
                            icon="📊",
                            accent_color=COLORS["blue"],
                            background_color=COLORS["blue_soft"],
                            progress=coverage_pct,
                        ),
                    ],
                },
                {
                    "type": "text",
                    "text": (
                        f"{_risk_indicator(risk_level)} 風險等級：{risk_level_text}"
                        f"｜風險點數：{risk_points_text}"
                    ),
                    "size": "xs",
                    "color": COLORS["text_secondary"],
                    "align": "center",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": "❤️ 評價情緒分布",
                    "size": "sm",
                    "weight": "bold",
                    "color": COLORS["text_primary"],
                    "margin": "sm",
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        _sentiment_box(
                            "正面",
                            positive_pct,
                            icon="🙂",
                            accent_color=COLORS["green"],
                            background_color=COLORS["green_soft"],
                        ),
                        _sentiment_box(
                            "中立",
                            neutral_pct,
                            icon="😐",
                            accent_color=COLORS["yellow"],
                            background_color=COLORS["yellow_soft"],
                        ),
                        _sentiment_box(
                            "負面",
                            negative_pct,
                            icon="☹️",
                            accent_color=COLORS["red"],
                            background_color=COLORS["red_soft"],
                        ),
                    ],
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": COLORS["mint"],
                    "cornerRadius": "12px",
                    "paddingAll": "12px",
                    "contents": [
                        {
                            "type": "text",
                            "text": (
                                f"📋 評論總數：{overview.get('total_reviews', 0)} 則"
                                f"｜已分析：{overview.get('analyzed_reviews', 0)} 則"
                            ),
                            "size": "sm",
                            "weight": "bold",
                            "color": COLORS["text_primary"],
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": (
                                f"未分類：{overview.get('unclassified', 0)} 則"
                                f"（{unclassified_pct:.1f}%）"
                            ),
                            "size": "xs",
                            "color": COLORS["text_secondary"],
                            "margin": "xs",
                        },
                    ],
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": COLORS["gray_soft"],
                    "cornerRadius": "12px",
                    "paddingAll": "10px",
                    "spacing": "sm",
                    "contents": table_contents,
                },
                {
                    "type": "text",
                    "text": f"🕒 {_updated_at_text(overview.get('updated_at'))}",
                    "size": "xxs",
                    "color": COLORS["text_secondary"],
                    "margin": "md",
                    "align": "end",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": "🔎 下次點選「查詢進度」，我會再幫你整理最新狀況。",
                    "size": "xxs",
                    "color": COLORS["text_secondary"],
                    "align": "end",
                    "wrap": True,
                },
            ],
        },
    }

    alt_text = _truncate_text(f"{business.get('name', '店家')}網路評價量化報告", 400)
    return [{"type": "flex", "altText": alt_text, "contents": bubble}]


def build_error_text_message(message: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": _truncate_text(message, 5000)}]


def build_registration_flex_message(line_user_id: str) -> list[dict[str, Any]]:
    registration_url = os.getenv("BI_RMP_REGISTRATION_URL", "").strip()
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if liff_id:
        registration_url = f"https://liff.line.me/{liff_id}"
    registration_ready = bool(registration_url)

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "hero": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1A73E8",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "BI-RMP",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "xxl",
                    "align": "center",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "尚未註冊店家",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#111111",
                    "align": "center",
                },
                {
                    "type": "text",
                    "text": (
                        "您目前尚未綁定任何店家，請點擊下方按鈕進行店家註冊，即可開始使用輿情監測與分析服務。"
                        if registration_ready
                        else "您目前尚未綁定任何店家，註冊入口尚未開放，請稍後再試。"
                    ),
                    "size": "sm",
                    "color": "#555555",
                    "wrap": True,
                },
            ],
        },
    }
    if registration_ready:
        bubble["footer"] = {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#1A73E8",
                    "action": {
                        "type": "uri",
                        "label": "開始註冊店家",
                        "uri": _registration_action_url(
                            registration_url,
                            line_user_id,
                        ),
                    },
                }
            ],
        }
    return [{"type": "flex", "altText": "店家註冊邀請", "contents": bubble}]


def build_registration_complete_flex_message(
    business_name: str,
    branch_name: str | None = None,
) -> list[dict[str, Any]]:
    display_name = business_name
    if branch_name:
        display_name = f"{business_name}｜{branch_name}"

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "hero": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#137A4A",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "BI-RMP",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "xxl",
                    "align": "center",
                },
                {
                    "type": "text",
                    "text": "店家註冊完成",
                    "color": "#D9FBE7",
                    "size": "sm",
                    "align": "center",
                    "margin": "sm",
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "🎉 恭喜完成註冊",
                    "weight": "bold",
                    "size": "xl",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": f"「{display_name}」已成功連結至您的 LINE 帳號。",
                    "size": "sm",
                    "color": "#555555",
                    "wrap": True,
                },
                {"type": "separator", "margin": "sm"},
                {
                    "type": "text",
                    "text": "接下來這樣使用",
                    "weight": "bold",
                    "size": "md",
                },
                {
                    "type": "text",
                    "text": "1. 在此聊天室傳送店家名稱，開始建立輿情分析。\n2. 分析完成後會收到量化報告。\n3. 可隨時再傳送店家名稱查看最新結果。",
                    "size": "sm",
                    "color": "#555555",
                    "wrap": True,
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#137A4A",
                    "action": {
                        "type": "message",
                        "label": "開始分析",
                        "text": business_name,
                    },
                }
            ],
        },
    }
    return [
        {
            "type": "flex",
            "altText": f"店家註冊完成：{display_name}"[:400],
            "contents": bubble,
        }
    ]


def _append_query_parameter(url: str, name: str, value: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, existing_value)
        for key, existing_value in parse_qsl(parts.query, keep_blank_values=True)
        if key != name
    ]
    query.append((name, value))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def _registration_action_url(registration_url: str, line_user_id: str) -> str:
    host = urlsplit(registration_url).netloc.lower()
    if host in {"liff.line.me", "miniapp.line.me"}:
        return registration_url
    return _append_query_parameter(registration_url, "line_user_id", line_user_id)


def _partner_reminder_text(
    *,
    overview: dict[str, Any],
    overall: dict[str, Any],
) -> str:
    del overall
    total_reviews = _as_float(overview.get("total_reviews"))
    coverage_pct = _as_float(overview.get("analysis_coverage_pct"))
    negative_pct = _as_float(overview.get("negative_pct"))
    risk_level = overview.get("risk_level")
    dominant_sentiment = overview.get("dominant_sentiment")

    if total_reviews <= 0 or coverage_pct < 40:
        return "🔎 夥伴提醒：目前資料量還不多，先把這份結果當作初步參考。持續蒐集更多評論後，判斷會更穩定。"
    if risk_level == "high" or negative_pct >= 20:
        return "🚨 夥伴提醒：近期負面訊號比較明顯，先別急。建議優先檢查高風險評論與重複出現的問題，逐項處理會比較有效。"
    if risk_level == "medium" or dominant_sentiment in {"neutral", "mixed"}:
        return "🧡 夥伴提醒：目前評價以中立或混合意見為主，整體仍算穩定。建議先看看大家最常提到的問題，再挑一兩項優先改善。"
    if risk_level == "low" and dominant_sentiment == "positive":
        return "💚 夥伴提醒：目前整體評價偏正向，辛苦了！建議持續留意新增負評與風險變化，穩穩維持好口碑。"
    return "✨ 夥伴提醒：這份報告整理了目前的評論狀況。建議持續觀察新增評論與風險變化，讓口碑維持在穩定狀態。"


def _metric_box(
    label: str,
    value: str,
    *,
    icon: str,
    accent_color: str,
    background_color: str,
    progress: float | None = None,
) -> dict[str, Any]:
    return {
        "type": "box",
        "layout": "vertical",
        "flex": 1,
        "backgroundColor": background_color,
        "cornerRadius": "14px",
        "paddingAll": "10px",
        "spacing": "xs",
        "contents": [
            {
                "type": "text",
                "text": f"{icon} {label}",
                "size": "xxs",
                "color": accent_color,
                "align": "center",
                "weight": "bold",
                "wrap": False,
            },
            {
                "type": "text",
                "text": value,
                "size": "sm",
                "weight": "bold",
                "align": "center",
                "color": COLORS["text_primary"],
                "wrap": False,
            },
            _progress_bar(
                progress,
                accent_color=accent_color,
                background_color=COLORS["surface"],
            ),
        ],
    }


def _progress_bar(
    value: float | int | None,
    *,
    accent_color: str,
    background_color: str,
) -> dict[str, Any]:
    progress = min(max(_as_float(value), 0.0), 100.0)
    width = max(progress, 2.0)
    return {
        "type": "box",
        "layout": "vertical",
        "height": "6px",
        "backgroundColor": background_color,
        "cornerRadius": "999px",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "height": "6px",
                "width": f"{width:.1f}%",
                "backgroundColor": accent_color,
                "cornerRadius": "999px",
                "contents": [],
            }
        ],
    }


def _sentiment_box(
    label: str,
    value: float,
    *,
    icon: str,
    accent_color: str,
    background_color: str,
) -> dict[str, Any]:
    return {
        "type": "box",
        "layout": "vertical",
        "flex": 1,
        "backgroundColor": background_color,
        "cornerRadius": "12px",
        "paddingAll": "10px",
        "contents": [
            {
                "type": "text",
                "text": f"{icon} {label}",
                "size": "xxs",
                "weight": "bold",
                "color": accent_color,
                "align": "center",
                "wrap": False,
            },
            {
                "type": "text",
                "text": _percent_text(value),
                "size": "sm",
                "weight": "bold",
                "color": COLORS["text_primary"],
                "align": "center",
                "margin": "xs",
                "wrap": False,
            },
        ],
    }


def _table_row(
    platform: str,
    positive: str,
    neutral: str,
    negative: str,
    total: str,
    *,
    header: bool = False,
) -> dict[str, Any]:
    weight = "bold" if header else "regular"
    platform_color = COLORS["text_primary"] if header else COLORS["text_secondary"]
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "xs",
        "contents": [
            _cell(platform, flex=4, align="start", weight=weight, color=platform_color),
            _cell(positive, flex=1, align="end", weight=weight, color=COLORS["green"]),
            _cell(neutral, flex=1, align="end", weight=weight, color=COLORS["yellow"]),
            _cell(negative, flex=1, align="end", weight=weight, color=COLORS["red"]),
            _cell(total, flex=1, align="end", weight=weight, color=COLORS["blue"]),
        ],
    }


def _cell(text: str, *, flex: int, align: str, weight: str, color: str) -> dict[str, Any]:
    return {
        "type": "text",
        "text": _truncate_text(text, 32),
        "size": "xs",
        "flex": flex,
        "align": align,
        "weight": weight,
        "color": color,
        "wrap": False,
    }


def _percent_text(value: Any) -> str:
    return f"{_as_float(value):.1f}%"


def _score_status_text(status: Any) -> str:
    if status == "complete":
        return "✅ 完整分析已完成，平台指標與文字情緒都已納入。"
    if status == "provisional":
        return "🛡️ 目前是暫定分數，部分平台或文字情緒仍在整理中。"
    return "🔎 目前資料還不夠完整，這份結果先作為初步參考。"


def _risk_indicator(risk_level: Any) -> str:
    if risk_level == "low":
        return "🟢"
    if risk_level == "medium":
        return "🟡"
    if risk_level == "high":
        return "🔴"
    return "⚪"


def _truncate_text(value: Any, max_length: int) -> str:
    if value is None:
        text = ""
    elif isinstance(value, (str, int, float, bool)):
        text = str(value)
    else:
        text = ""
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max(max_length - 1, 0)]}…"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _updated_at_text(value: str | datetime | None) -> str:
    if value is None:
        return "資料更新時間：尚無資料"
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return f"資料更新時間：{_truncate_text(value, 80)}"
    return f"資料更新時間：{parsed.astimezone(_taipei_tz()).strftime('%Y/%m/%d %H:%M')}"


def _taipei_tz():
    try:
        return ZoneInfo("Asia/Taipei")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=8))
