"""
_dispatch_safely wraps every downstream-agent asyncio.create_task in the
orchestrator's stream consumers (_consume_validated_signals,
_consume_triage_reports, _consume_escalation_needed). Before this, a
failure inside process_validated_signal/process_triage_report/
process_escalation was silent except for an unlogged asyncio "Task
exception was never retrieved" warning — the signal just vanished with
no audit trail. These test the wrapper directly.
"""

from unittest.mock import AsyncMock, patch

import pytest

from pulseguard.orchestrator.graph import _dispatch_safely

# _consecutive_failures (the module-level failure counter in graph.py) is
# reset before/after every test by the process-wide autouse fixture in
# tests/conftest.py — several tests below reuse the agent name "resolver"
# to exercise the 3-strikes/reset logic in isolation, and would otherwise
# leak state into each other or into other test modules.


class TestDispatchSafely:
    async def test_failure_is_logged_and_audited(self):
        async def failing() -> None:
            raise RuntimeError("boom")

        with patch("pulseguard.security.audit.write_audit_entry") as mock_audit:
            await _dispatch_safely(failing(), "triage", "sig-001", "trace-001")

        mock_audit.assert_called_once_with(
            "triage", "sig-001", "triage_dispatch_failed", "trace-001", {"reason": "boom"}
        )

    async def test_success_does_not_touch_the_audit_trail(self):
        mock_coro = AsyncMock(return_value=None)()

        with patch("pulseguard.security.audit.write_audit_entry") as mock_audit:
            await _dispatch_safely(mock_coro, "escalation", "sig-002", "trace-002")

        mock_audit.assert_not_called()

    @pytest.mark.asyncio
    async def test_halts_after_three_consecutive_failures_for_same_agent(self):
        from pulseguard.orchestrator.graph import _dispatch_safely

        async def failing_coro():
            raise RuntimeError("systemic failure")

        mock_redis = AsyncMock()
        with (
            patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            for _ in range(3):
                await _dispatch_safely(failing_coro(), "resolver", "sig-1", "trace-1")

        halt_calls = [c for c in mock_redis.set.await_args_list if c.args[0] == "pulseguard:halted"]
        assert len(halt_calls) == 1

    @pytest.mark.asyncio
    async def test_does_not_halt_before_three_failures(self):
        from pulseguard.orchestrator.graph import _dispatch_safely

        async def failing_coro():
            raise RuntimeError("one-off failure")

        mock_redis = AsyncMock()
        with (
            patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            await _dispatch_safely(failing_coro(), "resolver", "sig-1", "trace-1")
            await _dispatch_safely(failing_coro(), "resolver", "sig-2", "trace-2")

        halt_calls = [c for c in mock_redis.set.await_args_list if c.args[0] == "pulseguard:halted"]
        assert len(halt_calls) == 0

    @pytest.mark.asyncio
    async def test_success_resets_the_failure_counter(self):
        from pulseguard.orchestrator.graph import _dispatch_safely

        async def failing_coro():
            raise RuntimeError("failure")

        async def succeeding_coro():
            return None

        mock_redis = AsyncMock()
        with (
            patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            await _dispatch_safely(failing_coro(), "resolver", "sig-1", "trace-1")
            await _dispatch_safely(failing_coro(), "resolver", "sig-2", "trace-2")
            await _dispatch_safely(succeeding_coro(), "resolver", "sig-3", "trace-3")
            await _dispatch_safely(failing_coro(), "resolver", "sig-4", "trace-4")
            await _dispatch_safely(failing_coro(), "resolver", "sig-5", "trace-5")

        halt_calls = [c for c in mock_redis.set.await_args_list if c.args[0] == "pulseguard:halted"]
        assert len(halt_calls) == 0  # only 2 consecutive failures since the reset

    @pytest.mark.asyncio
    async def test_log_event_and_audit_action_overrides_are_used(self):
        """A caller (routes.py's _safe_process_signal) can preserve its own
        pre-existing log/audit naming while still getting halt-counting."""

        async def failing() -> None:
            raise RuntimeError("boom")

        with patch("pulseguard.security.audit.write_audit_entry") as mock_audit:
            await _dispatch_safely(
                failing(),
                "sentinel",
                "sig-010",
                "trace-010",
                log_event="manual_ingest_processing_failed",
                audit_action="signal_processing_failed",
            )

        mock_audit.assert_called_once_with(
            "sentinel", "sig-010", "signal_processing_failed", "trace-010", {"reason": "boom"}
        )


class TestIngestSignalRoutesThroughDispatchSafely:
    """Sentinel's process_signal is invoked from _ingest_signal (fired by
    the _poll_x/_poll_reddit polling loops) as well as from the stream
    consumers' _dispatch_safely calls. Before this fix, _ingest_signal
    awaited process_signal directly with no halt-counting at all, so a
    systemic sentinel failure (bad credentials, an exhausted budget cap)
    — which is also the earliest point in the pipeline such a failure
    would show up — never tripped the halt.
    """

    def _signal(self, signal_id: str = "sig-sentinel-1"):
        from datetime import UTC, datetime

        from pulseguard.models.signals import RawSignal

        return RawSignal(
            signal_id=signal_id,
            source="reddit",
            source_id="src-1",
            author_handle="handle",
            content="some content",
            url="https://example.com/1",
            posted_at=datetime.now(UTC),
            ingested_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_three_consecutive_sentinel_failures_trip_halt(self):
        from pulseguard.orchestrator.graph import PulseGuardOrchestrator

        orch = PulseGuardOrchestrator()
        mock_redis = AsyncMock()
        with (
            patch(
                "pulseguard.agents.sentinel.process_signal",
                AsyncMock(side_effect=RuntimeError("bad api key")),
            ),
            patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            for _ in range(3):
                await orch._ingest_signal(self._signal())

        halt_calls = [c for c in mock_redis.set.await_args_list if c.args[0] == "pulseguard:halted"]
        assert len(halt_calls) == 1
        assert "sentinel" in halt_calls[0].args[1]

    @pytest.mark.asyncio
    async def test_ingest_signal_does_not_raise_on_failure(self):
        """_dispatch_safely swallows the exception, so a failure in one
        signal's sentinel processing must not blow up the polling loop's
        `for signal in signals: await self._ingest_signal(signal)` before
        every fetched signal has been attempted."""
        from pulseguard.orchestrator.graph import PulseGuardOrchestrator

        orch = PulseGuardOrchestrator()
        mock_redis = AsyncMock()
        with (
            patch(
                "pulseguard.agents.sentinel.process_signal",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            await orch._ingest_signal(self._signal())  # must not raise
