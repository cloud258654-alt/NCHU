from __future__ import annotations

from typing import Any


def attach_quantitative_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    """Attach calculated rates to the reviews_enriched report response.

    Sentiment percentages use analyzed reviews as the denominator. Coverage and
    unclassified percentages use all collected reviews as the denominator.
    """

    overview = summary.get("overview")
    if not isinstance(overview, dict):
        overview = {}
        summary["overview"] = overview

    platforms = summary.get("platforms")
    if not isinstance(platforms, list):
        platforms = []
        summary["platforms"] = platforms

    for platform in platforms:
        if isinstance(platform, dict):
            _attach_record_metrics(
                platform,
                total_key="total",
                analyzed_key="analyzed",
            )

    _attach_record_metrics(
        overview,
        total_key="total_reviews",
        analyzed_key="analyzed_reviews",
    )
    overview["platform_count"] = sum(
        1
        for platform in platforms
        if isinstance(platform, dict) and _as_nonnegative_int(platform.get("total")) > 0
    )

    summary["report_contract"] = {
        "report_type": "reviews_enriched_quantitative",
        "version": "1.0",
        "sentiment_rate_denominator": "analyzed_reviews",
        "coverage_denominator": "total_reviews",
    }
    return summary


def _attach_record_metrics(
    record: dict[str, Any],
    *,
    total_key: str,
    analyzed_key: str,
) -> None:
    total = _as_nonnegative_int(record.get(total_key))
    positive = _as_nonnegative_int(record.get("positive"))
    neutral = _as_nonnegative_int(record.get("neutral"))
    negative = _as_nonnegative_int(record.get("negative"))
    unclassified = _as_nonnegative_int(record.get("unclassified"))

    classified_count = positive + neutral + negative
    analyzed = max(_as_nonnegative_int(record.get(analyzed_key)), classified_count)
    analysis_gap = max(total - analyzed, 0)

    record["classified_reviews"] = classified_count
    record["analysis_gap"] = analysis_gap
    record["analysis_coverage_pct"] = _percentage(analyzed, total)
    record["positive_pct"] = _percentage(positive, analyzed)
    record["neutral_pct"] = _percentage(neutral, analyzed)
    record["negative_pct"] = _percentage(negative, analyzed)
    record["unclassified_pct"] = _percentage(unclassified, total)
    record["dominant_sentiment"] = _dominant_sentiment(
        positive=positive,
        neutral=neutral,
        negative=negative,
    )


def _dominant_sentiment(*, positive: int, neutral: int, negative: int) -> str:
    counts = {
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
    }
    highest = max(counts.values(), default=0)
    if highest <= 0:
        return "unclassified"

    leaders = [name for name, count in counts.items() if count == highest]
    return leaders[0] if len(leaders) == 1 else "mixed"


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(min(max(numerator / denominator * 100, 0.0), 100.0), 1)


def _as_nonnegative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0
