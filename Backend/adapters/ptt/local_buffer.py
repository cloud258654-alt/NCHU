from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BUFFER_ROOT = Path(__file__).resolve().parent / "buffer"


def write_ptt_buffer(
    posts: list[dict[str, Any]],
    *,
    query: str,
    crawl_job_id: str | None = None,
    service_task_id: str | None = None,
) -> Path | None:
    if not posts:
        return None

    now = datetime.now(timezone.utc)
    date_dir = BUFFER_ROOT / now.strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    file_stem = crawl_job_id or now.strftime("%H%M%S_%f")
    path = date_dir / f"{file_stem}.jsonl"

    with path.open("w", encoding="utf-8") as handle:
        for post in posts:
            record = {
                "platform": "ptt",
                "query": query,
                "crawl_job_id": crawl_job_id,
                "service_task_id": service_task_id,
                "buffered_at": now.isoformat(),
                "payload": post,
            }
            handle.write(json.dumps(record, ensure_ascii=False, default=str))
            handle.write("\n")

    return path
