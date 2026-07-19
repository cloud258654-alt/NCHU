from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReputationSummaryRequest(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=255)
    message_text: str | None = Field(default=None, max_length=5000)
    business_name: str | None = Field(default=None, max_length=255)
    business_id: int | None = Field(default=None, gt=0)
    task_id: int | None = Field(default=None, gt=0)
    webhook_event_id: str | None = Field(default=None, max_length=255)
    refresh: bool = True


class ReputationCrawlRequest(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=255)
    business_name: str = Field(min_length=1, max_length=255)
    webhook_event_id: str | None = Field(default=None, max_length=255)


class ReputationCrawlJobStatusRequest(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=255)


@dataclass(frozen=True)
class BusinessRecord:
    id: int
    name: str
    branch_name: str | None = None

    @property
    def display_name(self) -> str:
        if self.branch_name:
            return f"{self.name}｜{self.branch_name}"
        return self.name


@dataclass(frozen=True)
class PlatformSummary:
    platform: str
    label: str
    total: int
    analyzed: int
    positive: int
    neutral: int
    negative: int
    unclassified: int
    risk_score: float | None
    risk_score_count: int
    risk_points: int | None
    risk_level: str | None
    updated_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return data


@dataclass(frozen=True)
class ReputationOverview:
    total_reviews: int
    analyzed_reviews: int
    positive: int
    neutral: int
    negative: int
    unclassified: int
    risk_score: float | None
    risk_points: int | None
    risk_level: str | None
    summary: str
    updated_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return data
