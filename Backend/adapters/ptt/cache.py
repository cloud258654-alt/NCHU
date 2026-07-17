from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("adapters.ptt.cache")
CACHE_ROOT = Path(__file__).resolve().parent / "cache"

from adapters.ptt.config import (
    PTT_CACHE_TTL_SECONDS,
    PTT_TERMINAL_QUARANTINE_TTL_SECONDS,
    PTT_TRANSIENT_QUARANTINE_TTL_SECONDS,
)

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()

def get_cached_article(url: str, diagnostics: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if _service_run():
        if diagnostics is not None:
            diagnostics["cache"]["miss"] += 1
        return None
    try:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_ROOT / f"{_url_hash(url)}.json"
        if not cache_file.exists():
            if diagnostics is not None:
                diagnostics["cache"]["miss"] += 1
            return None
            
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        if (datetime.now(timezone.utc) - fetched_at).total_seconds() > PTT_CACHE_TTL_SECONDS:
            # Cache expired
            cache_file.unlink(missing_ok=True)
            if diagnostics is not None:
                diagnostics["cache"]["stale"] += 1
            return None
            
        if diagnostics is not None:
            diagnostics["cache"]["hit"] += 1
        return data.get("parsed_payload")
    except Exception as exc:
        logger.warning("Failed to read from PTT cache: %s", exc)
        if diagnostics is not None:
            diagnostics["cache"]["miss"] += 1
        return None

def set_cached_article(url: str, payload: dict[str, Any], diagnostics: dict[str, Any] | None = None) -> bool:
    if _service_run():
        return False
    try:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_ROOT / f"{_url_hash(url)}.json"
        
        data = {
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "parsed_payload": payload,
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        if diagnostics is not None:
            diagnostics["cache"]["write_success"] += 1
        return True
    except Exception as exc:
        logger.warning("Failed to write to PTT cache: %s", exc)
        if diagnostics is not None:
            diagnostics["cache"]["write_failed"] += 1
        return False

def is_quarantined(url: str, diagnostics: dict[str, Any] | None = None) -> bool:
    if _service_run():
        return False
    try:
        quarantine_file = CACHE_ROOT / "failed_urls.jsonl"
        if not quarantine_file.exists():
            return False
            
        now = datetime.now(timezone.utc)
        with quarantine_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                data = json.loads(line)
                if data["url"] == url:
                    retry_after_str = data.get("retry_after")
                    if retry_after_str:
                        retry_after = datetime.fromisoformat(retry_after_str)
                        if now < retry_after:
                            if diagnostics is not None:
                                diagnostics["fetch"]["quarantine_skipped"] += 1
                            return True
        return False
    except Exception as exc:
        logger.warning("Failed to check quarantine list: %s", exc)
        return False

def quarantine_url(url: str, reason: str, diagnostics: dict[str, Any] | None = None) -> None:
    if _service_run():
        return
    try:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        quarantine_file = CACHE_ROOT / "failed_urls.jsonl"
        
        now = datetime.now(timezone.utc)
        
        terminal_reasons = {"HTTP_404", "HTTP_410", "invalid_ptt_url", "malformed_url"}
        is_terminal = reason in terminal_reasons or "404" in reason or "410" in reason
        
        if is_terminal:
            ttl = PTT_TERMINAL_QUARANTINE_TTL_SECONDS
        else:
            ttl = PTT_TRANSIENT_QUARANTINE_TTL_SECONDS
            
        retry_after = now + timedelta(seconds=ttl)
        
        # Read existing to update or keep
        records = []
        found = False
        if quarantine_file.exists():
            with quarantine_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data["url"] == url:
                        data["last_seen"] = now.isoformat()
                        data["reason"] = reason
                        data["retry_after"] = retry_after.isoformat()
                        found = True
                    records.append(data)
                    
        if not found:
            records.append({
                "url": url,
                "reason": reason,
                "first_seen": now.isoformat(),
                "last_seen": now.isoformat(),
                "retry_after": retry_after.isoformat()
            })
            
        with quarantine_file.open("w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
                
        if diagnostics is not None:
            diagnostics["fetch"]["quarantined"] += 1
    except Exception as exc:
        logger.warning("Failed to write to quarantine file: %s", exc)


def _service_run() -> bool:
    return bool(os.getenv("BI_RMP_SERVICE_TASK_ID"))
