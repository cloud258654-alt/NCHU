from __future__ import annotations

from dataclasses import dataclass

from core.logger import get_logger


class CircuitOpenError(RuntimeError):
    pass


@dataclass(slots=True)
class CircuitState:
    is_open: bool = False
    reason: str | None = None


class CircuitBreaker:
    """Stops platform work when compliant risk rules are triggered."""

    def __init__(self) -> None:
        self._states: dict[str, CircuitState] = {}
        self.logger = get_logger("anti_block.circuit_breaker")

    def open(self, platform: str, reason: str) -> None:
        self._states[platform] = CircuitState(is_open=True, reason=reason)
        self.logger.warning("Circuit opened: platform=%s reason=%s", platform, reason)

    def close(self, platform: str) -> None:
        self._states[platform] = CircuitState()

    def reason(self, platform: str) -> str | None:
        return self._states.get(platform, CircuitState()).reason

    def is_open(self, platform: str) -> bool:
        return self._states.get(platform, CircuitState()).is_open

    def raise_if_open(self, platform: str) -> None:
        reason = self.reason(platform)
        if self.is_open(platform):
            raise CircuitOpenError(f"Circuit open for {platform}: {reason}")

