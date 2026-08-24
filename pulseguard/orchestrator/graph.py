"""
Parent LangGraph orchestrator.
Manages adapter polling loops, event routing, and circuit breakers.
"""

import asyncio
import json
import uuid
from typing import Any

from pulseguard.adapters.app_store_adapter import AppStoreAdapter
from pulseguard.adapters.google_play_adapter import GooglePlayAdapter
from pulseguard.adapters.quora_adapter import QuoraAdapter
from pulseguard.adapters.reddit_adapter import RedditAdapter
from pulseguard.adapters.trustpilot_adapter import TrustpilotAdapter
from pulseguard.adapters.x_adapter import XAdapter
from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.models.signals import RawSignal, ValidatedSignal
from pulseguard.models.triage import TriageReport
from pulseguard.orchestrator.circuit_breaker import adapter_circuit_breakers, global_circuit_breaker
from pulseguard.orchestrator.event_bus import consume_stream
from pulseguard.redis_client import get_async_redis

logger = get_logger(__name__)


class PulseGuardOrchestrator:
    def __init__(self) -> None:
        redis = get_async_redis()
        self._adapters = {
            "x": XAdapter(redis_client=redis),
            "reddit": RedditAdapter(),
            "google_play": GooglePlayAdapter(),
            "app_store": AppStoreAdapter(),
            "trustpilot": TrustpilotAdapter(),
            "quora": QuoraAdapter(),
        }
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._running = True
        logger.info("orchestrator_starting")

        self._tasks = [
            asyncio.create_task(self._consume_validated_signals()),
            asyncio.create_task(self._consume_triage_reports()),
            asyncio.create_task(self._consume_escalation_needed()),
            asyncio.create_task(self._update_adapter_health()),
        ]

        if settings.enable_adapter_polling:
            self._tasks += [
                asyncio.create_task(self._poll_x()),
                asyncio.create_task(self._poll_reddit()),
                asyncio.create_task(self._poll_daily("google_play")),
                asyncio.create_task(self._poll_daily("app_store")),
                asyncio.create_task(self._poll_daily("trustpilot")),
                asyncio.create_task(self._poll_daily("quora")),
            ]
        else:
            logger.warning("adapter_polling_disabled")

        logger.info("orchestrator_started", tasks=len(self._tasks))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("orchestrator_stopped")

    # ── Adapter polling loops ───────────────────────────────────────────────

    async def _poll_x(self) -> None:
        adapter = self._adapters["x"]
        cb = adapter_circuit_breakers["x"]
        while self._running:
            if cb.is_open:
                logger.warning("adapter_circuit_open", adapter="x")
                await asyncio.sleep(settings.x_poll_interval_seconds)
                continue
            if await global_circuit_breaker.should_pause_intake():
                logger.warning("global_circuit_open_pausing_intake")
                await asyncio.sleep(60)
                continue
            try:
                signals = await adapter.fetch()
                for signal in signals:
                    await self._ingest_signal(signal)
                await cb.record_success()
            except Exception as exc:
                logger.error("x_poll_error", error=str(exc))
                await cb.record_error()
            await asyncio.sleep(settings.x_poll_interval_seconds)

    async def _poll_reddit(self) -> None:
        adapter = self._adapters["reddit"]
        cb = adapter_circuit_breakers["reddit"]
        while self._running:
            if cb.is_open:
                await asyncio.sleep(300)
                continue
            try:
                signals = await adapter.fetch()
                for signal in signals:
                    await self._ingest_signal(signal)
                await cb.record_success()
            except Exception as exc:
                logger.error("reddit_poll_error", error=str(exc))
                await cb.record_error()
            await asyncio.sleep(300)

    async def _poll_daily(self, adapter_name: str) -> None:
        adapter = self._adapters[adapter_name]
        cb = adapter_circuit_breakers[adapter_name]
        interval = {
            "google_play": 86400,
            "app_store": 86400,
            "trustpilot": settings.trustpilot_poll_interval_seconds,
            "quora": settings.quora_poll_interval_seconds,
        }.get(adapter_name, 86400)
        while self._running:
            if cb.is_open:
                await asyncio.sleep(3600)
                continue
            try:
                signals = await adapter.fetch()
                for signal in signals:
                    await self._ingest_signal(signal)
                await cb.record_success()
            except Exception as exc:
                logger.error("daily_poll_error", adapter=adapter_name, error=str(exc))
                await cb.record_error()
            await asyncio.sleep(interval)

    async def _ingest_signal(self, signal: RawSignal) -> None:
        from pulseguard.agents.sentinel import process_signal

        trace_id = str(uuid.uuid4())
        await process_signal(signal, trace_id)

    # ── Event consumers ─────────────────────────────────────────────────────

    async def _consume_validated_signals(self) -> None:
        while self._running:
            try:
                events = await consume_stream(
                    "pulseguard:stream:validated_signals",
                    "triage-group",
                    "orchestrator",
                )
                for event in events:
                    data = json.loads(event["data"]["data"])
                    validated = ValidatedSignal(**data)
                    trace_id = str(uuid.uuid4())
                    from pulseguard.agents.triage import process_validated_signal

                    asyncio.create_task(process_validated_signal(validated, trace_id))
            except Exception as exc:
                logger.error("consume_validated_error", error=str(exc))
                await asyncio.sleep(5)

    async def _consume_triage_reports(self) -> None:
        while self._running:
            try:
                events = await consume_stream(
                    "pulseguard:stream:triage_reports",
                    "routing-group",
                    "orchestrator",
                )
                for event in events:
                    data = json.loads(event["data"]["data"])
                    routing = event["data"].get("routing", "ESCALATION")
                    report = TriageReport(**data)
                    trace_id = str(uuid.uuid4())

                    # Fetch the validated signal for context
                    redis = get_async_redis()
                    vs_raw = await redis.hget("pulseguard:validated_signals", report.signal_id)
                    validated_signal = json.loads(vs_raw) if vs_raw else {}

                    if routing == "RESOLVER":
                        from pulseguard.agents.resolver import process_triage_report

                        asyncio.create_task(
                            process_triage_report(report, validated_signal, trace_id)
                        )
                    else:
                        from pulseguard.agents.escalation import process_escalation

                        asyncio.create_task(process_escalation(report, validated_signal, trace_id))
            except Exception as exc:
                logger.error("consume_triage_error", error=str(exc))
                await asyncio.sleep(5)

    async def _consume_escalation_needed(self) -> None:
        while self._running:
            try:
                events = await consume_stream(
                    "pulseguard:stream:needs_escalation",
                    "escalation-group",
                    "orchestrator",
                )
                for event in events:
                    signal_id = event["data"].get("signal_id", "")
                    attempted = event["data"].get("attempted_response", "")

                    redis = get_async_redis()
                    triage_raw = await redis.hget("pulseguard:triage_reports", signal_id)
                    vs_raw = await redis.hget("pulseguard:validated_signals", signal_id)

                    if triage_raw and vs_raw:
                        report = TriageReport(**json.loads(triage_raw))
                        validated_signal = json.loads(vs_raw)
                        trace_id = str(uuid.uuid4())
                        from pulseguard.agents.escalation import process_escalation

                        asyncio.create_task(
                            process_escalation(
                                report, validated_signal, trace_id, attempted_resolution=attempted
                            )
                        )
            except Exception as exc:
                logger.error("consume_escalation_error", error=str(exc))
                await asyncio.sleep(5)

    async def _update_adapter_health(self) -> None:
        """Periodically write adapter health to Redis and sync Prometheus gauges."""
        while self._running:
            try:
                redis = get_async_redis()
                for name, adapter in self._adapters.items():
                    health = await adapter.health_check()
                    await redis.hset(
                        "pulseguard:adapters:status",
                        name,
                        health.model_dump_json(),
                    )

                # Sync gauges from Redis into Prometheus
                from pulseguard.gateway.metrics import escalation_queue_depth, x_api_reads_monthly

                x_reads = await redis.get("pulseguard:x:monthly_reads")
                x_api_reads_monthly.set(int(x_reads or 0))
                depth = await redis.get("pulseguard:escalation:queue_depth")
                escalation_queue_depth.set(int(depth or 0))
            except Exception as exc:
                logger.error("health_update_error", error=str(exc))
            await asyncio.sleep(60)

    async def get_status(self) -> dict[str, Any]:
        queue_depth = await global_circuit_breaker.get_queue_depth()
        cb_states = {name: await cb.get_state() for name, cb in adapter_circuit_breakers.items()}
        redis = get_async_redis()
        x_reads = await redis.get("pulseguard:x:monthly_reads")
        return {
            "running": self._running,
            "queue_depth_unacknowledged": queue_depth,
            "global_circuit_open": await global_circuit_breaker.should_pause_intake(),
            "adapter_circuit_breakers": cb_states,
            "x_monthly_reads": int(x_reads or 0),
            "x_monthly_cap": settings.x_monthly_cap,
        }


orchestrator = PulseGuardOrchestrator()
