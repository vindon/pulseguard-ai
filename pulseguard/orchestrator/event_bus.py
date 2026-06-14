"""
Redis Streams event bus.
Agents publish events here; the orchestrator consumes and routes them.
"""

from pulseguard.logging_config import get_logger
from pulseguard.models.resolution import ResolutionRecord
from pulseguard.models.signals import ValidatedSignal
from pulseguard.models.triage import TriageReport
from pulseguard.redis_client import get_async_redis

logger = get_logger(__name__)

_STREAM_RAW = "pulseguard:stream:raw_signals"
_STREAM_VALIDATED = "pulseguard:stream:validated_signals"
_STREAM_TRIAGED = "pulseguard:stream:triage_reports"
_STREAM_NEEDS_ESCALATION = "pulseguard:stream:needs_escalation"


async def publish_raw_signal(signal: object) -> None:
    redis = get_async_redis()
    await redis.xadd(_STREAM_RAW, {"data": signal.model_dump_json()})  # type: ignore[attr-defined]
    logger.debug("event_published", stream=_STREAM_RAW)


async def publish_validated_signal(signal: ValidatedSignal) -> None:
    redis = get_async_redis()
    await redis.xadd(_STREAM_VALIDATED, {"data": signal.model_dump_json()})
    logger.debug("event_published", stream=_STREAM_VALIDATED, signal_id=signal.signal_id)


async def publish_triage_report(report: TriageReport) -> None:
    redis = get_async_redis()
    await redis.xadd(
        _STREAM_TRIAGED,
        {
            "data": report.model_dump_json(),
            "routing": report.routing_decision,
        },
    )
    logger.debug("event_published", stream=_STREAM_TRIAGED, signal_id=report.signal_id)


async def publish_escalation_needed(signal_id: str, resolution: ResolutionRecord) -> None:
    redis = get_async_redis()
    await redis.xadd(
        _STREAM_NEEDS_ESCALATION,
        {
            "signal_id": signal_id,
            "escalation_reason": resolution.escalation_reason or "",
            "attempted_response": resolution.draft_response,
        },
    )
    logger.debug("event_published", stream=_STREAM_NEEDS_ESCALATION, signal_id=signal_id)


async def consume_stream(
    stream: str, consumer_group: str, consumer_name: str, count: int = 10
) -> list[dict]:
    redis = get_async_redis()
    try:
        await redis.xgroup_create(stream, consumer_group, id="0", mkstream=True)
    except Exception:
        pass  # Group already exists

    messages = await redis.xreadgroup(
        consumer_group, consumer_name, {stream: ">"}, count=count, block=1000
    )
    results = []
    for _, entries in messages or []:
        for msg_id, data in entries:
            results.append({"id": msg_id, "data": data})
            await redis.xack(stream, consumer_group, msg_id)
    return results
