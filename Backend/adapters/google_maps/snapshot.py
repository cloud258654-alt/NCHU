from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNAPSHOT_ROOT = Path(__file__).resolve().parent / "snapshots"


async def save_google_maps_snapshot(page: Any, *, reason: str) -> Path | None:
    try:
        now = datetime.now(timezone.utc)
        date_dir = SNAPSHOT_ROOT / now.strftime("%Y%m%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        safe_reason = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in reason
        )

        path = date_dir / f"{now.strftime('%H%M%S_%f')}_{safe_reason}.html"
        html = await page.content()
        path.write_text(html, encoding="utf-8")
        return path
    except Exception:
        return None
