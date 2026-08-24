"""
Circuit breaker implementation for adapters and the global escalation queue.
"""

from datetime import UTC, datetime
from typing import Any

from pulseguard.logging_config import get_logger
from pulseguard.redis_client import get_async_redis

logger = get_logger(__name__)

_ERROR_KEY_PREFIX = "pulseguard:cb:errors:"
_STATE_KEY_PREFIX = "pulseguard:cb:state:"
_ADAPTER_ERROR_THRESHOLD = 5
_GLOBAL_QUEUE_THRESHOLD = 100


class CircuitBreaker:
    """Per-adapter circuit breaker. Opens after N consecutive errors."""

    def __init__(self, name: str, threshold: int = _ADAPTER_ERROR_THRESHOLD) -> None:
        self.name = name
        self.threshold = threshold
        self._open = False
        self._consecutive_errors = 0
        self._opened_at: datetime | None = None

    async def record_success(self) -> None:
        self._consecutive_errors = 0
        self._open = False
        redis = get_async_redis()
        await redis.set(f"{_ERROR_KEY_PREFIX}{self.name}", 0)
        await redis.set(f"{_STATE_KEY_PREFIX}{self.name}", "closed")
        logger.info("circuit_breaker_closed", adapter=self.name)

    async def record_error(self) -> None:
        self._consecutive_errors += 1
        redis = get_async_redis()
        await redis.incr(f"{_ERROR_KEY_PREFIX}{self.name}")

        if self._consecutive_errors >= self.threshold:
            self._open = True
            self._opened_at = datetime.now(UTC)
            await redis.set(f"{_STATE_KEY_PREFIX}{self.name}", "open")
            logger.error(
                "circuit_breaker_opened",
                adapter=self.name,
                consecutive_errors=self._consecutive_errors,
            )

    @property
    def is_open(self) -> bool:
        return self._open

    async def get_state(self) -> dict[str, Any]:
        redis = get_async_redis()
        errors = await redis.get(f"{_ERROR_KEY_PREFIX}{self.name}")
        state = await redis.get(f"{_STATE_KEY_PREFIX}{self.name}")
        return {
            "name": self.name,
            "state": state or "closed",
            "consecutive_errors": int(errors or 0),
            "opened_at": self._opened_at.isoformat() if self._opened_at else None,
        }


class GlobalCircuitBreaker:
    """Halts all new intake when escalation queue exceeds threshold."""

    def __init__(self, threshold: int = _GLOBAL_QUEUE_THRESHOLD) -> None:
        self.threshold = threshold

    async def should_pause_intake(self) -> bool:
        redis = get_async_redis()
        depth = await redis.get("pulseguard:escalation:queue_depth")
        current = int(depth or 0)
        if current >= self.threshold:
            logger.error(
                "global_circuit_breaker_open",
                queue_depth=current,
                threshold=self.threshold,
            )
            return True
        return False

    async def get_queue_depth(self) -> int:
        redis = get_async_redis()
        depth = await redis.get("pulseguard:escalation:queue_depth")
        return int(depth or 0)


# Singleton instances
global_circuit_breaker = GlobalCircuitBreaker()

adapter_circuit_breakers: dict[str, CircuitBreaker] = {
    name: CircuitBreaker(name)
    for name in (
        "x",
        "reddit",
        "google_play",
        "app_store",
        "trustpilot",
        "quora",
    )
}
