from __future__ import annotations

import time
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class HealthSnapshot:
    platform: str
    keyword: str
    success_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    elapsed_seconds: float = 0.0
    risk_reason: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class HealthMonitor:
    def __init__(self, *, platform: str, keyword: str) -> None:
        self.platform = platform
        self.keyword = keyword
        self.started_at = time.monotonic()
        self.success_count = 0
        self.failed_count = 0
        self.blocked_count = 0
        self.risk_reason: str | None = None

    def record_success(self, count: int = 1) -> None:
        self.success_count += count

    def record_failure(self, count: int = 1) -> None:
        self.failed_count += count

    def record_blocked(self, reason: str) -> None:
        self.blocked_count += 1
        self.risk_reason = reason

    def snapshot(self) -> HealthSnapshot:
        return HealthSnapshot(
            platform=self.platform,
            keyword=self.keyword,
            success_count=self.success_count,
            failed_count=self.failed_count,
            blocked_count=self.blocked_count,
            elapsed_seconds=time.monotonic() - self.started_at,
            risk_reason=self.risk_reason,
        )

