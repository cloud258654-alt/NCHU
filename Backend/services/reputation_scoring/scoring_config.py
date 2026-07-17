from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_REPUTATION_SCORING_CONFIG: dict[str, Any] = {
    "version": "urs_v1",
    "analysis": {"mode": "none"},
    "google_maps": {"native_weight": 0.70, "sentiment_weight": 0.30},
    "ptt": {"native_weight": 0.45, "sentiment_weight": 0.55, "prior_strength": 5},
    "ptt_comment": {
        "native_weight": 0.35,
        "sentiment_weight": 0.65,
        "push_score": 75,
        "boo_score": 25,
        "arrow_score": 50,
    },
    "threads": {
        "sentiment_weight": 1.0,
        "engagement": {"like": 1.0, "reply": 1.5, "repost": 2.0, "quote": 2.0, "view": 0.05},
    },
    "aggregation": {
        "prior_n": 5,
        "target_sample_count": 20,
        "platform_weights": {"google_maps": 1.0, "ptt": 1.0, "threads": 1.0},
    },
}


def load_reputation_scoring_config(path: str | Path | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_REPUTATION_SCORING_CONFIG)
    config_path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "config" / "reputation_scoring.yaml"
    if not config_path.exists():
        return config

    try:
        import yaml
    except ModuleNotFoundError:
        return config

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return config
    _deep_merge(config, loaded)
    return config


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
