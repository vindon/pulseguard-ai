# tests/unit/test_budget_guard.py
from unittest.mock import AsyncMock, patch

import pytest

from pulseguard.security.budget_guard import BudgetExceededError, check_budget, record_spend


def _mock_redis(daily: str = "0", monthly: str = "0") -> AsyncMock:
    r = AsyncMock()

    async def _get(key: str):
        if "daily" in key:
            return daily
        if "monthly" in key:
            return monthly
        return None

    r.get = AsyncMock(side_effect=_get)
    r.incrbyfloat = AsyncMock()
    r.expire = AsyncMock()
    return r


class TestCheckBudget:
    @pytest.mark.asyncio
    async def test_passes_when_no_caps_configured(self, monkeypatch):
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.daily_budget_usd_cap", 0.0)
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.monthly_budget_usd_cap", 0.0)
        with patch("pulseguard.security.budget_guard.get_async_redis", return_value=_mock_redis()):
            await check_budget()  # must not raise

    @pytest.mark.asyncio
    async def test_passes_when_under_cap(self, monkeypatch):
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.daily_budget_usd_cap", 10.0)
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.monthly_budget_usd_cap", 100.0)
        with patch(
            "pulseguard.security.budget_guard.get_async_redis",
            return_value=_mock_redis(daily="5.00", monthly="50.00"),
        ):
            await check_budget()

    @pytest.mark.asyncio
    async def test_raises_when_daily_cap_exceeded(self, monkeypatch):
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.daily_budget_usd_cap", 10.0)
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.monthly_budget_usd_cap", 1000.0)
        with patch(
            "pulseguard.security.budget_guard.get_async_redis",
            return_value=_mock_redis(daily="10.01", monthly="50.00"),
        ):
            with pytest.raises(BudgetExceededError, match="daily"):
                await check_budget()

    @pytest.mark.asyncio
    async def test_raises_when_monthly_cap_exceeded(self, monkeypatch):
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.daily_budget_usd_cap", 1000.0)
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.monthly_budget_usd_cap", 100.0)
        with patch(
            "pulseguard.security.budget_guard.get_async_redis",
            return_value=_mock_redis(daily="5.00", monthly="100.01"),
        ):
            with pytest.raises(BudgetExceededError, match="monthly"):
                await check_budget()


class TestRecordSpend:
    @pytest.mark.asyncio
    async def test_computes_and_records_cost(self, monkeypatch):
        monkeypatch.setattr(
            "pulseguard.security.budget_guard.settings.model_pricing_per_million_tokens",
            "claude-haiku-4-5:1.00,5.00",
        )
        mock_redis = _mock_redis()
        with patch("pulseguard.security.budget_guard.get_async_redis", return_value=mock_redis):
            cost = await record_spend("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=200_000)
        # 1M input tokens @ $1.00/M + 200K output tokens @ $5.00/M = $1.00 + $1.00 = $2.00
        assert cost == pytest.approx(2.00)
        assert mock_redis.incrbyfloat.await_count == 2  # daily + monthly counters

    @pytest.mark.asyncio
    async def test_unknown_model_records_zero_cost_without_raising(self, monkeypatch):
        monkeypatch.setattr(
            "pulseguard.security.budget_guard.settings.model_pricing_per_million_tokens", ""
        )
        mock_redis = _mock_redis()
        with patch("pulseguard.security.budget_guard.get_async_redis", return_value=mock_redis):
            cost = await record_spend("claude-haiku-4-5", input_tokens=1000, output_tokens=1000)
        assert cost == 0.0
