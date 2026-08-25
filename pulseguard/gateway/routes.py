import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from pulseguard.gateway.auth import require_api_key
from pulseguard.gateway.limiter import limiter
from pulseguard.logging_config import get_logger
from pulseguard.models.signals import RawSignal
from pulseguard.redis_client import get_async_redis
from pulseguard.security.sanitise import hash_handle, sanitise_pii

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1")


async def _build_lifecycle(signal_id: str) -> dict[str, Any]:
    """Join all Redis hashes to produce a full signal lifecycle record."""
    redis = get_async_redis()
    validated_raw, triage_raw, resolution_raw, escalation_raw = (
        await redis.hget("pulseguard:validated_signals", signal_id),
        await redis.hget("pulseguard:triage_reports", signal_id),
        await redis.hget("pulseguard:resolutions", signal_id),
        await redis.hget("pulseguard:escalations", signal_id),
    )

    result: dict[str, Any] = {"signal_id": signal_id}

    if validated_raw:
        vs = json.loads(validated_raw)
        raw = vs.get("raw", {})
        result["sentinel"] = {
            "source": raw.get("source"),
            "carrier": vs.get("detected_carrier"),
            "is_valid": vs.get("is_valid"),
            "validity_reason": vs.get("validity_reason"),
            "content_preview": (raw.get("content") or "")[:200],
            "url": raw.get("url"),
            "posted_at": raw.get("posted_at"),
            "validated_at": vs.get("validated_at"),
        }

    if triage_raw:
        tr = json.loads(triage_raw)
        result["triage"] = {
            "category": tr.get("category"),
            "resolution_tier": tr.get("resolution_tier"),
            "severity_score": tr.get("severity_score"),
            "sentiment_score": tr.get("sentiment_score"),
            "churn_risk": tr.get("churn_risk"),
            "routing_decision": tr.get("routing_decision"),
            "routing_rationale": tr.get("routing_rationale"),
            "triaged_at": tr.get("triaged_at"),
        }

    if resolution_raw:
        rr = json.loads(resolution_raw)
        result["resolver"] = {
            "resolved": rr.get("resolved"),
            "confidence_score": rr.get("confidence_score"),
            "draft_response": rr.get("draft_response"),
            "escalation_reason": rr.get("escalation_reason"),
            "resolved_at": rr.get("resolved_at"),
        }

    if escalation_raw:
        eb = json.loads(escalation_raw)
        result["escalation"] = {
            "severity": eb.get("severity"),
            "summary": eb.get("summary"),
            "recommended_action": eb.get("recommended_action"),
            "churn_risk": eb.get("churn_risk"),
            "sentiment_score": eb.get("sentiment_score"),
            "acknowledged": eb.get("acknowledged"),
            "acknowledged_by": eb.get("acknowledged_by"),
            "escalated_at": eb.get("escalated_at"),
        }

    # Derive overall stage
    if escalation_raw:
        eb = json.loads(escalation_raw)
        result["stage"] = "escalated"
        result["severity"] = eb.get("severity")
        result["acknowledged"] = eb.get("acknowledged", False)
    elif resolution_raw:
        rr = json.loads(resolution_raw)
        result["stage"] = "resolved" if rr.get("resolved") else "escalated"
    elif triage_raw:
        result["stage"] = "triaged"
    elif validated_raw:
        result["stage"] = "validated"
    else:
        result["stage"] = "unknown"

    return result


async def _get_all_signal_ids(redis: Any) -> list[str]:
    return list(await redis.hkeys("pulseguard:validated_signals"))


class IngestRequest(BaseModel):
    source: str
    source_id: str = Field(max_length=500)
    author_handle: str = Field(max_length=500)
    # Bounded well above any real post length on every supported platform
    # (Reddit's own cap is 40,000) — an unauthenticated length here would
    # let one ingest call balloon into an arbitrarily expensive LLM request
    # across all four agents.
    content: str = Field(max_length=40_000)
    url: str = Field(max_length=2000)
    posted_at: datetime
    carrier_hint: str | None = Field(default=None, max_length=100)
    adapter_metadata: dict[str, Any] = {}


class AckRequest(BaseModel):
    ack_by: str


# ── Signal endpoints ────────────────────────────────────────────────────────


