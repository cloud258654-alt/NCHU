from __future__ import annotations

import os
from typing import Any

from services.reputation_scoring.scoring_config import load_reputation_scoring_config


def analyze_text(text: str, *, mode: str | None = None) -> dict[str, Any]:
    config = load_reputation_scoring_config()
    selected_mode = mode or os.getenv("NLP_ANALYSIS_MODE") or config["analysis"]["mode"]
    if selected_mode == "none":
        return {
            "analysis_status": "pending",
            "sentiment": None,
            "sentiment_score_normalized": None,
            "model_confidence": None,
            "analysis_method": "none",
            "model_name": None,
            "model_version": None,
            "topic": [],
            "risk_signals": [],
        }
    if selected_mode == "rule_based":
        return _rule_based_analysis(text)
    return {
        "analysis_status": "failed",
        "sentiment": None,
        "sentiment_score_normalized": None,
        "model_confidence": None,
        "analysis_method": selected_mode,
        "model_name": None,
        "model_version": None,
        "topic": [],
        "risk_signals": ["unsupported_analysis_mode"],
    }


def _rule_based_analysis(text: str) -> dict[str, Any]:
    normalized = text.casefold()
    positive_terms = ("好吃", "推薦", "親切", "乾淨", "滿意", "positive", "good")
    negative_terms = ("難吃", "糟", "不推", "失望", "髒", "negative", "bad")
    positives = sum(1 for term in positive_terms if term in normalized)
    negatives = sum(1 for term in negative_terms if term in normalized)
    if positives > negatives:
        sentiment = "positive"
        score = 75
    elif negatives > positives:
        sentiment = "negative"
        score = 25
    else:
        sentiment = "neutral"
        score = 50
    return {
        "analysis_status": "completed",
        "sentiment": sentiment,
        "sentiment_score_normalized": score,
        "model_confidence": 0.5 if positives or negatives else 0.25,
        "analysis_method": "rule_based",
        "model_name": None,
        "model_version": None,
        "topic": [],
        "risk_signals": [],
    }
