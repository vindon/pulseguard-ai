import json
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.redis_client import get_async_redis
from pulseguard.tracing import tool_trace

configure_logging()
logger = get_logger(__name__)

mcp = FastMCP("pulseguard-feed-mcp")

_PENDING_KEY = "pulseguard:signals:pending"
_ADAPTER_STATUS_KEY = "pulseguard:adapters:status"


class ErrorResponse(BaseModel):
    error: str
    code: str


@mcp.tool()
@tool_trace("feed", "list_pending_signals")
async def list_pending_signals(source: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List signals awaiting SENTINEL processing."""
    if limit < 1 or limit > 500:
        return ErrorResponse(
            error="limit must be between 1 and 500", code="INVALID_PARAM"
        ).model_dump()
    try:
        redis = get_async_redis()
        raw_signals = await redis.lrange(_PENDING_KEY, 0, limit - 1)
        signals = [json.loads(s) for s in raw_signals]
        if source:
            signals = [s for s in signals if s.get("source") == source]
        logger.info("list_pending_signals", count=len(signals), source=source)
        return {"signals": signals, "count": len(signals)}
    except Exception as exc:
        logger.error("list_pending_signals_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("feed", "mark_signal_processed")
async def mark_signal_processed(signal_id: str, outcome: str) -> dict[str, Any]:
    """Mark a signal as validated or dropped after SENTINEL processing."""
    if not signal_id:
        return ErrorResponse(error="signal_id is required", code="INVALID_PARAM").model_dump()
    if outcome not in ("validated", "dropped"):
        return ErrorResponse(
            error="outcome must be 'validated' or 'dropped'", code="INVALID_PARAM"
        ).model_dump()
    try:
        redis = get_async_redis()
        await redis.hset(f"pulseguard:signal:{signal_id}:status", mapping={"outcome": outcome})
        logger.info("mark_signal_processed", signal_id=signal_id, outcome=outcome)
        return {"signal_id": signal_id, "outcome": outcome, "success": True}
    except Exception as exc:
        logger.error("mark_signal_processed_error", signal_id=signal_id, error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("feed", "get_adapter_status")
async def get_adapter_status() -> dict[str, Any]:
    """Get health status of all registered adapters."""
    try:
        redis = get_async_redis()
        raw = await redis.hgetall(_ADAPTER_STATUS_KEY)
        statuses = {k: json.loads(v) for k, v in raw.items()}
        return {"adapters": statuses, "count": len(statuses)}
    except Exception as exc:
        logger.error("get_adapter_status_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


if __name__ == "__main__":
    mcp.run()
