from __future__ import annotations

import re
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from ml.safe_text_features import summarize_text_features


BASELINE_VERSION = "rules-baseline-2026-07-18"
MODEL_NAME = "bi-rmp-offline-rules-baseline"
MODEL_KIND = "deterministic_rules_baseline"
ANALYSIS_METHOD = "deterministic_rules"

POSITIVE_TERMS = frozenset(
    {
        "clean",
        "friendly",
        "good",
        "great",
        "helpful",
        "kind",
        "love",
        "nice",
        "polite",
        "professional",
        "quick",
        "recommend",
        "satisfied",
    }
)
NEGATIVE_TERMS = frozenset(
    {
        "angry",
        "bad",
        "broken",
        "dirty",
        "disappointed",
        "expensive",
        "late",
        "poor",
        "refund",
        "rude",
        "sick",
        "slow",
        "terrible",
        "unhappy",
        "unsafe",
        "wait",
        "worse",
        "worst",
    }
)
RISK_TERMS = frozenset(
    {
        "allergy",
        "chargeback",
        "danger",
        "fraud",
        "illegal",
        "injury",
        "lawsuit",
        "refund",
        "scam",
        "sick",
        "threat",
        "unsafe",
    }
)
SERVICE_TERMS = frozenset({"rude", "friendly", "helpful", "polite", "professional", "slow", "wait"})
PRICE_TERMS = frozenset({"cheap", "expensive", "overpriced", "price", "refund"})
QUALITY_TERMS = frozenset({"broken", "clean", "dirty", "fresh", "good", "poor", "quality", "terrible"})

ZH_POSITIVE_TERMS = frozenset(
    {
        "乾淨",
        "友善",
        "好吃",
        "專業",
        "推薦",
        "滿意",
        "親切",
        "讚",
        "快速",
        "喜歡",
        "舒服",
        "細心",
    }
)
ZH_NEGATIVE_TERMS = frozenset(
    {
        "不滿",
        "失望",
        "生氣",
        "很慢",
        "難吃",
        "髒",
        "態度差",
        "糟糕",
        "退費",
        "等太久",
        "貴",
        "不會再來",
        "不推薦",
    }
)
ZH_RISK_TERMS = frozenset(
    {
        "食物中毒",
        "過敏",
        "受傷",
        "危險",
        "詐騙",
        "違法",
        "提告",
        "客訴",
        "退費",
        "不安全",
    }
)
ZH_SERVICE_TERMS = frozenset({"服務", "親切", "態度", "態度差", "等太久", "很慢", "專業", "細心"})
ZH_PRICE_TERMS = frozenset({"價格", "貴", "太貴", "退費", "收費"})
ZH_QUALITY_TERMS = frozenset({"品質", "好吃", "難吃", "乾淨", "髒", "新鮮", "糟糕"})


@dataclass(frozen=True)
class ReviewAnalysisInput:
    content: str
    review_id: str | None = None
    business_id: str | None = None
    platform: str | None = None
    title: str | None = None
    language: str | None = None