@router.post("/signals/ingest", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
async def ingest_signal(request: Request, req: IngestRequest) -> dict[str, Any]:
    """Manually ingest a signal (for testing and integration).

    Rate-limited: each call fans out to all four LLM agents, so this is
    also the API's main cost/abuse surface, not just a traffic concern.
    """
    signal = RawSignal(
        signal_id=str(uuid.uuid4()),
        source=req.source,
        source_id=req.source_id,
        carrier_hint=req.carrier_hint,
        author_handle=hash_handle(req.author_handle),
        content=sanitise_pii(req.content),
        url=req.url,
        posted_at=req.posted_at,
        ingested_at=datetime.now(UTC),
        adapter_metadata=req.adapter_metadata,
    )

    from pulseguard.agents.sentinel import process_signal

    trace_id = str(uuid.uuid4())
    import asyncio

    asyncio.create_task(process_signal(signal, trace_id))

    from pulseguard.gateway.metrics import signals_ingested

    signals_ingested.labels(source=req.source, carrier=req.carrier_hint or "unknown").inc()

    logger.info("manual_ingest", signal_id=signal.signal_id)
    return {"signal_id": signal.signal_id, "trace_id": trace_id, "status": "queued"}


@router.get("/signals/{signal_id}/lifecycle", dependencies=[Depends(require_api_key)])
async def get_signal_lifecycle(signal_id: str) -> dict[str, Any]:
    """Full lifecycle for one signal: SENTINEL → TRIAGE → RESOLVER/ESCALATION."""
    result = await _build_lifecycle(signal_id)
    if result.get("stage") == "unknown":
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return result


@router.get("/pipeline/signals", dependencies=[Depends(require_api_key)])
async def list_pipeline_signals(
    source: str | None = Query(None, description="Filter by feed source"),
    stage: str | None = Query(None, description="Filter by stage: escalated, resolved, triaged"),
    hours: int = Query(24, ge=1, le=168),
) -> dict[str, Any]:
    """All signals with full lifecycle joined. Use source= to filter by feed type."""
    from datetime import timedelta

    redis = get_async_redis()
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    all_ids = await _get_all_signal_ids(redis)

    signals = []
    for sid in all_ids:
        lc = await _build_lifecycle(sid)
        sentinel = lc.get("sentinel", {})

        # Time filter
        posted = sentinel.get("posted_at")
        if posted:
            try:
                dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except Exception:
                pass

        # Source filter
        if source and sentinel.get("source") != source:
            continue

        # Stage filter
        if stage and lc.get("stage") != stage:
            continue

        signals.append(lc)

    # Sort newest first
    signals.sort(
        key=lambda s: s.get("sentinel", {}).get("posted_at") or "",
        reverse=True,
    )
    return {"signals": signals, "count": len(signals)}


@router.get("/signals/{signal_id}", dependencies=[Depends(require_api_key)])
async def get_signal(signal_id: str) -> dict[str, Any]:
    from pulseguard.mcp_servers.output_mcp import get_signal_status

    result = await get_signal_status(signal_id)
    if "error" in result and result.get("code") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return result


@router.get("/signals", dependencies=[Depends(require_api_key)])
async def list_signals(
    carrier: str | None = Query(None),
    status: str | None = Query(None),
    source: str | None = Query(None),
    hours: int = Query(24, ge=1, le=168),
) -> dict[str, Any]:
    from pulseguard.mcp_servers.output_mcp import list_resolved

    resolved = await list_resolved(carrier=carrier, hours=hours)
    return resolved


# ── Escalation endpoints ────────────────────────────────────────────────────


@router.get("/escalations", dependencies=[Depends(require_api_key)])
async def list_escalations_endpoint(
    priority: str | None = Query(None),
    acknowledged: bool | None = Query(None),
) -> dict[str, Any]:
    from pulseguard.mcp_servers.output_mcp import list_escalations

    return await list_escalations(priority=priority, acknowledged=acknowledged)


@router.post("/escalations/{signal_id}/ack", dependencies=[Depends(require_api_key)])
async def acknowledge_escalation(signal_id: str, req: AckRequest) -> dict[str, Any]:
    from pulseguard.mcp_servers.notify_mcp import acknowledge_escalation as notify_ack

    result = await notify_ack(signal_id=signal_id, ack_by=req.ack_by)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/escalations/{signal_id}/export", dependencies=[Depends(require_api_key)])
async def export_escalation(signal_id: str) -> Response:
    """Download full escalation lifecycle as JSON file."""
    from pulseguard.mcp_servers.output_mcp import export_escalation_json

    result = await export_escalation_json(signal_id)
    if "error" in result and result.get("code") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"Escalation {signal_id} not found")
    return Response(
        content=json.dumps(result, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="escalation_{signal_id}.json"'},
    )


# ── Infrastructure endpoints ────────────────────────────────────────────────


@router.get("/adapters/status", dependencies=[Depends(require_api_key)])
async def adapter_status() -> dict[str, Any]:
    from pulseguard.mcp_servers.feed_mcp import get_adapter_status

    return await get_adapter_status()


@router.get("/orchestrator/status", dependencies=[Depends(require_api_key)])
async def orchestrator_status() -> dict[str, Any]:
    from pulseguard.orchestrator.graph import orchestrator

    return await orchestrator.get_status()
