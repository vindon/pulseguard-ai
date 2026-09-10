# tests/unit/test_budget_guard.py
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

import pulseguard.security.budget_guard as budget_guard_module
from pulseguard.config import Settings
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


class _StatefulFakeRedis:
    """A real (in-memory) key-value store, unlike _mock_redis above which
    fakes responses by substring-matching "daily"/"monthly" in the key
    regardless of its exact value. Needed to prove that two different exact
    keys (e.g. today's vs. yesterday's date-partitioned key) are genuinely
    independent counters, not just that the mock was told the right answer.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def incrbyfloat(self, key: str, amount: float) -> float:
        current = float(self.store.get(key, "0")) + amount
        self.store[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class _FixedClock:
    """Stand-in for the `datetime` imported into budget_guard, so tests can
    move "now" across a calendar boundary without real time passing."""

    _now: datetime

    @classmethod
    def now(cls, tz=None):
        return cls._now


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


class TestModelPricingMap:
    def test_parses_multi_model_pricing_string(self):
        # Regression test for the token-pairing parser: a naive split(",")
        # on the whole string breaks apart each entry's own input,output
        # rate pair, so this must be exercised with more than one model to
        # actually catch a regression in the pairing/stride logic.
        settings_instance = Settings(
            model_pricing_per_million_tokens=(
                "claude-haiku-4-5:1.00,5.00,claude-sonnet-4-5:3.00,15.00"
            )
        )
        assert settings_instance.model_pricing_map == {
            "claude-haiku-4-5": (1.0, 5.0),
            "claude-sonnet-4-5": (3.0, 15.0),
        }


class TestCalendarPartitionedKeys:
    def test_daily_key_changes_across_date_boundary_monthly_key_does_not(self, monkeypatch):
        _FixedClock._now = datetime(2026, 9, 7, 23, 59, 0, tzinfo=UTC)
        monkeypatch.setattr(budget_guard_module, "datetime", _FixedClock)
        daily_key_day1 = budget_guard_module._daily_key()
        monthly_key_day1 = budget_guard_module._monthly_key()

        _FixedClock._now = datetime(2026, 9, 8, 0, 1, 0, tzinfo=UTC)
        daily_key_day2 = budget_guard_module._daily_key()
        monthly_key_day2 = budget_guard_module._monthly_key()

        assert daily_key_day1 != daily_key_day2
        assert "2026-09-07" in daily_key_day1
        assert "2026-09-08" in daily_key_day2
        # Same month, so the monthly key must be unchanged.
        assert monthly_key_day1 == monthly_key_day2

    @pytest.mark.asyncio
    async def test_spend_recorded_yesterday_does_not_count_toward_todays_cap(self, monkeypatch):
        monkeypatch.setattr(
            "pulseguard.security.budget_guard.settings.model_pricing_per_million_tokens",
            "claude-haiku-4-5:1.00,5.00",
        )
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.daily_budget_usd_cap", 1.0)
        monkeypatch.setattr("pulseguard.security.budget_guard.settings.monthly_budget_usd_cap", 0.0)
        monkeypatch.setattr(budget_guard_module, "datetime", _FixedClock)

        fake_redis = _StatefulFakeRedis()
        with patch(
            "pulseguard.security.budget_guard.get_async_redis", return_value=fake_redis
        ):
            # "Yesterday": record $2.00 of spend, which already exceeds
            # today's $1.00 daily cap if the two days shared one counter.
            _FixedClock._now = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
            cost = await record_spend(
                "claude-haiku-4-5", input_tokens=2_000_000, output_tokens=0
            )
            assert cost == pytest.approx(2.00)

            # A pre-existing bug (fixed-window TTL refreshed on every write)
            # would make this next call raise, since the sliding TTL never
            # actually lets the counter reset — this proves it now does.
            _FixedClock._now = datetime(2026, 9, 7, 0, 5, 0, tzinfo=UTC)
            await check_budget()  # must not raise: today's key starts at $0
