import json
from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.models.drafts import PendingDraft
from pulseguard.models.escalation import EscalationBrief
from pulseguard.models.resolution import ResolutionRecord
from pulseguard.redis_client import get_async_redis
from pulseguard.tracing import tool_trace

configure_logging()
logger = get_logger(__name__)

mcp = FastMCP("pulseguard-output-mcp")

_RESOLUTION_KEY = "pulseguard:resolutions"
_ESCALATION_KEY = "pulseguard:escalations"
_SIGNAL_STATUS_KEY_PREFIX = "pulseguard:signal:status:"
_PENDING_DRAFTS_KEY = "pulseguard:pending_drafts"


class SignalStatus(BaseModel):
    signal_id: str
    stage: str  # "pending" | "validated" | "triaged" | "resolved" | "escalated"
    routing: str | None = None
    resolved: bool | None = None
    acknowledged: bool | None = None
    last_updated: datetime


class ErrorResponse(BaseModel):
    error: str
    code: str


@mcp.tool()
@tool_trace("output", "write_resolution")
async def write_resolution(signal_id: str, resolution: dict[str, Any]) -> dict[str, Any]:
    """Persist a ResolutionRecord for a resolved or escalated Tier 0/1 signal."""
    if not signal_id:
        return ErrorResponse(error="signal_id is required", code="INVALID_PARAM").model_dump()
    try:
        rec = ResolutionRecord(**resolution)
        redis = get_async_redis()
        await redis.hset(_RESOLUTION_KEY, signal_id, rec.model_dump_json())
        await redis.hset(
            f"{_SIGNAL_STATUS_KEY_PREFIX}{signal_id}",
            mapping={
                "stage": "resolved",
                "resolved": str(rec.resolved),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        )
        logger.info("write_resolution", signal_id=signal_id, resolved=rec.resolved)
        return {"written": True, "signal_id": signal_id}
    except Exception as exc:
        logger.error("write_resolution_error", signal_id=signal_id, error=str(exc))
        return ErrorResponse(error=str(exc), code="WRITE_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "write_escalation")
async def write_escalation(signal_id: str, brief: dict[str, Any]) -> dict[str, Any]:
    """Persist an EscalationBrief and increment the escalation queue depth."""
    if not signal_id:
        return ErrorResponse(error="signal_id is required", code="INVALID_PARAM").model_dump()
    try:
        eb = EscalationBrief(**brief)
        redis = get_async_redis()
        await redis.hset(_ESCALATION_KEY, signal_id, eb.model_dump_json())
        await redis.hset(
            f"{_SIGNAL_STATUS_KEY_PREFIX}{signal_id}",
            mapping={
                "stage": "escalated",
                "severity": eb.severity,
                "acknowledged": "False",
                "last_updated": datetime.now(UTC).isoformat(),
            },
        )
        await redis.incr("pulseguard:escalation:queue_depth")
        logger.info("write_escalation", signal_id=signal_id, severity=eb.severity)
        return {"written": True, "signal_id": signal_id}
    except Exception as exc:
        logger.error("write_escalation_error", signal_id=signal_id, error=str(exc))
        return ErrorResponse(error=str(exc), code="WRITE_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "write_pending_draft")
async def write_pending_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Persist a PendingDraft — the copilot's core review-queue unit."""
    try:
        pd = PendingDraft(**draft)
        redis = get_async_redis()
        await redis.hset(_PENDING_DRAFTS_KEY, pd.signal_id, pd.model_dump_json())
        return {"written": True, "signal_id": pd.signal_id}
    except Exception as exc:
        logger.error("write_pending_draft_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="WRITE_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "list_pending_drafts")
async def list_pending_drafts(status: str | None = None) -> dict[str, Any]:
    """List drafts in the review queue, optionally filtered by status.

    Malformed records (invalid JSON) are skipped with a warning log; the queue
    is still returned with all valid records to ensure no draft is hidden."""
    try:
        redis = get_async_redis()
        all_raw = await redis.hgetall(_PENDING_DRAFTS_KEY)
        drafts = []
        for signal_id, raw_val in all_raw.items():
            try:
                drafts.append(json.loads(raw_val))
            except json.JSONDecodeError as e:
                logger.warning(
                    "list_pending_drafts_malformed_record",
                    signal_id=signal_id,
                    error=str(e),
                )
        if status:
            drafts = [d for d in drafts if d.get("status") == status]
        drafts.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return {"drafts": drafts, "count": len(drafts)}
    except Exception as exc:
        logger.error("list_pending_drafts_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="READ_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "update_draft_status")
async def update_draft_status(
    signal_id: str, status: str, reviewed_by: str | None = None
) -> dict[str, Any]:
    """Mark a PendingDraft approved or rejected. Does not publish anything —
    Task 10 wires the actual publish call separately, after this write."""
    try:
        redis = get_async_redis()
        raw = await redis.hget(_PENDING_DRAFTS_KEY, signal_id)
        if not raw:
            return ErrorResponse(
                error=f"Draft {signal_id} not found", code="NOT_FOUND"
            ).model_dump()
        pd = PendingDraft(**json.loads(raw))
        pd.status = status  # type: ignore[assignment]
        pd.reviewed_at = datetime.now(UTC)
        pd.reviewed_by = reviewed_by
        await redis.hset(_PENDING_DRAFTS_KEY, signal_id, pd.model_dump_json())
        return pd.model_dump(mode="json")
    except Exception as exc:
        logger.error("update_draft_status_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="WRITE_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "get_signal_status")
async def get_signal_status(signal_id: str) -> dict[str, Any]:
    """Get the current lifecycle stage and status of a signal."""
    if not signal_id:
        return ErrorResponse(error="signal_id is required", code="INVALID_PARAM").model_dump()
    try:
        redis = get_async_redis()
        raw = await redis.hgetall(f"{_SIGNAL_STATUS_KEY_PREFIX}{signal_id}")
        if not raw:
            return ErrorResponse(
                error=f"Signal {signal_id} not found", code="NOT_FOUND"
            ).model_dump()
        return {
            "signal_id": signal_id,
            "stage": raw.get("stage", "unknown"),
            "routing": raw.get("routing"),
            "resolved": raw.get("resolved"),
            "acknowledged": raw.get("acknowledged"),
            "last_updated": raw.get("last_updated"),
        }
    except Exception as exc:
        logger.error("get_signal_status_error", signal_id=signal_id, error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "list_resolved")
async def list_resolved(carrier: str | None = None, hours: int = 24) -> dict[str, Any]:
    """List ResolutionRecords within the last N hours, optionally filtered by carrier."""
    if hours < 1 or hours > 168:
        return ErrorResponse(
            error="hours must be between 1 and 168", code="INVALID_PARAM"
        ).model_dump()
    try:
        redis = get_async_redis()
        all_raw = await redis.hgetall(_RESOLUTION_KEY)
        cutoff = datetime.now(UTC).timestamp() - (hours * 3600)
        records = []
        for _, raw_val in all_raw.items():
            rec = json.loads(raw_val)
            resolved_at = datetime.fromisoformat(rec["resolved_at"]).timestamp()
            if resolved_at < cutoff:
                continue
            if carrier and rec.get("carrier", "").lower() != carrier.lower():
                continue
            records.append(rec)
        records.sort(key=lambda r: r["resolved_at"], reverse=True)
        return {"records": records, "count": len(records)}
    except Exception as exc:
        logger.error("list_resolved_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "list_escalations")
async def list_escalations(
    priority: str | None = None,
    acknowledged: bool | None = None,
) -> dict[str, Any]:
    """List EscalationBriefs, optionally filtered by priority and acknowledgement status."""
    try:
        redis = get_async_redis()
        all_raw = await redis.hgetall(_ESCALATION_KEY)
        briefs = []
        for _, raw_val in all_raw.items():
            brief = json.loads(raw_val)
            if priority and brief.get("severity") != priority:
                continue
            if acknowledged is not None and brief.get("acknowledged") != acknowledged:
                continue
            briefs.append(brief)
        briefs.sort(key=lambda b: b.get("escalated_at", ""), reverse=True)
        return {"briefs": briefs, "count": len(briefs)}
    except Exception as exc:
        logger.error("list_escalations_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "export_escalation_json")
async def export_escalation_json(signal_id: str) -> dict[str, Any]:
    """Export the full escalation lifecycle as a downloadable JSON record."""
    if not signal_id:
        return ErrorResponse(error="signal_id is required", code="INVALID_PARAM").model_dump()
    try:
        redis = get_async_redis()
        brief_raw = await redis.hget(_ESCALATION_KEY, signal_id)
        if not brief_raw:
            return ErrorResponse(
                error=f"Escalation {signal_id} not found", code="NOT_FOUND"
            ).model_dump()

        brief = json.loads(brief_raw)
        status_raw = await redis.hgetall(f"{_SIGNAL_STATUS_KEY_PREFIX}{signal_id}")

        export = {
            "export_generated_at": datetime.now(UTC).isoformat(),
            "signal_id": signal_id,
            "lifecycle_status": status_raw,
            "escalation_brief": brief,
        }
        logger.info("export_escalation_json", signal_id=signal_id)
        return export
    except Exception as exc:
        logger.error("export_escalation_json_error", signal_id=signal_id, error=str(exc))
        return ErrorResponse(error=str(exc), code="EXPORT_ERROR").model_dump()


if __name__ == "__main__":
    mcp.run()
