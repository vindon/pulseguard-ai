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


@pytest.fixture(autouse=True)
def _reset_consecutive_failures():
    """_consecutive_failures is a module-level dict in graph.py, shared for
    the lifetime of the process so a real halt survives across signals for
    the same agent. Several tests below reuse the agent name "resolver" to
    exercise the 3-strikes/reset logic in isolation, so the counter must be
    cleared between tests or an earlier test's failures leak into the next.
    """
    from pulseguard.orchestrator import graph

    graph._consecutive_failures.clear()
    yield
    graph._consecutive_failures.clear()


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
