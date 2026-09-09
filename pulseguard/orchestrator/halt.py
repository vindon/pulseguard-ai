"""System-wide halt flag: when set, the orchestrator's dispatch wrapper
(_dispatch_safely in graph.py) stops launching new agent work and every
signal-processing entrypoint returns early, until a human clears it via
POST /api/v1/admin/halt/clear. This replaces silent, indefinite retry of
a systemically broken pipeline (a bad API key, a persistent schema
mismatch, an already-exceeded budget cap) with a stop that requires a
human to look at it — the same "halt beats silent retry" policy already
proven in a sibling project after a real incident there."""

import json
from datetime import UTC, datetime

from pulseguard.redis_client import get_async_redis

_HALT_KEY = "pulseguard:halted"


async def is_halted() -> bool:
    redis = get_async_redis()
    return await redis.get(_HALT_KEY) is not None


async def halt(reason: str) -> None:
    redis = get_async_redis()
    payload = json.dumps({"reason": reason, "halted_at": datetime.now(UTC).isoformat()})
    await redis.set(_HALT_KEY, payload)


async def clear_halt() -> None:
    redis = get_async_redis()
    await redis.delete(_HALT_KEY)