def analyze_review(payload: ReviewAnalysisInput) -> dict[str, Any]:
    text = " ".join(part for part in (payload.title, payload.content) if part).strip()
    tokens = _tokens(text)
    positive_hits = _hits(tokens, POSITIVE_TERMS) | _phrase_hits(text, ZH_POSITIVE_TERMS)
    negative_hits = _hits(tokens, NEGATIVE_TERMS) | _phrase_hits(text, ZH_NEGATIVE_TERMS)
    risk_hits = _hits(tokens, RISK_TERMS) | _phrase_hits(text, ZH_RISK_TERMS)

    sentiment_score = _clamp((len(positive_hits) - len(negative_hits)) / 5)
    risk_score = _clamp(len(risk_hits) / 3 + max(len(negative_hits) - len(positive_hits), 0) / 8)
    topics = _topics(tokens, text)
    features = summarize_text_features(text)
    sentiment_label = _sentiment(sentiment_score)
    risk_level = _risk_level(risk_score)
    response_suggestion = _analysis_response_suggestion(
        text=text,
        sentiment_label=sentiment_label,
        risk_level=risk_level,
    )
    human_review_required = risk_level == "high" or bool(risk_hits)
    limitations = [
        "This is a deterministic rules baseline, not a recovered original model.",
        "This is not a production-grade trained machine learning model.",
        "No trained-model accuracy is claimed.",
        "Traditional Chinese support is rules-based phrase matching, not a trained language model.",
    ]

    return {
        "review_id": payload.review_id,
        "business_id": payload.business_id,
        "platform": payload.platform,
        "sentiment_label": sentiment_label,
        "sentiment_score": round(sentiment_score, 3),
        "risk_score": round(risk_score, 3),
        "risk_level": risk_level,
        "topics": topics,
        "tags": sorted(positive_hits | negative_hits | risk_hits),
        "response_suggestion": response_suggestion,
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
        "analysis_id": _analysis_id(payload, text),
        "analyzed_at": _analyzed_at(),
        "human_review_required": human_review_required,
        "limitations": limitations,
        # Backward-compatible fields retained for Gate 4 clients.
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "sentiment": sentiment_label,
        "confidence": _confidence(features.word_count, positive_hits, negative_hits, risk_hits),
        "categories": topics,
        "matched_terms": {
            "positive": sorted(positive_hits),
            "negative": sorted(negative_hits),
            "risk": sorted(risk_hits),
        },
        "summary": _summary(text, sentiment_score, risk_score),
        "suggested_actions": _suggested_actions(sentiment_score, risk_score, topics),
        "features": asdict(features),
    }


def analyze_batch(items: list[ReviewAnalysisInput]) -> dict[str, Any]:
    analyses = [analyze_review(item) for item in items]
    risk_counts: dict[str, int] = {}
    sentiment_counts: dict[str, int] = {}
    for item in analyses:
        risk_counts[item["risk_level"]] = risk_counts.get(item["risk_level"], 0) + 1
        sentiment_counts[item["sentiment_label"]] = sentiment_counts.get(item["sentiment_label"], 0) + 1
    return {
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "count": len(analyses),
        "items": analyses,
        "aggregate": {
            "risk_counts": risk_counts,
            "sentiment_counts": sentiment_counts,
        },
    }


def suggest_response(
    *,
    review_text: str,
    business_name: str | None = None,
    sentiment: str | None = None,
    risk_level: str | None = None,
    tone: str | None = None,
) -> dict[str, Any]:
    inferred = analyze_review(ReviewAnalysisInput(content=review_text))
    final_sentiment = (sentiment or inferred["sentiment_label"]).lower()
    final_risk = (risk_level or inferred["risk_level"]).lower()
    final_tone = (tone or "professional").lower()
    name = business_name or "our team"

    if final_risk == "high":
        response = (
            f"Thank you for telling {name} about this issue. We take this seriously and would like "
            "to review the details directly. Please contact our team with your visit information so we can follow up."
        )
    elif final_sentiment == "positive":
        response = (
            f"Thank you for the feedback. {name} appreciates your support and will keep working to provide a good experience."
        )
    elif final_sentiment == "negative":
        response = (
            f"Thank you for sharing this. {name} is sorry the experience did not meet expectations. "
            "We will review the issue and use it to improve our service."
        )
    else:
        response = (
            f"Thank you for your review. {name} values the feedback and will continue improving the customer experience."
        )

    return {
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "tone": final_tone,
        "suggested_response": response,
        "rationale": {
            "sentiment": final_sentiment,
            "risk_level": final_risk,
            "method": "deterministic template selected from rules baseline",
        },
        "limitations": [
            "This response is generated by deterministic templates, not by an LLM.",
            "Human review is required before customer-facing use.",
        ],
    }


