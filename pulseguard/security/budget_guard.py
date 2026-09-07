"""Hard spend cap on LLM usage, checked before every agent LLM call.

Two independent counters (daily, monthly) live in Redis as plain floats,
reset naturally by TTL rather than a cron job — each increment refreshes
the TTL to the remaining time in that period. check_budget() is called
before an LLM invocation; record_spend() is called after, using the
real token counts from the response's usage metadata rather than an
estimate, so the guard tracks actual spend, not a guess.
"""

from datetime import UTC, datetime

from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.redis_client import get_async_redis

logger = get_logger(__name__)

_DAILY_KEY = "pulseguard:spend:daily"
_MONTHLY_KEY = "pulseguard:spend:monthly"
_SECONDS_PER_DAY = 86400
_SECONDS_PER_MONTH = 31 * _SECONDS_PER_DAY


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
        daily_raw = await redis.get(_DAILY_KEY)
        daily_spent = float(daily_raw) if daily_raw else 0.0
        if daily_spent > settings.daily_budget_usd_cap:
            raise BudgetExceededError(
                f"daily spend ${daily_spent:.2f} exceeds cap ${settings.daily_budget_usd_cap:.2f}"
            )

    if settings.monthly_budget_usd_cap > 0:
        monthly_raw = await redis.get(_MONTHLY_KEY)
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
    await redis.incrbyfloat(_DAILY_KEY, cost)
    await redis.expire(_DAILY_KEY, _SECONDS_PER_DAY)
    await redis.incrbyfloat(_MONTHLY_KEY, cost)
    await redis.expire(_MONTHLY_KEY, _SECONDS_PER_MONTH)

    logger.info(
        "budget_guard_spend_recorded",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost, 6),
        recorded_at=datetime.now(UTC).isoformat(),
    )
    return cost
