from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


@dataclass(frozen=True, slots=True)
class PlatformPolicy:
    min_delay: float = 1.0
    max_delay: float = 3.0
    max_scroll: int = 5
    max_concurrency: int = 1
    stop_on_login: bool = True
    stop_on_captcha: bool = True
    stop_on_verification: bool = True
    stop_on_status: bool = True


class CrawlPolicy:
    DEFAULT_POLICY = PlatformPolicy()

    def __init__(self, policies: dict[str, PlatformPolicy] | None = None) -> None:
        self._policies = policies or {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CrawlPolicy":
        policy_path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "config" / "crawl_policy.yaml"
        if not policy_path.exists():
            return cls()
        text = policy_path.read_text(encoding="utf-8")
        payload = yaml.safe_load(text) if yaml is not None else _parse_simple_yaml(text)
        payload = payload or {}
        policies = {
            platform: PlatformPolicy(
                min_delay=float(values.get("min_delay", cls.DEFAULT_POLICY.min_delay)),
                max_delay=float(values.get("max_delay", cls.DEFAULT_POLICY.max_delay)),
                max_scroll=int(values.get("max_scroll", cls.DEFAULT_POLICY.max_scroll)),
                max_concurrency=max(1, int(values.get("max_concurrency", cls.DEFAULT_POLICY.max_concurrency))),
                stop_on_login=bool(values.get("stop_on_login", cls.DEFAULT_POLICY.stop_on_login)),
                stop_on_captcha=bool(values.get("stop_on_captcha", cls.DEFAULT_POLICY.stop_on_captcha)),
                stop_on_verification=bool(values.get("stop_on_verification", cls.DEFAULT_POLICY.stop_on_verification)),
                stop_on_status=bool(values.get("stop_on_status", cls.DEFAULT_POLICY.stop_on_status)),
            )
            for platform, values in payload.items()
            if isinstance(values, dict)
        }
        return cls(policies)

    def for_platform(self, platform: str) -> PlatformPolicy:
        return self._policies.get(platform, self.DEFAULT_POLICY)

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {
            platform: {
                "min_delay": policy.min_delay,
                "max_delay": policy.max_delay,
                "max_scroll": policy.max_scroll,
                "max_concurrency": policy.max_concurrency,
                "stop_on_login": policy.stop_on_login,
                "stop_on_captcha": policy.stop_on_captcha,
                "stop_on_verification": policy.stop_on_verification,
                "stop_on_status": policy.stop_on_status,
            }
            for platform, policy in self._policies.items()
        }


def _parse_simple_yaml(text: str) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            current = line[:-1]
            payload[current] = {}
        elif current and ":" in line:
            key, value = line.split(":", 1)
            payload[current][key.strip()] = _parse_scalar(value.strip())
    return payload


def _parse_scalar(value: str) -> Any:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
