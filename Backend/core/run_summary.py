from __future__ import annotations

from datetime import datetime, timezone


def summarize_results(results: list[dict], *, started_at: datetime) -> dict:
    total = len(results)
    technical_success = sum(
        1
        for item in results
        if item.get("technical_success", item.get("status") in {"success", "partial_success"})
    )
    data_yield_success = sum(
        1
        for item in results
        if item.get("data_yield_success", bool(item.get("canonical_posts_written") or item.get("canonical_comments_written") or item.get("inserted")))
    )
    outcomes = {
        "success_with_data": 0,
        "success_no_changes": 0,
        "success_no_results": 0,
        "partial_success": 0,
        "blocked": 0,
        "failed": 0,
    }
    for item in results:
        outcome = item.get("outcome") or _infer_outcome(item)
        outcomes[outcome if outcome in outcomes else "failed"] += 1
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    return {
        "total": total,
        "technical_success": technical_success,
        "technical_failed": total - technical_success,
        "technical_success_rate": technical_success / total if total else 0,
        "data_yield_success": data_yield_success,
        "data_yield_zero": total - data_yield_success,
        "data_yield_rate": data_yield_success / total if total else 0,
        "outcomes": outcomes,
        "success": technical_success,
        "failed": total - technical_success,
        "success_rate": technical_success / total if total else 0,
        "elapsed": elapsed,
        "platform_success_rate": {
            item["platform"]: 1.0 if item.get("technical_success", item.get("status") in {"success", "partial_success"}) else 0.0
            for item in results
        },
        "recent_errors": [
            item.get("error_message") for item in results if item.get("error_message")
        ],
    }


def _infer_outcome(item: dict) -> str:
    if item.get("status") == "failed":
        return "failed"
    if item.get("status") == "partial_success":
        return "partial_success"
    if item.get("canonical_posts_written") or item.get("canonical_comments_written") or item.get("inserted"):
        return "success_with_data"
    if item.get("cards_found") or item.get("comments_found"):
        return "success_no_changes"
    return "success_no_results"
