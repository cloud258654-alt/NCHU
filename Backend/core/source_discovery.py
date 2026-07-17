from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from urllib.parse import parse_qsl, quote_plus, unquote_plus, urlencode, urlsplit, urlunsplit

from core.logger import get_logger
from core.search_config import SearchConfig, load_config
from core.search_engines import _clean_bing_url, _clean_duckduckgo_url, create_engine
from core.search_models import SearchQuery, SearchResult


logger = get_logger("core.source_discovery")

GOOGLE_MAPS_HOSTS = {
    "google.com",
    "www.google.com",
    "maps.google.com",
    "google.com.tw",
    "www.google.com.tw",
    "maps.google.com.tw",
}
GOOGLE_SEARCH_REDIRECT_HOSTS = {
    "google.com",
    "www.google.com",
    "bing.com",
    "www.bing.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
}
GOOGLE_MAPS_SHORT_URL_HOSTS = {"maps.app.goo.gl"}
GOOGLE_MAPS_ALLOWED_QUERY_KEYS = {"api", "cid", "place_id", "query", "query_place_id"}
_UNSET = object()


@dataclass(frozen=True, slots=True)
class GoogleMapsCandidate:
    raw_url: str
    normalized_url: str
    title: str
    engine: str
    query: str
    rank: int
    accepted: bool
    candidate_type: str | None
    score: int
    rejection_reason: str | None


@dataclass(frozen=True, slots=True)
class GoogleMapsDiscoveryResult:
    url: str
    source: str
    diagnostics: dict


def new_google_maps_source_discovery_diagnostics() -> dict:
    return {
        "enabled": False,
        "engines_attempted": [],
        "queries": [],
        "raw_results_seen": 0,
        "accepted_candidates": 0,
        "rejected_candidates": 0,
        "selected_url": None,
        "selected_source": None,
        "fallback_used": False,
        "results": [],
        "errors": [],
    }


async def discover_platform_urls(
    *,
    business_name: str,
    keyword: str | None = None,
    platforms: list[str] | tuple[str, ...] | None = None,
    deadline: float | None = None,
    diagnostics: dict | None = None,
) -> dict[str, str]:
    """Discover required platform URLs from business context.

    The public service does not ask users for URLs. For MVP, only Google Maps
    needs source URL discovery; PTT and Threads search by business query.
    """

    if platforms is not None and "google_maps" not in set(platforms):
        return {}

    result = await discover_google_maps_source_url(
        business_name=business_name,
        keyword=keyword,
        deadline=deadline,
        diagnostics=diagnostics,
    )
    return {"google_maps": result.url}


