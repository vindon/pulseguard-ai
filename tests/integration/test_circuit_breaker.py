"""
Circuit breaker tests — adapter and global breaker behaviour.
"""

from unittest.mock import AsyncMock, patch

import pytest

from pulseguard.orchestrator.circuit_breaker import CircuitBreaker, GlobalCircuitBreaker


class TestAdapterCircuitBreaker:
    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker("test_adapter", threshold=3)
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch(
            "pulseguard.orchestrator.circuit_breaker.get_async_redis", return_value=mock_redis
        ):
            assert not cb.is_open
            await cb.record_error()
            await cb.record_error()
            assert not cb.is_open
            await cb.record_error()  # 3rd error — threshold reached
        assert cb.is_open

    @pytest.mark.asyncio
    async def test_closes_on_success(self):
        cb = CircuitBreaker("test_adapter2", threshold=2)
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch(
            "pulseguard.orchestrator.circuit_breaker.get_async_redis", return_value=mock_redis
        ):
            await cb.record_error()
            await cb.record_error()
            assert cb.is_open
            await cb.record_success()
        assert not cb.is_open
        assert cb._consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_get_state_returns_dict(self):
        cb = CircuitBreaker("test_adapter3", threshold=5)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="2")

        with patch(
            "pulseguard.orchestrator.circuit_breaker.get_async_redis", return_value=mock_redis
        ):
            state = await cb.get_state()

        assert state["name"] == "test_adapter3"
        assert "state" in state
        assert "consecutive_errors" in state


class TestGlobalCircuitBreaker:
    @pytest.mark.asyncio
    async def test_pauses_when_queue_exceeds_threshold(self):
        gcb = GlobalCircuitBreaker(threshold=10)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="15")

        with patch(
            "pulseguard.orchestrator.circuit_breaker.get_async_redis", return_value=mock_redis
        ):
            should_pause = await gcb.should_pause_intake()
        assert should_pause is True

    @pytest.mark.asyncio
    async def test_allows_intake_below_threshold(self):
        gcb = GlobalCircuitBreaker(threshold=100)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="50")

        with patch(
            "pulseguard.orchestrator.circuit_breaker.get_async_redis", return_value=mock_redis
        ):
            should_pause = await gcb.should_pause_intake()
        assert should_pause is False

    @pytest.mark.asyncio
    async def test_empty_queue_allows_intake(self):
        gcb = GlobalCircuitBreaker(threshold=100)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch(
            "pulseguard.orchestrator.circuit_breaker.get_async_redis", return_value=mock_redis
        ):
            should_pause = await gcb.should_pause_intake()
        assert should_pause is False
