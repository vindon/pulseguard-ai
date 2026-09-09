from unittest.mock import AsyncMock, patch

import pytest

from pulseguard.orchestrator.halt import clear_halt, halt, is_halted


class TestHalt:
    @pytest.mark.asyncio
    async def test_not_halted_by_default(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        with patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis):
            assert await is_halted() is False

    @pytest.mark.asyncio
    async def test_halt_sets_flag_with_reason(self):
        mock_redis = AsyncMock()
        with patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis):
            await halt("3 consecutive dispatch failures for agent=resolver")
        mock_redis.set.assert_awaited_once()
        args, _ = mock_redis.set.call_args
        assert args[0] == "pulseguard:halted"
        assert "resolver" in args[1]

    @pytest.mark.asyncio
    async def test_is_halted_true_after_flag_set(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b'{"reason": "test"}')
        with patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis):
            assert await is_halted() is True

    @pytest.mark.asyncio
    async def test_clear_halt_removes_flag(self):
        mock_redis = AsyncMock()
        with patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis):
            await clear_halt()
        mock_redis.delete.assert_awaited_once_with("pulseguard:halted")
