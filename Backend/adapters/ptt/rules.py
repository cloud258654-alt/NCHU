from __future__ import annotations

import re
from typing import Any

NEGATIVE_KEYWORDS = [
    "難吃",
    "太貴",
    "踩雷",
    "失望",
    "服務差",
    "態度差",
    "等很久",
    "不會再去",
    "雷",
]

TOPIC_KEYWORDS = {
    "service": ["服務", "態度", "店員", "老闆"],
    "price": ["價格", "太貴", "漲價", "便宜"],
    "food": ["味道", "餐點", "牛肉湯", "麵", "份量"],
    "queue": ["排隊", "等很久", "候位"],
    "environment": ["環境", "衛生", "乾淨", "座位"],
}

def classify_rule_based_signals(article: dict[str, Any]) -> dict[str, Any]:
    title = article.get("title") or ""
    content = article.get("content") or ""
    text = f"{title}\n{content}".casefold()
    
    # 1. Negative keywords match
    matched_negatives = [kw for kw in NEGATIVE_KEYWORDS if kw in text]
    has_negative_keyword = len(matched_negatives) > 0
    
    # 2. Topics match
    matched_topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched_topics.append(topic)
            
    # 3. Risk flags & score calculation
    risk_flags = []
    
    # Rule 1: boo_count >= 3 -> negative_signal
    boo_count = article.get("boo_count") or 0
    if boo_count >= 3:
        risk_flags.append("negative_signal")
        
    # Rule 2: negative keyword count >= 2 -> complaint_signal
    if len(matched_negatives) >= 2:
        risk_flags.append("complaint_signal")
        
    # Rule 3: comment_count >= 20 and ptt_net_score < 0 -> reputation_risk
    comment_count = article.get("comment_count") or 0
    ptt_net_score = article.get("ptt_net_score") or 0
    if comment_count >= 20 and ptt_net_score < 0:
        risk_flags.append("reputation_risk")
        
    # Base risk score calculation
    risk_score = 0.0
    if has_negative_keyword:
        risk_score += 0.2
    risk_score += len(matched_negatives) * 0.1
    risk_score += len(risk_flags) * 0.2
    
    # Cap risk score at 1.0
    risk_score = round(min(risk_score, 1.0), 2)
    
    return {
        "rule_based_signals": {
            "has_negative_keyword": has_negative_keyword,
            "negative_keywords": list(matched_negatives),
            "topics": list(matched_topics),
            "risk_flags": list(risk_flags),
            "risk_score": risk_score,
        }
    }