def model_info() -> dict[str, Any]:
    return {
        "service": "dashboard-ml-offline-analysis",
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "original_model_restored": False,
        "production_grade_ml": False,
        "uses_pickle_or_joblib": False,
        "uses_ollama_or_llm": False,
        "description": "Offline deterministic rules baseline for versioned analysis API development.",
        "supported_languages": ["en", "zh-TW"],
        "endpoints": [
            "GET /api/ml/health",
            "GET /api/ml/info",
            "POST /api/ml/analyze-review",
            "POST /api/ml/analyze-batch",
            "POST /api/ai/suggest-response",
        ],
        "limitations": [
            "Not the original recovered model.",
            "Not a production-grade trained machine learning model.",
            "No trained-model accuracy is claimed.",
            "Ollama and LLM integrations are deferred.",
        ],
    }


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z'-]*", text.lower()))


def _hits(tokens: set[str], terms: frozenset[str]) -> set[str]:
    return tokens.intersection(terms)


def _phrase_hits(text: str, terms: frozenset[str]) -> set[str]:
    return {term for term in terms if term in text}


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _sentiment(score: float) -> str:
    if score >= 0.2:
        return "positive"
    if score <= -0.2:
        return "negative"
    return "neutral"


def _risk_level(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def _topics(tokens: set[str], text: str) -> list[str]:
    topics = []
    if tokens.intersection(SERVICE_TERMS) or _phrase_hits(text, ZH_SERVICE_TERMS):
        topics.append("service")
    if tokens.intersection(PRICE_TERMS) or _phrase_hits(text, ZH_PRICE_TERMS):
        topics.append("price")
    if tokens.intersection(QUALITY_TERMS) or _phrase_hits(text, ZH_QUALITY_TERMS):
        topics.append("quality")
    if tokens.intersection(RISK_TERMS) or _phrase_hits(text, ZH_RISK_TERMS):
        topics.append("risk")
    return topics or ["general"]


def _confidence(word_count: int, positive_hits: set[str], negative_hits: set[str], risk_hits: set[str]) -> str:
    signal_count = len(positive_hits) + len(negative_hits) + len(risk_hits)
    if word_count >= 8 and signal_count >= 2:
        return "medium"
    if signal_count >= 1:
        return "low"
    return "low"


def _summary(text: str, sentiment_score: float, risk_score: float) -> str:
    if not text.strip():
        return "No review text was provided."
    sentiment = _sentiment(sentiment_score)
    risk = _risk_level(risk_score)
    return f"Rules baseline classified the review as {sentiment} sentiment with {risk} risk."


def _analysis_response_suggestion(*, text: str, sentiment_label: str, risk_level: str) -> str:
    if _contains_cjk(text):
        if risk_level == "high":
            return "建議先由人工審查並確認事實，再以正式管道回覆顧客。"
        if sentiment_label == "negative":
            return "建議先致謝並承認顧客感受，說明會檢視問題並安排後續改善。"
        if sentiment_label == "positive":
            return "建議感謝顧客支持，並簡短回應會持續維持服務品質。"
        return "建議以中性語氣感謝回饋，並表示會持續改善顧客體驗。"
    if risk_level == "high":
        return "Escalate for human review before sending a customer-facing response."
    if sentiment_label == "negative":
        return "Acknowledge the concern, thank the reviewer, and state that the team will review the issue."
    if sentiment_label == "positive":
        return "Thank the reviewer and reinforce that the team will continue maintaining service quality."
    return "Thank the reviewer for the feedback and keep the response factual."


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _analysis_id(payload: ReviewAnalysisInput, text: str) -> str:
    raw = "|".join(
        [
            BASELINE_VERSION,
            payload.review_id or "",
            payload.business_id or "",
            payload.platform or "",
            payload.language or "",
            text,
        ]
    )
    return "rules-" + sha256(raw.encode("utf-8")).hexdigest()[:24]


def _analyzed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _suggested_actions(sentiment_score: float, risk_score: float, categories: list[str]) -> list[str]:
    actions = []
    if risk_score >= 0.66:
        actions.append("Escalate for manual review before responding.")
    elif risk_score >= 0.33:
        actions.append("Review the issue and prepare a factual follow-up.")
    if sentiment_score <= -0.2:
        actions.append("Acknowledge the complaint and identify an owner for follow-up.")
    if "service" in categories:
        actions.append("Check service workflow notes for the reported touchpoint.")
    return actions or ["Monitor the review and respond according to standard service guidelines."]
