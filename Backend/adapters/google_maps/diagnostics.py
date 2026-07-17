from __future__ import annotations


def new_google_maps_diagnostics() -> dict:
    return {
        "discovery": {
            "place_urls_discovered": 0,
            "fallback_used": False,
        },
        "navigation": {
            "restricted": False,
            "reviews_tab_opened": False,
            "last_url": None,
            "last_error_type": None,
            "last_error_message": None,
        },
        "reviews": {
            "cards_seen": 0,
            "cards_parsed": 0,
            "duplicates_removed": 0,
            "expanded_buttons_clicked": 0,
            "scroll_rounds": 0,
            "stable_rounds": 0,
        },
        "snapshot": {
            "saved": False,
            "path": None,
            "reason": None,
        },
        "crawl4ai": {
            "attempted": False,
            "success": False,
            "error": None,
        },
        "error": {
            "type": None,
            "message": None,
            "recoverable": None,
        },
    }


def set_google_maps_error(
    diagnostics: dict,
    error_type: str,
    message: str | None,
    *,
    recoverable: bool | None,
) -> None:
    diagnostics["error"]["type"] = error_type
    diagnostics["error"]["message"] = message
    diagnostics["error"]["recoverable"] = recoverable
