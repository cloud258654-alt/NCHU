from __future__ import annotations

from datetime import datetime, timezone

from api.models import BusinessRecord
from api.reputation import RepositorySnapshot, ReputationSummaryService


class FakeRepository:
    def load_snapshot(self, line_user_id: str, business_id: int | None = None) -> RepositorySnapshot:
        assert line_user_id == "U123"
        assert business_id is None
        return RepositorySnapshot(
            business=BusinessRecord(id=1, name="文章牛肉湯", branch_name="安平總店"),
            platform_rows=[
                {
                    "platform": "ptt",
                    "total": 16,
                    "analyzed": 16,
                    "positive": 5,
                    "neutral": 8,
                    "negative": 3,
                    "unclassified": 0,
                    "risk_score": 50.0,
                    "risk_score_count": 16,
                    "risk_points": 7,
                    "risk_rank": 2,
                    "updated_at": datetime(2026, 7, 11, 2, 0, tzinfo=timezone.utc),
                },
                {
                    "platform": "google_maps",
                    "total": 66,
                    "analyzed": 60,
                    "positive": 51,
                    "neutral": 6,
                    "negative": 3,
                    "unclassified": 6,
                    "risk_score": 40.0,
                    "risk_score_count": 60,
                    "risk_points": 11,
                    "risk_rank": 1,
                    "updated_at": datetime(2026, 7, 11, 3, 0, tzinfo=timezone.utc),
                },
            ],
            latest_summary="近期等待時間相關負評略有增加。",
            numeric_risk_available=True,
        )


def test_build_summary_aggregates_platforms() -> None:
    result = ReputationSummaryService(FakeRepository()).build_summary("U123")

    assert result["business"]["display_name"] == "文章牛肉湯｜安平總店"
    assert result["overview"]["total_reviews"] == 82
    assert result["overview"]["positive"] == 56
    assert result["overview"]["negative"] == 6
    assert result["overview"]["risk_points"] == 18
    assert result["overview"]["risk_level"] == "medium"
    assert result["overview"]["risk_score"] == 42.1
    assert result["overview"]["summary"] == "近期等待時間相關負評略有增加。"


def test_empty_data_returns_safe_summary() -> None:
    class EmptyRepository:
        def load_snapshot(self, line_user_id: str, business_id: int | None = None) -> RepositorySnapshot:
            return RepositorySnapshot(
                business=BusinessRecord(id=2, name="測試店家"),
                platform_rows=[],
                latest_summary=None,
                numeric_risk_available=False,
            )

    result = ReputationSummaryService(EmptyRepository()).build_summary("U-empty")

    assert result["overview"]["total_reviews"] == 0
    assert result["overview"]["risk_score"] is None
    assert "尚未收集" in result["overview"]["summary"]
