from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextFeatures:
    character_count: int
    word_count: int
    line_count: int


def summarize_text_features(text: str | None) -> TextFeatures:
    """Return deterministic text features without loading model artifacts."""

    normalized = (text or "").strip()
    words = [part for part in normalized.split() if part]
    lines = normalized.splitlines() if normalized else []
    return TextFeatures(
        character_count=len(normalized),
        word_count=len(words),
        line_count=len(lines),
    )
