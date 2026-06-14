from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.redis_client import get_async_redis
from pulseguard.tracing import tool_trace

configure_logging()
logger = get_logger(__name__)

mcp = FastMCP("pulseguard-dedup-mcp")

_BLOOM_KEY = "pulseguard:dedup:bloom"
_SEEN_COUNT_KEY = "pulseguard:dedup:seen_total"
_DROPPED_COUNT_KEY = "pulseguard:dedup:dropped_total"

# Simple Redis SET-based dedup (bloom filter approximation without extra Redis modules).
# For production at scale, replace with RedisBloom or pybloom-live backed by Redis.
_SEEN_SET_KEY = "pulseguard:dedup:seen_ids"


class ErrorResponse(BaseModel):
    error: str
    code: str


def _dedup_id(content_hash: str, source_id: str) -> str:
    return f"{content_hash}:{source_id}"


@mcp.tool()
@tool_trace("dedup", "check_duplicate")
async def check_duplicate(content_hash: str, source_id: str) -> dict[str, Any]:
    """Check if a signal has been seen before. Returns is_duplicate=True if seen."""
    if not content_hash or not source_id:
        return ErrorResponse(
            error="content_hash and source_id are required", code="INVALID_PARAM"
        ).model_dump()
    try:
        redis = get_async_redis()
        key = _dedup_id(content_hash, source_id)
        is_dup = await redis.sismember(_SEEN_SET_KEY, key)
        logger.info(
            "check_duplicate",
            content_hash=content_hash[:8],
            source_id=source_id,
            is_duplicate=bool(is_dup),
        )
        return {"is_duplicate": bool(is_dup)}
    except Exception as exc:
        logger.error("check_duplicate_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("dedup", "register_signal")
async def register_signal(content_hash: str, source_id: str) -> dict[str, Any]:
    """Register a signal as seen. Call after validation to prevent re-processing."""
    if not content_hash or not source_id:
        return ErrorResponse(
            error="content_hash and source_id are required", code="INVALID_PARAM"
        ).model_dump()
    try:
        redis = get_async_redis()
        key = _dedup_id(content_hash, source_id)
        await redis.sadd(_SEEN_SET_KEY, key)
        await redis.incr(_SEEN_COUNT_KEY)
        logger.info("register_signal", content_hash=content_hash[:8], source_id=source_id)
        return {"registered": True, "key": key}
    except Exception as exc:
        logger.error("register_signal_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("dedup", "get_dedup_stats")
async def get_dedup_stats() -> dict[str, Any]:
    """Return total signals seen and total dropped as duplicates."""
    try:
        redis = get_async_redis()
        seen = await redis.get(_SEEN_COUNT_KEY)
        dropped = await redis.get(_DROPPED_COUNT_KEY)
        return {
            "total_seen": int(seen or 0),
            "total_dropped_as_duplicate": int(dropped or 0),
        }
    except Exception as exc:
        logger.error("get_dedup_stats_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


if __name__ == "__main__":
    mcp.run()