async def discover_google_maps_source_url(
    *,
    business_name: str,
    keyword: str | None = None,
    location: str | None = None,
    deadline: float | None = None,
    diagnostics: dict | None = None,
) -> GoogleMapsDiscoveryResult:
    diagnostics = _ensure_google_maps_source_discovery_diagnostics(diagnostics)
    diagnostics["enabled"] = google_maps_discovery_enabled()
    queries = build_google_maps_discovery_queries(business_name, keyword, location=location)
    diagnostics["queries"] = queries

    fallback_url = google_maps_search_url(business_name, location=location)
    if not diagnostics["enabled"]:
        diagnostics["fallback_used"] = True
        diagnostics["selected_url"] = fallback_url
        diagnostics["selected_source"] = "generated_fallback"
        return GoogleMapsDiscoveryResult(fallback_url, "generated_fallback", diagnostics)

    engine_names = google_maps_discovery_engine_names(google_maps_discovery_engine())
    candidates: list[GoogleMapsCandidate] = []
    seen: set[str] = set()

    for engine_name in engine_names:
        if deadline is not None and _remaining(deadline) <= 0:
            diagnostics["errors"].append(
                {"engine": engine_name, "type": "timeout", "message": "Google Maps discovery deadline expired"}
            )
            break
        diagnostics["engines_attempted"].append(engine_name)
        try:
            config = _deadline_config(load_config(), deadline)
            engine = create_engine(engine_name, config)
            for rendered_query in queries:
                if deadline is not None and _remaining(deadline) <= 0:
                    diagnostics["errors"].append(
                        {"engine": engine_name, "type": "timeout", "message": "Google Maps discovery deadline expired"}
                    )
                    break
                query_config = _deadline_config(config, deadline)
                engine = create_engine(engine_name, query_config)
                results = await engine.search(
                    SearchQuery(
                        keyword=rendered_query,
                        engine=engine_name,
                        max_results=google_maps_discovery_max_results(),
                    )
                )
                diagnostics["raw_results_seen"] += len(results)
                for result in results:
                    candidate = google_maps_candidate_from_result(
                        result,
                        business_name=business_name,
                        location=location,
                        seen=seen,
                    )
                    diagnostics["results"].append(candidate_to_diagnostics(candidate))
                    if candidate.accepted:
                        seen.add(candidate.normalized_url)
                        candidates.append(candidate)
                        diagnostics["accepted_candidates"] += 1
                    else:
                        diagnostics["rejected_candidates"] += 1
            if any(is_high_confidence_google_maps_candidate(candidate) for candidate in candidates):
                break
        except Exception as exc:
            diagnostics["errors"].append(
                {"engine": engine_name, "type": exc.__class__.__name__, "message": str(exc)}
            )
            continue

    selected = select_google_maps_candidate(candidates)
    if selected is not None:
        diagnostics["selected_url"] = selected.normalized_url
        diagnostics["selected_source"] = selected.engine
        logger.info(
            "Discovered Google Maps source URL: engine=%s score=%s type=%s url=%s",
            selected.engine,
            selected.score,
            selected.candidate_type,
            selected.normalized_url,
        )
        return GoogleMapsDiscoveryResult(selected.normalized_url, selected.engine, diagnostics)

    diagnostics["fallback_used"] = True
    diagnostics["selected_url"] = fallback_url
    diagnostics["selected_source"] = "generated_fallback"
    diagnostics["results"].append(
        {
            "engine": "generated_fallback",
            "query": "",
            "raw_url": fallback_url,
            "normalized_url": fallback_url,
            "title": "",
            "accepted": True,
            "candidate_type": "search_fallback",
            "score": 0,
            "rejection_reason": None,
        }
    )
    logger.info("No Google Maps source URL discovered; using search URL: %s", fallback_url)
    return GoogleMapsDiscoveryResult(fallback_url, "generated_fallback", diagnostics)


def google_maps_discovery_enabled() -> bool:
    return os.getenv("GOOGLE_MAPS_DISCOVERY_ENABLED", "true").strip().casefold() not in {
        "0",
        "false",
        "no",
        "disabled",
    }


def _ensure_google_maps_source_discovery_diagnostics(diagnostics: dict | None) -> dict:
    defaults = new_google_maps_source_discovery_diagnostics()
    if diagnostics is None:
        return defaults
    for key, value in defaults.items():
        if key not in diagnostics:
            diagnostics[key] = value
    return diagnostics


def google_maps_discovery_engine() -> str:
    return os.getenv("GOOGLE_MAPS_DISCOVERY_ENGINE", "auto").strip().casefold() or "auto"


def google_maps_discovery_max_results() -> int:
    return max(1, int(os.getenv("GOOGLE_MAPS_DISCOVERY_MAX_RESULTS", "10")))


def google_maps_discovery_query_variant_limit() -> int:
    return max(1, int(os.getenv("GOOGLE_MAPS_DISCOVERY_QUERY_VARIANT_LIMIT", "4")))


def google_maps_discovery_engine_names(option: str, *, searxng_base_url: str | None | object = _UNSET) -> list[str]:
    option = (option or "auto").strip().casefold()
    if option in {"disabled", "none", "off"}:
        return []
    if option == "auto":
        config = load_config()
        base_url = config.searxng_base_url if searxng_base_url is _UNSET else searxng_base_url
        names = []
        if base_url:
            names.append("searxng")
        names.extend(["duckduckgo", "bing"])
        return names
    if option in {"searxng", "duckduckgo", "bing"}:
        return [option]
    raise ValueError(f"Unsupported Google Maps discovery engine: {option}")


