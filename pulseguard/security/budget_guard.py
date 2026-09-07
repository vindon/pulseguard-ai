"""Hard spend cap on LLM usage, checked before every agent LLM call.

Two independent counters (daily, monthly) live in Redis as plain floats,
keyed by the current UTC calendar date / year-month so a new day or month
starts a fresh, zero-valued key by construction — the reset happens at
real calendar boundaries, not by sliding a TTL forward. (An earlier version
of this module tried to reset by refreshing a fixed-window TTL on every
write, but that pushes expiry to "now + window" on *every* call, so a
continuously-running service that calls record_spend() at least once a
day never lets the key expire — once a cap was hit, check_budget() would
raise forever until someone manually cleared Redis.) The TTL still set on
each write here is just housekeeping to eventually garbage-collect old
date-keyed entries; it plays no role in the reset logic.

check_budget() is called before an LLM invocation; record_spend() is
called after, using the real token counts from the response's usage
metadata rather than an estimate, so the guard tracks actual spend, not
a guess.
"""

from datetime import UTC, datetime

from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.redis_client import get_async_redis

logger = get_logger(__name__)

_SECONDS_PER_DAY = 86400
_DAILY_KEY_TTL_SECONDS = 2 * _SECONDS_PER_DAY
_MONTHLY_KEY_TTL_SECONDS = 32 * _SECONDS_PER_DAY


def _daily_key() -> str:
    return f"pulseguard:spend:daily:{datetime.now(UTC).strftime('%Y-%m-%d')}"


def _monthly_key() -> str:
    return f"pulseguard:spend:monthly:{datetime.now(UTC).strftime('%Y-%m')}"


class BudgetExceededError(Exception):
    """Raised by check_budget() when a configured cap has already been hit.
    Callers must not invoke an LLM after catching this — see orchestrator
    halt-on-failure (Task 4) for what happens to the pipeline when it fires.
    """


async def check_budget() -> None:
    if settings.daily_budget_usd_cap <= 0 and settings.monthly_budget_usd_cap <= 0:
        return

    redis = get_async_redis()

    if settings.daily_budget_usd_cap > 0:
        daily_raw = await redis.get(_daily_key())
        daily_spent = float(daily_raw) if daily_raw else 0.0
        if daily_spent > settings.daily_budget_usd_cap:
            raise BudgetExceededError(
                f"daily spend ${daily_spent:.2f} exceeds cap ${settings.daily_budget_usd_cap:.2f}"
            )

    if settings.monthly_budget_usd_cap > 0:
        monthly_raw = await redis.get(_monthly_key())
        monthly_spent = float(monthly_raw) if monthly_raw else 0.0
        if monthly_spent > settings.monthly_budget_usd_cap:
            raise BudgetExceededError(
                f"monthly spend ${monthly_spent:.2f} exceeds cap ${settings.monthly_budget_usd_cap:.2f}"
            )


async def record_spend(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = settings.model_pricing_map
    if model not in pricing:
        logger.warning("budget_guard_unknown_model_pricing", model=model)
        return 0.0

    input_rate, output_rate = pricing[model]
    cost = (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate

    redis = get_async_redis()
    daily_key = _daily_key()
    monthly_key = _monthly_key()
    await redis.incrbyfloat(daily_key, cost)
    await redis.expire(daily_key, _DAILY_KEY_TTL_SECONDS)
    await redis.incrbyfloat(monthly_key, cost)
    await redis.expire(monthly_key, _MONTHLY_KEY_TTL_SECONDS)

    logger.info(
        "budget_guard_spend_recorded",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost, 6),
        recorded_at=datetime.now(UTC).isoformat(),
    )
    return cost
