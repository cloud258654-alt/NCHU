from __future__ import annotations

from math import log1p
from typing import Any

from .scoring_config import load_reputation_scoring_config


def google_native_score(rating_value: Any) -> float | None:
    rating = _safe_float(rating_value)
    if rating is None or rating < 1 or rating > 5:
        return None
    return round((rating - 1) / 4 * 100, 2)


def ptt_post_native_score(push_count: Any, boo_count: Any, arrow_count: Any, *, prior_strength: float | None = None) -> float:
    config = load_reputation_scoring_config()
    prior = float(prior_strength if prior_strength is not None else config["ptt"]["prior_strength"])
    push = _safe_int(push_count)
    boo = _safe_int(boo_count)
    arrow = _safe_int(arrow_count)
    denominator = push + boo + arrow + prior
    if denominator <= 0:
        return 50.0
    reaction_balance = (push - boo) / denominator
    return round(50 + 50 * reaction_balance, 2)


def ptt_comment_native_score(comment_type: str | None) -> tuple[float | None, str | None, float | None]:
    config = load_reputation_scoring_config()
    normalized = (comment_type or "").strip().casefold()
    mapping = {
        "push": float(config["ptt_comment"]["push_score"]),
        "推": float(config["ptt_comment"]["push_score"]),
        "boo": float(config["ptt_comment"]["boo_score"]),
        "噓": float(config["ptt_comment"]["boo_score"]),
        "arrow": float(config["ptt_comment"]["arrow_score"]),
        "neutral": float(config["ptt_comment"]["arrow_score"]),
        "→": float(config["ptt_comment"]["arrow_score"]),
    }
    score = mapping.get(normalized)
    if score is None:
        return None, None, None
    return score, "native_type_only", 0.35


def threads_raw_engagement(
    *,
    like_count: Any = 0,
    reply_count: Any = 0,
    repost_count: Any = 0,
    quote_count: Any = 0,
    view_count: Any = 0,
) -> float:
    weights = load_reputation_scoring_config()["threads"]["engagement"]
    return round(
        float(weights["like"]) * _safe_int(like_count)
        + float(weights["reply"]) * _safe_int(reply_count)
        + float(weights["repost"]) * _safe_int(repost_count)
        + float(weights["quote"]) * _safe_int(quote_count)
        + float(weights["view"]) * _safe_int(view_count),
        4,
    )


def engagement_score_from_raw(raw_engagement: Any, *, percentile_basis: list[float] | None = None) -> float:
    raw = max(_safe_float(raw_engagement) or 0.0, 0.0)
    compressed = log1p(raw)
    if not percentile_basis:
        return round(min(100.0, compressed * 20), 2)

    basis = sorted(log1p(max(float(value), 0.0)) for value in percentile_basis)
    if not basis:
        return round(min(100.0, compressed * 20), 2)
    lower_or_equal = sum(1 for value in basis if value <= compressed)
    return round(lower_or_equal / len(basis) * 100, 2)


def impact_weight(engagement_score: Any) -> float:
    score = min(max(_safe_float(engagement_score) or 0.0, 0.0), 100.0)
    return round(0.5 + 1.5 * score / 100, 3)


def score_to_rating(score: Any) -> float | None:
    normalized = _safe_float(score)
    if normalized is None:
        return None
    normalized = min(max(normalized, 0.0), 100.0)
    return round(1 + 4 * normalized / 100, 2)


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