def build_google_maps_discovery_queries(
    business_name: str,
    keyword: str | None,
    location: str | None = None,
) -> list[str]:
    business = " ".join((business_name or "").split())
    del keyword  # Google Maps discovery intentionally uses business identity only.
    location = " ".join((location or "").split())
    base = " ".join(part for part in (business, location) if part).strip()
    variants = [
        f"{base or business} site:google.com/maps",
        f"{base or business} Google Maps",
    ]
    output: list[str] = []
    for query in variants:
        query = " ".join(query.split())
        if query and query not in output:
            output.append(query)
        if len(output) >= google_maps_discovery_query_variant_limit():
            break
    return output


def classify_google_maps_candidate(url: str) -> tuple[str, str]:
    normalized_url, reason, _candidate_type = _classify_google_maps_candidate(url)
    return normalized_url, reason


def google_maps_candidate_from_result(
    result: SearchResult,
    *,
    business_name: str,
    location: str | None,
    seen: set[str],
) -> GoogleMapsCandidate:
    raw_url = result.url or ""
    normalized_url, reason, candidate_type = _classify_google_maps_candidate(raw_url)
    accepted = bool(normalized_url and reason == "accepted")
    if accepted and normalized_url in seen:
        accepted = False
        reason = "duplicate"
    identity_text = f"{result.title} {unquote_plus(normalized_url or raw_url)}"
    if accepted and not _contains_compact(identity_text, business_name):
        accepted = False
        reason = "business_mismatch"
    score = score_google_maps_candidate(
        normalized_url or raw_url,
        title=result.title,
        business_name=business_name,
        location=location,
        candidate_type=candidate_type,
        accepted=accepted,
    )
    if accepted and score < 0:
        accepted = False
        reason = "low_confidence"
    return GoogleMapsCandidate(
        raw_url=diagnostic_safe_google_maps_url(raw_url),
        normalized_url=diagnostic_safe_google_maps_url(normalized_url),
        title=result.title,
        engine=result.engine,
        query=result.query,
        rank=result.rank,
        accepted=accepted,
        candidate_type=candidate_type,
        score=score,
        rejection_reason=None if accepted else reason,
    )


def score_google_maps_candidate(
    url: str,
    *,
    title: str,
    business_name: str,
    location: str | None,
    candidate_type: str | None,
    accepted: bool,
) -> int:
    score = 0
    if candidate_type == "place_url":
        score += 100
    if candidate_type == "cid_url":
        score += 90
    if candidate_type == "place_id_url":
        score += 80
    if _contains_compact(title, business_name):
        score += 30
    if location and _contains_compact(title, location):
        score += 20
    if "google.com/maps" in url or "maps.google.com" in url:
        score += 10
    if candidate_type in {"search_url", "search_fallback"}:
        score -= 30
    if not accepted:
        score -= 100
    return score


def select_google_maps_candidate(candidates: list[GoogleMapsCandidate]) -> GoogleMapsCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.score, -item.rank), reverse=True)[0]


def is_high_confidence_google_maps_candidate(candidate: GoogleMapsCandidate) -> bool:
    return bool(
        candidate.accepted
        and candidate.candidate_type in {"place_url", "cid_url", "place_id_url"}
    )


def candidate_to_diagnostics(candidate: GoogleMapsCandidate) -> dict:
    return {
        "engine": candidate.engine,
        "query": candidate.query,
        "raw_url": candidate.raw_url,
        "normalized_url": candidate.normalized_url,
        "title": candidate.title,
        "rank": candidate.rank,
        "accepted": candidate.accepted,
        "candidate_type": candidate.candidate_type,
        "score": candidate.score,
        "rejection_reason": candidate.rejection_reason,
    }


def google_maps_search_url(business_name: str, *, location: str | None = None) -> str:
    query = " ".join(part.strip() for part in (business_name, location or "") if part and part.strip())
    return f"https://www.google.com/maps/search/{quote_plus(query)}"


def diagnostic_safe_google_maps_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    safe_query = _allowlisted_google_maps_query(parsed.query)
    return urlunsplit((parsed.scheme, netloc, parsed.path, safe_query, ""))


