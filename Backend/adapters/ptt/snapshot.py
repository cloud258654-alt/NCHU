from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
import logging

logger = logging.getLogger("adapters.ptt.snapshot")
SNAPSHOT_ROOT = Path(__file__).resolve().parent / "debug_html"

def save_html_snapshot(html: str, external_id: str | None = None) -> Path | None:
    try:
        now = datetime.now(timezone.utc)
        date_dir = SNAPSHOT_ROOT / now.strftime("%Y%m%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        
        file_name = _safe_snapshot_name(external_id or now.strftime("%H%M%S_%f"))
        if not file_name.endswith(".html"):
            file_name = f"{file_name}.html"
            
        path = date_dir / file_name
        path.write_text(html, encoding="utf-8")
        logger.info("PTT abnormal HTML snapshot saved: path=%s", path)
        return path
    except Exception as exc:
        logger.warning("Failed to save HTML snapshot: %s", exc)
        return None


def _safe_snapshot_name(value: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or "snapshot"