def _classify_google_maps_candidate(url: str) -> tuple[str, str, str | None]:
    cleaned = _clean_search_redirect(url)
    if not cleaned:
        return "", "empty_url", None
    parsed = urlsplit(cleaned)
    host = parsed.netloc.casefold()
    if not parsed.scheme or not host:
        return "", "empty_url", None
    if _is_unresolved_search_redirect(parsed):
        return "", "search_redirect_unresolved", None
    if host in GOOGLE_MAPS_SHORT_URL_HOSTS:
        return "", "short_redirect_unresolved", None
    if "google" not in host:
        return "", "unsupported_domain", None
    if host not in GOOGLE_MAPS_HOSTS:
        return "", "unsupported_domain", None
    if not _is_maps_path_or_query(parsed):
        return "", "google_homepage", None
    if _is_maps_homepage(parsed):
        return "", "maps_homepage", None

    path = parsed.path or ""
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    candidate_type: str | None = None
    if "/maps/place/" in path:
        candidate_type = "place_url"
    elif query.get("cid"):
        candidate_type = "cid_url"
    elif query.get("place_id") or query.get("query_place_id"):
        candidate_type = "place_id_url"
    elif "/maps/search" in path:
        candidate_type = "search_url"
    elif path.startswith("/maps") or host == "maps.google.com":
        candidate_type = "maps_url"

    if candidate_type is None:
        return "", "not_maps_url", None

    normalized = _normalize_google_maps_url(parsed)
    return normalized, "accepted", candidate_type


def _clean_search_redirect(url: str) -> str:
    if not url:
        return ""
    raw = _clean_duckduckgo_url(url.strip())
    raw = _clean_bing_url(raw)
    parsed = urlsplit(raw)
    if parsed.netloc.casefold() in {"google.com", "www.google.com"} and parsed.path == "/url":
        query = dict(parse_qsl(parsed.query, keep_blank_values=False))
        return query.get("q") or query.get("url") or raw
    return raw


def _is_unresolved_search_redirect(parsed) -> bool:
    host = parsed.netloc.casefold()
    if host in {"bing.com", "www.bing.com"} and parsed.path.startswith("/ck/"):
        return True
    if host in {"duckduckgo.com", "www.duckduckgo.com"} and parsed.path.startswith("/l/"):
        return True
    if host in {"google.com", "www.google.com"} and parsed.path == "/url":
        return True
    return False


def _is_maps_path_or_query(parsed) -> bool:
    host = parsed.netloc.casefold()
    if host in {"maps.google.com", "maps.google.com.tw"}:
        return True
    return parsed.path.startswith("/maps")


def _is_maps_homepage(parsed) -> bool:
    path = (parsed.path or "").rstrip("/")
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    if query.get("cid") or query.get("place_id") or query.get("query_place_id") or query.get("query"):
        return False
    return parsed.netloc.casefold() in {"maps.google.com", "maps.google.com.tw"} and path in {"", "/"} or path == "/maps"


def _normalize_google_maps_url(parsed) -> str:
    host = "www.google.com"
    path = parsed.path or "/maps"
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    if parsed.netloc.casefold() in {"maps.google.com", "maps.google.com.tw"} and path.rstrip("/") in {"", "/"} and (
        query.get("cid") or query.get("place_id") or query.get("query_place_id") or query.get("query")
    ):
        path = "/maps"
    safe_query = _allowlisted_google_maps_query(parsed.query)
    return urlunsplit(("https", host, path, safe_query, ""))


def _allowlisted_google_maps_query(query: str) -> str:
    pairs = [
        (key, value)
        for key, value in parse_qsl(query or "", keep_blank_values=False)
        if key in GOOGLE_MAPS_ALLOWED_QUERY_KEYS
    ]
    return urlencode(pairs)


def _contains_compact(text: str, needle: str | None) -> bool:
    folded_text = _compact(text)
    folded_needle = _compact(needle)
    return bool(folded_text and folded_needle and folded_needle in folded_text)


def _compact(value: str | None) -> str:
    return "".join(ch for ch in (value or "").casefold() if ch.isalnum())


def _deadline_config(config: SearchConfig, deadline: float | None) -> SearchConfig:
    timeout = config.timeout_seconds
    if deadline is not None:
        timeout = min(timeout, max(0.1, _remaining(deadline)))
    return replace(config, timeout_seconds=timeout, retry_attempts=1)


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()
