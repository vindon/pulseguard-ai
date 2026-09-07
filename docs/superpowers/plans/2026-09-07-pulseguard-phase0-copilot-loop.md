# PulseGuard Phase 0: Draft-Review Copilot Loop + Safety Foundations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a pilot-ready, single-tenant PulseGuard where every drafted response — not just escalated ones — lands in a human-approval queue that can actually publish an approved reply back to X, with spend guards, halt-on-failure, and a minimal eval gate protecting the pipeline from day one.

**Architecture:** Presentation-and-workflow-layer addition on the existing 4-agent core. No multi-tenancy, no new adapters beyond X publishing, no autonomous send path — every new capability in this plan lands behind a human-approval gate. Resolver's existing `emit_resolved` node gains a new write (a `PendingDraft` record) alongside its existing `ResolutionRecord`/escalation-publish behavior, which is unchanged. Two new cross-cutting safety mechanisms (BudgetGuard, halt-on-failure) wrap the existing agent call sites without changing their public interfaces.

**Tech Stack:** Python 3.12, LangGraph, langchain-anthropic, FastAPI, Redis, pytest, respx (HTTP mocking), Next.js 16 frontend (existing), Playwright.

**Spec:** `docs/superpowers/specs/2026-09-07-pulseguard-copilot-pivot-design.md` (§6 publish adapters, §9 permanent-copilot positioning, §12 evals, §13 code quality gates, §14 spend guard, §15 Phase 0/1 success criteria)

## Global Constraints

- Every action stays draft-and-approve — nothing in this plan auto-sends anything. Publishing only happens from the human-triggered `/drafts/{id}/approve` endpoint (spec §9, non-negotiable, not a placeholder for later autonomy).
- `mypy --strict`, `ruff check`, `black --check`, and the full test suite must stay green after every task — no task is done with a red CI (spec §13).
- PII is already sanitised and handles already hashed at signal creation (`adapters/base.py::_make_signal`) — nothing in this plan touches that path or needs to re-derive it.
- Per spec §15's sequencing note: full multi-tenancy is explicitly **not** in scope for this plan. `CarrierConfig` stays as-is; there is one pilot deployment per customer.
- Per spec §6's sequencing note: only the X publish adapter is required for Phase 0/1 — Google Business Profile and Reddit publishing are future work, not part of this plan.
- New settings follow the existing `Settings` class pattern in `pulseguard/config.py` (empty-string/zero default, graceful skip when unset, matching how Slack/email/enterprise-integration settings already work).

---

## Task 1: Harden every LLM client with an explicit timeout and retry cap

**Files:**
- Modify: `pulseguard/agents/sentinel.py:24`
- Modify: `pulseguard/agents/triage.py:25`
- Modify: `pulseguard/agents/resolver.py:28-31`
- Modify: `pulseguard/agents/escalation.py:25`
- Test: `tests/unit/test_llm_client_config.py` (new)

**Interfaces:**
- No behavioral interface changes — same module-level `_MODEL`/`_MODEL_THINKING` names, same call sites. This task only changes construction kwargs.

An unbounded client timeout is exactly what let a stuck pipeline burn spend silently in a sibling project before a hard cap was added (spec §14) — this closes that at the source, before Task 2's BudgetGuard adds spend-level protection on top.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_llm_client_config.py
"""Every ChatAnthropic client in the codebase must set an explicit timeout
and max_retries=1 — an unbounded client timeout is what lets a stuck LLM
call burn spend silently instead of failing fast into the retry/halt logic
in orchestrator/graph.py."""

import pulseguard.agents.escalation as escalation
import pulseguard.agents.resolver as resolver
import pulseguard.agents.sentinel as sentinel
import pulseguard.agents.triage as triage


def _assert_hardened(model) -> None:
    assert model.default_request_timeout is not None
    assert model.default_request_timeout <= 60
    assert model.max_retries == 1


class TestLlmClientHardening:
    def test_sentinel_model(self):
        _assert_hardened(sentinel._MODEL)

    def test_triage_model(self):
        _assert_hardened(triage._MODEL)

    def test_resolver_model(self):
        _assert_hardened(resolver._MODEL)

    def test_resolver_thinking_model(self):
        _assert_hardened(resolver._MODEL_THINKING)

    def test_escalation_model(self):
        _assert_hardened(escalation._MODEL)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_llm_client_config.py -v`
Expected: FAIL — `default_request_timeout` is `None` (or attribute inspection shows no timeout set) on at least the first client checked.

- [ ] **Step 3: Add `timeout=30, max_retries=1` to every `ChatAnthropic(...)` construction**

In `pulseguard/agents/sentinel.py:24`, change:
```python
_MODEL = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
```
to:
```python
_MODEL = ChatAnthropic(model="claude-haiku-4-5", temperature=0, timeout=30, max_retries=1)
```

In `pulseguard/agents/triage.py:25`, apply the identical change to its `_MODEL` line.

In `pulseguard/agents/escalation.py:25`, apply the identical change to its `_MODEL` line.

In `pulseguard/agents/resolver.py:28-31`, change:
```python
_MODEL = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
_MODEL_THINKING = ChatAnthropic(
```
so both `_MODEL` and `_MODEL_THINKING` get `timeout=30, max_retries=1` added to their existing constructor arguments (keep whatever extended-thinking-specific kwargs `_MODEL_THINKING` already has — only add the two new kwargs, do not remove anything).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_llm_client_config.py -v`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green, no regressions.

- [ ] **Step 6: Commit**

```bash
git add pulseguard/agents/sentinel.py pulseguard/agents/triage.py pulseguard/agents/resolver.py pulseguard/agents/escalation.py tests/unit/test_llm_client_config.py
git commit -m "Harden every LLM client with an explicit timeout and max_retries=1"
```

---

## Task 2: BudgetGuard — hard spend cap checked before every LLM call

**Files:**
- Create: `pulseguard/security/budget_guard.py`
- Modify: `pulseguard/config.py`
- Test: `tests/unit/test_budget_guard.py` (new)

**Interfaces:**
- Produces: `class BudgetExceededError(Exception)`, `async def check_budget() -> None` (raises `BudgetExceededError` if the daily or monthly cap is already exceeded — called *before* an LLM invocation), `async def record_spend(model: str, input_tokens: int, output_tokens: int) -> float` (returns the dollar cost just recorded, adds it to Redis-tracked daily/monthly totals) — both consumed by Task 3.
- Consumes: `pulseguard.redis_client.get_async_redis`, new settings `daily_budget_usd_cap`, `monthly_budget_usd_cap`, `model_pricing_per_million_tokens` from `pulseguard.config.settings`.

- [ ] **Step 1: Add budget settings to `pulseguard/config.py`**

Add after the `enable_adapter_polling: bool = True` line:
```python
    # Spend guard — hard caps on LLM spend, checked before every call.
    # 0 means "no cap" (useful for local dev); set real values before any
    # pilot deployment. Pricing is per-million-tokens, "model:input,output"
    # pairs comma-separated, e.g. "claude-haiku-4-5:1.00,5.00" — set from
    # Anthropic's current published pricing at deploy time, not hardcoded
    # here, since pricing changes independently of this codebase.
    daily_budget_usd_cap: float = 0.0
    monthly_budget_usd_cap: float = 0.0
    model_pricing_per_million_tokens: str = ""
```

Add this property after `trusted_proxy_ips_set`:
```python
    @property
    def model_pricing_map(self) -> dict[str, tuple[float, float]]:
        """Parses MODEL_PRICING_PER_MILLION_TOKENS into {model: (input_$/M, output_$/M)}."""
        pricing: dict[str, tuple[float, float]] = {}
        for entry in self.model_pricing_per_million_tokens.split(","):
            entry = entry.strip()
            if not entry:
                continue
            model, rates = entry.split(":")
            input_rate, output_rate = rates.split(",")
            pricing[model.strip()] = (float(input_rate), float(output_rate))
        return pricing
```

- [ ] **Step 2: Write the failing test**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_budget_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pulseguard.security.budget_guard'`.

- [ ] **Step 4: Implement `pulseguard/security/budget_guard.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_budget_guard.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 6: Static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add pulseguard/security/budget_guard.py pulseguard/config.py tests/unit/test_budget_guard.py
git commit -m "Add BudgetGuard: hard daily/monthly spend caps checked before LLM calls"
```

---

## Task 3: Wire BudgetGuard into every agent's LLM call site

**Files:**
- Modify: `pulseguard/agents/sentinel.py` (its `_MODEL.ainvoke` call site)
- Modify: `pulseguard/agents/triage.py` (its `_MODEL.ainvoke` call site)
- Modify: `pulseguard/agents/resolver.py` (its `_MODEL`/`_MODEL_THINKING`/`.ainvoke` call sites)
- Modify: `pulseguard/agents/escalation.py` (its `_MODEL.ainvoke` call site)
- Test: `tests/unit/test_agents.py` (extend existing `TestSentinelAgent`, `TestTriageAgent`, `TestResolverAgent`, `TestEscalationAgent` classes)

**Interfaces:**
- Consumes: `check_budget()`, `record_spend()` from Task 2's `pulseguard.security.budget_guard`.
- Produces: no new public interface — existing agent node functions keep their exact signatures; this task only adds a guard check before, and a spend record after, each `.ainvoke(...)` call.

This task touches every LLM call site in the codebase. Rather than repeat the same wrapper at each of the ~6 call sites, add one shared helper used by all of them.

- [ ] **Step 1: Write the failing test for the shared helper**

```python
# Add to tests/unit/test_agents.py, near the top-level helpers
class TestInvokeWithBudgetGuard:
    @pytest.mark.asyncio
    async def test_raises_before_calling_model_when_over_budget(self):
        from pulseguard.agents.llm_guard import invoke_with_budget_guard
        from pulseguard.security.budget_guard import BudgetExceededError

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock()

        with patch(
            "pulseguard.agents.llm_guard.check_budget",
            AsyncMock(side_effect=BudgetExceededError("over cap")),
        ):
            with pytest.raises(BudgetExceededError):
                await invoke_with_budget_guard(mock_model, [], model_name="claude-haiku-4-5")

        mock_model.ainvoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_records_spend_from_response_usage_metadata(self):
        from pulseguard.agents.llm_guard import invoke_with_budget_guard

        mock_response = MagicMock()
        mock_response.usage_metadata = {"input_tokens": 500, "output_tokens": 100}
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with (
            patch("pulseguard.agents.llm_guard.check_budget", AsyncMock()),
            patch("pulseguard.agents.llm_guard.record_spend", AsyncMock(return_value=0.001)) as mock_record,
        ):
            result = await invoke_with_budget_guard(mock_model, [], model_name="claude-haiku-4-5")

        assert result is mock_response
        mock_record.assert_awaited_once_with("claude-haiku-4-5", input_tokens=500, output_tokens=100)

    @pytest.mark.asyncio
    async def test_missing_usage_metadata_records_zero_without_raising(self):
        from pulseguard.agents.llm_guard import invoke_with_budget_guard

        mock_response = MagicMock()
        mock_response.usage_metadata = None
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with (
            patch("pulseguard.agents.llm_guard.check_budget", AsyncMock()),
            patch("pulseguard.agents.llm_guard.record_spend", AsyncMock()) as mock_record,
        ):
            await invoke_with_budget_guard(mock_model, [], model_name="claude-haiku-4-5")

        mock_record.assert_awaited_once_with("claude-haiku-4-5", input_tokens=0, output_tokens=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agents.py::TestInvokeWithBudgetGuard -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pulseguard.agents.llm_guard'`.

- [ ] **Step 3: Implement `pulseguard/agents/llm_guard.py`**

```python
"""Shared wrapper every agent's LLM call site uses: check the spend cap
before invoking, record actual spend from the response's real token
counts after. One helper here instead of six near-identical inline
try/except blocks across the four agent modules."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from pulseguard.security.budget_guard import check_budget, record_spend


async def invoke_with_budget_guard(
    model: BaseChatModel, messages: list[BaseMessage], *, model_name: str
) -> Any:
    await check_budget()
    response = await model.ainvoke(messages)
    usage = getattr(response, "usage_metadata", None) or {}
    await record_spend(
        model_name,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_agents.py::TestInvokeWithBudgetGuard -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Replace every direct `_MODEL.ainvoke(messages)` call with the guarded helper**

In each of `sentinel.py`, `triage.py`, `resolver.py`, `escalation.py`, find every line matching `response = await _MODEL.ainvoke(messages)` (or `_MODEL_THINKING.ainvoke(...)` in resolver.py) and replace with the guarded call, e.g. in `sentinel.py`:
```python
from pulseguard.agents.llm_guard import invoke_with_budget_guard
...
response = await invoke_with_budget_guard(_MODEL, messages, model_name="claude-haiku-4-5")
```
Apply the same substitution pattern in `triage.py` (`model_name="claude-sonnet-4-6"`), `escalation.py` (`model_name="claude-opus-4-6"`), and in `resolver.py` for both its `_MODEL` call sites (`model_name="claude-sonnet-4-6"`) and its `_MODEL_THINKING` call site (`model_name="claude-sonnet-4-6"` — extended thinking is the same underlying model, just a different call configuration, so pricing is identical).

- [ ] **Step 6: Update existing agent tests to account for the new budget check**

Every existing test in `tests/unit/test_agents.py` that patches `_MODEL`/`_MODEL_THINKING` directly (e.g. `patch("pulseguard.agents.sentinel._MODEL", mock_llm)`) continues to work unchanged, because `invoke_with_budget_guard` still calls `model.ainvoke(...)` on whatever object is passed in — but each of those existing mocked LLM responses must now expose a `usage_metadata` attribute or the guard's `getattr(response, "usage_metadata", None) or {}` fallback silently no-ops (which is safe, just recording $0 spend — acceptable for these tests, no change required). Confirm this by running the full existing suite in the next step rather than editing every fixture individually.

- [ ] **Step 7: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green. If any existing test fails because `check_budget`/`record_spend` now hit real Redis unexpectedly, add `patch("pulseguard.security.budget_guard.get_async_redis", return_value=AsyncMock())` to that specific test rather than changing production code — budget caps default to `0.0` (disabled) in `Settings`, so `check_budget()` should no-op and never touch Redis in any test that hasn't explicitly configured a cap; if a failure appears here it means a test's environment is unexpectedly setting a budget cap and should be diagnosed, not the guard's default behavior.

- [ ] **Step 8: Commit**

```bash
git add pulseguard/agents/llm_guard.py pulseguard/agents/sentinel.py pulseguard/agents/triage.py pulseguard/agents/resolver.py pulseguard/agents/escalation.py tests/unit/test_agents.py
git commit -m "Wire BudgetGuard into every agent LLM call site via a shared helper"
```

---

## Task 4: Strict halt-on-failure — stop a stuck pipeline instead of silently retrying

**Files:**
- Create: `pulseguard/orchestrator/halt.py`
- Modify: `pulseguard/orchestrator/graph.py:28-52` (`_dispatch_safely`)
- Modify: `pulseguard/gateway/routes.py` (new admin endpoints)
- Test: `tests/unit/test_halt.py` (new)
- Test: `tests/unit/test_orchestrator_dispatch.py` (extend existing)

**Interfaces:**
- Produces: `async def is_halted() -> bool`, `async def halt(reason: str) -> None`, `async def clear_halt() -> None` from `pulseguard.orchestrator.halt` — consumed by `_dispatch_safely` (this task) and by the new gateway endpoints (this task).
- Consumes: `pulseguard.redis_client.get_async_redis`. No special-cased import of `BudgetExceededError` — it's a plain `Exception` subclass, so three consecutive budget breaches trip the halt through the same generic `except Exception` path as any other failure type, with no separate wiring needed.

Today, `_dispatch_safely` catches every exception, logs it, writes an audit entry, and lets the orchestrator keep running — meaning a systemically broken agent (a bad API key, a budget cap already exceeded, a persistent schema mismatch) fails silently and repeatedly, once per signal, forever, with no one necessarily noticing. This adds a halt: three consecutive dispatch failures trip a Redis-backed flag that stops new signal processing until a human clears it via the gateway.

- [ ] **Step 1: Write the failing test for the halt module**

```python
# tests/unit/test_halt.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_halt.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pulseguard/orchestrator/halt.py`**

```python
"""System-wide halt flag: when set, the orchestrator's dispatch wrapper
(_dispatch_safely in graph.py) stops launching new agent work and every
signal-processing entrypoint returns early, until a human clears it via
POST /api/v1/admin/halt/clear. This replaces silent, indefinite retry of
a systemically broken pipeline (a bad API key, a persistent schema
mismatch, an already-exceeded budget cap) with a stop that requires a
human to look at it — the same "halt beats silent retry" policy already
proven in a sibling project after a real incident there."""

import json
from datetime import UTC, datetime

from pulseguard.redis_client import get_async_redis

_HALT_KEY = "pulseguard:halted"


async def is_halted() -> bool:
    redis = get_async_redis()
    return await redis.get(_HALT_KEY) is not None


async def halt(reason: str) -> None:
    redis = get_async_redis()
    payload = json.dumps({"reason": reason, "halted_at": datetime.now(UTC).isoformat()})
    await redis.set(_HALT_KEY, payload)


async def clear_halt() -> None:
    redis = get_async_redis()
    await redis.delete(_HALT_KEY)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_halt.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Write the failing test for `_dispatch_safely`'s new halt-after-3-failures behavior**

Add to `tests/unit/test_orchestrator_dispatch.py` (its existing `TestDispatchSafely` class):
```python
    @pytest.mark.asyncio
    async def test_halts_after_three_consecutive_failures_for_same_agent(self):
        from pulseguard.orchestrator.graph import _dispatch_safely
        from pulseguard.orchestrator.halt import is_halted

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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestrator_dispatch.py -v`
Expected: the 3 new tests FAIL (no halt behavior exists yet); the pre-existing tests in this file still PASS.

- [ ] **Step 7: Implement the failure counter and halt trigger in `_dispatch_safely`**

Replace `pulseguard/orchestrator/graph.py:28-52` with:
```python
_consecutive_failures: dict[str, int] = {}
_HALT_THRESHOLD = 3


async def _dispatch_safely(coro: Any, agent: str, signal_id: str, trace_id: str) -> None:
    """Wrapper for the downstream-agent tasks each stream consumer below
    fires via asyncio.create_task. A task scheduled that way runs
    independently of the consumer loop's own try/except — by the time a
    stream message has been read, an unwrapped failure inside
    process_validated_signal/process_triage_report/process_escalation
    was previously silent except for an unlogged "Task exception was
    never retrieved" warning, and the signal just vanished with no audit
    trail (found via the /signals/ingest version of this same gap).

    A third consecutive failure for the same agent trips a system-wide
    halt (pulseguard.orchestrator.halt) instead of retrying indefinitely
    — a systemically broken pipeline (bad credentials, exceeded budget,
    a persistent schema mismatch) should stop and wait for a human, not
    fail once per signal forever.
    """
    from pulseguard.orchestrator.halt import halt
    from pulseguard.security.audit import write_audit_entry

    try:
        await coro
        _consecutive_failures[agent] = 0
    except Exception as exc:
        _consecutive_failures[agent] = _consecutive_failures.get(agent, 0) + 1
        logger.error(
            "agent_dispatch_failed",
            agent=agent,
            signal_id=signal_id,
            trace_id=trace_id,
            error=str(exc),
            consecutive_failures=_consecutive_failures[agent],
        )
        write_audit_entry(
            agent, signal_id, f"{agent}_dispatch_failed", trace_id, {"reason": str(exc)}
        )
        if _consecutive_failures[agent] >= _HALT_THRESHOLD:
            await halt(f"{_HALT_THRESHOLD} consecutive dispatch failures for agent={agent}: {exc}")
            logger.error("orchestrator_halted", agent=agent, reason=str(exc))
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestrator_dispatch.py -v`
Expected: PASS, all tests including the 3 new ones.

- [ ] **Step 9: Make the manual-ingest endpoint respect the halt flag**

In `pulseguard/gateway/routes.py`, modify `ingest_signal` (around line 163) to check the halt flag first. Find the function body's start and add, as its first statement:
```python
    from pulseguard.orchestrator.halt import is_halted

    if await is_halted():
        raise HTTPException(
            status_code=503,
            detail="PulseGuard is halted pending human review — see GET /api/v1/admin/halt",
        )
```

- [ ] **Step 10: Add admin endpoints to view and clear the halt**

Add to `pulseguard/gateway/routes.py`, after the existing `# ── Infrastructure endpoints ──` section (after `orchestrator_status`):
```python
@router.get("/admin/halt", dependencies=[Depends(require_api_key)])
async def get_halt_status() -> dict[str, Any]:
    from pulseguard.orchestrator.halt import is_halted
    from pulseguard.redis_client import get_async_redis

    if not await is_halted():
        return {"halted": False}
    redis = get_async_redis()
    raw = await redis.get("pulseguard:halted")
    return {"halted": True, "detail": json.loads(raw) if raw else None}


@router.post("/admin/halt/clear", dependencies=[Depends(require_api_key)])
async def clear_halt_endpoint() -> dict[str, Any]:
    from pulseguard.orchestrator.halt import clear_halt

    await clear_halt()
    logger.warning("orchestrator_halt_cleared_by_human")
    return {"halted": False}
```

- [ ] **Step 11: Write endpoint tests**

Add to `tests/unit/test_gateway.py`:
```python
class TestHaltEndpoints:
    @pytest.mark.asyncio
    async def test_get_halt_status_when_not_halted(self):
        from pulseguard.gateway.routes import get_halt_status

        with patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=False)):
            result = await get_halt_status()
        assert result == {"halted": False}

    @pytest.mark.asyncio
    async def test_clear_halt_endpoint_calls_clear_halt(self):
        from pulseguard.gateway.routes import clear_halt_endpoint

        with patch("pulseguard.orchestrator.halt.clear_halt", AsyncMock()) as mock_clear:
            result = await clear_halt_endpoint()
        mock_clear.assert_awaited_once()
        assert result == {"halted": False}
```

- [ ] **Step 12: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 13: Commit**

```bash
git add pulseguard/orchestrator/halt.py pulseguard/orchestrator/graph.py pulseguard/gateway/routes.py tests/unit/test_halt.py tests/unit/test_orchestrator_dispatch.py tests/unit/test_gateway.py
git commit -m "Add strict halt-on-failure: 3 consecutive dispatch failures stop the pipeline"
```

---

## Task 5: `PendingDraft` model and its Redis-backed read/write MCP tools

**Files:**
- Create: `pulseguard/models/drafts.py`
- Modify: `pulseguard/mcp_servers/output_mcp.py`
- Test: `tests/unit/test_mcp_tools.py` (extend)

**Interfaces:**
- Produces: `class PendingDraft(BaseModel)` from `pulseguard.models.drafts` — consumed by Task 6 (Resolver writes one) and Task 8 (gateway reads/updates them).
- Produces: `async def write_pending_draft(draft: dict) -> dict`, `async def list_pending_drafts(status: str | None = None) -> dict`, `async def update_draft_status(signal_id: str, status: str) -> dict` from `output_mcp.py` — consumed by Task 6 and Task 8.

- [ ] **Step 1: Create `pulseguard/models/drafts.py`**

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PendingDraft(BaseModel):
    """A drafted response awaiting human review — the copilot's core unit.
    Written for every signal that reaches a draft, whether Resolver judged
    it high-confidence or not; confidence affects queue priority, never
    whether a human sees it (spec §9 — this product never auto-sends)."""

    signal_id: str
    carrier: str
    category: str
    severity: str | None = None
    source_platform: str
    source_url: str
    draft_text: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    status: Literal["pending", "approved", "rejected"] = "pending"
    screen_flag: str | None = None  # set by Task 7's output screening, None means it passed
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    published_result: dict | None = None  # set by Task 10 once actually posted
```

- [ ] **Step 2: Write the failing test**

```python
# Add to tests/unit/test_mcp_tools.py
def _sample_pending_draft() -> dict:
    return dict(
        signal_id="sig-draft-001",
        carrier="verizon",
        category="Billing dispute",
        severity="P2",
        source_platform="x",
        source_url="https://x.com/i/web/status/sig-draft-001",
        draft_text="Hi! I'm sorry about the billing confusion — I've credited the extra charge.",
        confidence_score=0.88,
        created_at=_now_iso(),
    )


class TestDraftQueue:
    @pytest.mark.asyncio
    async def test_write_pending_draft_happy_path(self):
        from pulseguard.mcp_servers.output_mcp import write_pending_draft

        mock_redis = AsyncMock()
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            result = await write_pending_draft(_sample_pending_draft())

        assert result == {"written": True, "signal_id": "sig-draft-001"}
        mock_redis.hset.assert_awaited_once()
        args, _ = mock_redis.hset.call_args
        assert args[0] == "pulseguard:pending_drafts"
        assert args[1] == "sig-draft-001"

    @pytest.mark.asyncio
    async def test_list_pending_drafts_filters_by_status(self):
        from pulseguard.mcp_servers.output_mcp import list_pending_drafts

        pending = _sample_pending_draft()
        approved = _sample_pending_draft()
        approved["signal_id"] = "sig-draft-002"
        approved["status"] = "approved"

        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(
            return_value={
                "sig-draft-001": json.dumps(pending),
                "sig-draft-002": json.dumps(approved),
            }
        )
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            result = await list_pending_drafts(status="pending")

        assert result["count"] == 1
        assert result["drafts"][0]["signal_id"] == "sig-draft-001"

    @pytest.mark.asyncio
    async def test_list_pending_drafts_no_filter_returns_all(self):
        from pulseguard.mcp_servers.output_mcp import list_pending_drafts

        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(
            return_value={"sig-draft-001": json.dumps(_sample_pending_draft())}
        )
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            result = await list_pending_drafts()

        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_update_draft_status_happy_path(self):
        from pulseguard.mcp_servers.output_mcp import update_draft_status

        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=json.dumps(_sample_pending_draft()))
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            result = await update_draft_status("sig-draft-001", "approved")

        assert result["status"] == "approved"
        mock_redis.hset.assert_awaited_once()
        written = json.loads(mock_redis.hset.call_args.args[2])
        assert written["status"] == "approved"
        assert written["reviewed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_draft_status_not_found(self):
        from pulseguard.mcp_servers.output_mcp import update_draft_status

        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            result = await update_draft_status("sig-missing", "approved")

        assert result["code"] == "NOT_FOUND"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_mcp_tools.py::TestDraftQueue -v`
Expected: FAIL — the three new functions don't exist yet.

- [ ] **Step 4: Add the three MCP tools to `pulseguard/mcp_servers/output_mcp.py`**

Add near the top, with the other `_KEY` constants:
```python
_PENDING_DRAFTS_KEY = "pulseguard:pending_drafts"
```

Add the three functions (after `write_escalation`, matching the file's existing `@mcp.tool()` + `@tool_trace(...)` pattern):
```python
@mcp.tool()
@tool_trace("output", "write_pending_draft")
async def write_pending_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Persist a PendingDraft — the copilot's core review-queue unit."""
    try:
        pd = PendingDraft(**draft)
        redis = get_async_redis()
        await redis.hset(_PENDING_DRAFTS_KEY, pd.signal_id, pd.model_dump_json())
        return {"written": True, "signal_id": pd.signal_id}
    except Exception as exc:
        logger.error("write_pending_draft_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="WRITE_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "list_pending_drafts")
async def list_pending_drafts(status: str | None = None) -> dict[str, Any]:
    """List drafts in the review queue, optionally filtered by status."""
    try:
        redis = get_async_redis()
        all_raw = await redis.hgetall(_PENDING_DRAFTS_KEY)
        drafts = [json.loads(v) for v in all_raw.values()]
        if status:
            drafts = [d for d in drafts if d.get("status") == status]
        drafts.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return {"drafts": drafts, "count": len(drafts)}
    except Exception as exc:
        logger.error("list_pending_drafts_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="READ_ERROR").model_dump()


@mcp.tool()
@tool_trace("output", "update_draft_status")
async def update_draft_status(
    signal_id: str, status: str, reviewed_by: str | None = None
) -> dict[str, Any]:
    """Mark a PendingDraft approved or rejected. Does not publish anything —
    Task 10 wires the actual publish call separately, after this write."""
    try:
        redis = get_async_redis()
        raw = await redis.hget(_PENDING_DRAFTS_KEY, signal_id)
        if not raw:
            return ErrorResponse(error=f"Draft {signal_id} not found", code="NOT_FOUND").model_dump()
        pd = PendingDraft(**json.loads(raw))
        pd.status = status  # type: ignore[assignment]
        pd.reviewed_at = datetime.now(UTC)
        pd.reviewed_by = reviewed_by
        await redis.hset(_PENDING_DRAFTS_KEY, signal_id, pd.model_dump_json())
        return pd.model_dump(mode="json")
    except Exception as exc:
        logger.error("update_draft_status_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="WRITE_ERROR").model_dump()
```

Add the import near the top of the file, alongside the existing model imports:
```python
from pulseguard.models.drafts import PendingDraft
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_mcp_tools.py::TestDraftQueue -v`
Expected: PASS, all 5 tests.

- [ ] **Step 6: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add pulseguard/models/drafts.py pulseguard/mcp_servers/output_mcp.py tests/unit/test_mcp_tools.py
git commit -m "Add PendingDraft model and its write/list/update MCP tools"
```

---

## Task 6: Resolver writes a PendingDraft for every processed signal

**Files:**
- Modify: `pulseguard/agents/resolver.py:246-289` (`emit_resolved`)
- Test: `tests/unit/test_agents.py` (extend `TestResolverAgent`)

**Interfaces:**
- Consumes: `PendingDraft` (Task 5's model), `write_pending_draft` (Task 5's MCP tool).
- No change to `emit_resolved`'s existing behavior (`ResolutionRecord` write, escalation publish on `resolved=False`) — this task only adds a second write alongside the existing one.

This is the core behavioral change from the old "auto-resolve and file it" model to the new copilot model: every signal that reaches `emit_resolved`, whether high-confidence or not, now also produces a `PendingDraft` a human can see and act on in the review queue — not just the low-confidence ones that already went to Escalation.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_agents.py`'s `TestResolverAgent` class:
```python
    @pytest.mark.asyncio
    async def test_emit_resolved_writes_pending_draft_when_resolved(self):
        from pulseguard.agents.resolver import emit_resolved

        state = {
            "triage_report": {"signal_id": "sig-001", "category": "eSIM activation", "severity_score": 2},
            "validated_signal": {
                "detected_carrier": "verizon",
                "raw": {"source": "x", "url": "https://x.com/i/web/status/sig-001"},
            },
            "formatted_response": "Try Settings > Cellular > Add eSIM and rescan the QR code.",
            "draft_response": "",
            "confidence_score": 0.91,
            "resolved": True,
            "escalation_reason": None,
            "trace_id": "trace-001",
        }
        mock_write_res = AsyncMock(return_value={"written": True})
        mock_write_draft = AsyncMock(return_value={"written": True})
        with (
            patch("pulseguard.mcp_servers.output_mcp.write_resolution", mock_write_res),
            patch("pulseguard.mcp_servers.output_mcp.write_pending_draft", mock_write_draft),
        ):
            await emit_resolved(state)

        mock_write_draft.assert_awaited_once()
        written = mock_write_draft.call_args.args[0]
        assert written["signal_id"] == "sig-001"
        assert written["draft_text"] == "Try Settings > Cellular > Add eSIM and rescan the QR code."
        assert written["confidence_score"] == 0.91
        assert written["status"] == "pending"

    @pytest.mark.asyncio
    async def test_emit_resolved_writes_pending_draft_when_not_resolved(self):
        """Even a low-confidence signal that also triggers Escalation gets a
        PendingDraft — the simple review-and-send queue and the full
        Escalation brief are two independent surfaces, not exclusive."""
        from pulseguard.agents.resolver import emit_resolved

        state = {
            "triage_report": {"signal_id": "sig-002", "category": "Device troubleshooting", "severity_score": 3},
            "validated_signal": {
                "detected_carrier": "att",
                "raw": {"source": "reddit", "url": "https://reddit.com/r/att/sig-002"},
            },
            "formatted_response": "",
            "draft_response": "Best-effort draft: try a network reset in Settings.",
            "confidence_score": 0.4,
            "resolved": False,
            "escalation_reason": "Confidence 0.40 below threshold 0.85",
            "trace_id": "trace-002",
        }
        mock_write_draft = AsyncMock(return_value={"written": True})
        with (
            patch("pulseguard.mcp_servers.output_mcp.write_resolution", AsyncMock(return_value={"written": True})),
            patch("pulseguard.mcp_servers.output_mcp.write_pending_draft", mock_write_draft),
            patch("pulseguard.orchestrator.event_bus.publish_escalation_needed", AsyncMock()),
        ):
            await emit_resolved(state)

        written = mock_write_draft.call_args.args[0]
        assert written["draft_text"] == "Best-effort draft: try a network reset in Settings."
        assert written["confidence_score"] == 0.4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agents.py::TestResolverAgent::test_emit_resolved_writes_pending_draft_when_resolved -v`
Expected: FAIL — no `write_pending_draft` call is made yet.

- [ ] **Step 3: Add the PendingDraft write to `emit_resolved`**

In `pulseguard/agents/resolver.py`, insert this block into `emit_resolved` immediately after the existing `await write_resolution(signal_id, record.model_dump())` line (line 265) and before the `if not state.get("resolved"):` block:
```python
    from pulseguard.mcp_servers.output_mcp import write_pending_draft
    from pulseguard.models.drafts import PendingDraft

    pending_draft = PendingDraft(
        signal_id=signal_id,
        carrier=carrier,
        category=category,
        severity=state["triage_report"].get("severity_score") and str(state["triage_report"]["severity_score"]),
        source_platform=source,
        source_url=state["validated_signal"].get("raw", {}).get("url", ""),
        draft_text=record.draft_response,
        confidence_score=record.confidence_score,
        created_at=datetime.now(UTC),
    )
    await write_pending_draft(pending_draft.model_dump(mode="json"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_agents.py::TestResolverAgent -v`
Expected: PASS, all tests in the class including the 2 new ones.

- [ ] **Step 5: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add pulseguard/agents/resolver.py tests/unit/test_agents.py
git commit -m "Resolver writes a PendingDraft for every signal, not just escalated ones"
```

---

## Task 7: Draft-output policy screening

**Files:**
- Create: `pulseguard/security/output_screen.py`
- Modify: `pulseguard/agents/resolver.py` (wire the screen into `emit_resolved`)
- Test: `tests/unit/test_output_screen.py` (new)

**Interfaces:**
- Produces: `class ScreenResult(BaseModel)` with `passed: bool`, `reasons: list[str]`; `async def screen_draft(draft_text: str, category: str) -> ScreenResult` from `pulseguard.security.output_screen` — consumed by Task 6's `emit_resolved` (extended in this task) and surfaced to the reviewer via `PendingDraft.screen_flag`.

A failed screen never blocks the draft from reaching the human queue (spec §9 — this product never fully automates a decision away from a human) — it flags the draft so the reviewer sees the concern before approving.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_output_screen.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pulseguard.security.output_screen import screen_draft


class TestScreenDraft:
    @pytest.mark.asyncio
    async def test_clean_draft_passes(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps({"passed": True, "reasons": []})
        with patch(
            "pulseguard.security.output_screen._MODEL.ainvoke", AsyncMock(return_value=mock_response)
        ):
            result = await screen_draft("Sorry about the delay — I've issued a credit.", "Billing dispute")
        assert result.passed is True
        assert result.reasons == []

    @pytest.mark.asyncio
    async def test_flagged_draft_carries_reasons(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {"passed": False, "reasons": ["Promises a specific refund amount the KB does not authorize"]}
        )
        with patch(
            "pulseguard.security.output_screen._MODEL.ainvoke", AsyncMock(return_value=mock_response)
        ):
            result = await screen_draft("I'll refund you $500 right now!", "Billing dispute")
        assert result.passed is False
        assert "refund" in result.reasons[0]

    @pytest.mark.asyncio
    async def test_screening_failure_fails_open_with_a_flag(self):
        """If the screening call itself errors, the draft still reaches the
        queue (never silently dropped) but is flagged for extra scrutiny —
        the one place a screen failure is a signal, not a blocker."""
        with patch(
            "pulseguard.security.output_screen._MODEL.ainvoke",
            AsyncMock(side_effect=RuntimeError("model unavailable")),
        ):
            result = await screen_draft("Some draft text.", "General complaint / NPS risk")
        assert result.passed is False
        assert "screening unavailable" in result.reasons[0].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_output_screen.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pulseguard/security/output_screen.py`**

```python
"""Screens a drafted reply before it reaches the human review queue —
tone, discriminatory language, and unauthorized promises (e.g. a refund
amount the brand's KB doesn't sanction). A failed screen never blocks
the draft; it sets PendingDraft.screen_flag so the reviewer sees the
concern before clicking Approve & Send. This is deliberately a second,
independent check from Resolver's own confidence score — a high-
confidence draft can still say something the brand shouldn't send."""

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from pulseguard.logging_config import get_logger

logger = get_logger(__name__)

_MODEL = ChatAnthropic(model="claude-haiku-4-5", temperature=0, timeout=30, max_retries=1)

_SCREEN_SYSTEM = """You review a customer-support draft reply before a human sees it.

Flag it (passed=false) if it: promises a specific dollar amount, discount,
or account action the reply itself invents rather than reports; uses
discriminatory, dismissive, or unprofessional language; or makes a legal
or safety claim beyond a routine customer-service response.

Return ONLY a JSON object: {"passed": true|false, "reasons": ["<short reason>", ...]}
"reasons" must be empty when passed is true."""


class ScreenResult(BaseModel):
    passed: bool
    reasons: list[str] = []


async def screen_draft(draft_text: str, category: str) -> ScreenResult:
    try:
        messages = [
            SystemMessage(content=_SCREEN_SYSTEM),
            HumanMessage(content=f"Category: {category}\n\nDraft reply:\n{draft_text}"),
        ]
        response = await _MODEL.ainvoke(messages)
        parsed = json.loads(str(response.content))
        return ScreenResult(**parsed)
    except Exception as exc:
        logger.error("output_screen_error", error=str(exc))
        return ScreenResult(passed=False, reasons=[f"Screening unavailable: {exc}"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_output_screen.py -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Wire the screen into `emit_resolved` and add `screen_flag` to the `PendingDraft` write**

In `pulseguard/agents/resolver.py`, in the block added by Task 6, insert the screen call before constructing `pending_draft` and pass its result through:
```python
    from pulseguard.security.output_screen import screen_draft

    screen_result = await screen_draft(record.draft_response, category)

    pending_draft = PendingDraft(
        signal_id=signal_id,
        carrier=carrier,
        category=category,
        severity=state["triage_report"].get("severity_score") and str(state["triage_report"]["severity_score"]),
        source_platform=source,
        source_url=state["validated_signal"].get("raw", {}).get("url", ""),
        draft_text=record.draft_response,
        confidence_score=record.confidence_score,
        screen_flag="; ".join(screen_result.reasons) if not screen_result.passed else None,
        created_at=datetime.now(UTC),
    )
```

- [ ] **Step 6: Update Task 6's tests to account for the new screening call**

In both tests added in Task 6 (`test_emit_resolved_writes_pending_draft_when_resolved` and `..._when_not_resolved`), add a patch for the screen so the test doesn't make a real LLM call:
```python
        with (
            patch("pulseguard.mcp_servers.output_mcp.write_resolution", mock_write_res),
            patch("pulseguard.mcp_servers.output_mcp.write_pending_draft", mock_write_draft),
            patch(
                "pulseguard.agents.resolver.screen_draft",
                AsyncMock(return_value=ScreenResult(passed=True, reasons=[])),
            ),
        ):
```
(Add `from pulseguard.security.output_screen import ScreenResult` to the test file's imports, and add the matching third `patch(...)` context manager to the second test too.)

- [ ] **Step 7: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add pulseguard/security/output_screen.py pulseguard/agents/resolver.py tests/unit/test_output_screen.py tests/unit/test_agents.py
git commit -m "Add draft-output policy screening, surfaced as a flag not a block"
```

---

## Task 8: Gateway endpoints — list, approve, reject drafts

**Files:**
- Modify: `pulseguard/gateway/routes.py`
- Test: `tests/unit/test_gateway.py` (extend)

**Interfaces:**
- Produces: `GET /api/v1/drafts?status=`, `POST /api/v1/drafts/{signal_id}/approve`, `POST /api/v1/drafts/{signal_id}/reject` — the approve endpoint's actual publish call is added in Task 10, not this task (this task marks status only, so it's independently testable first).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_gateway.py`:
```python
class TestDraftEndpoints:
    @pytest.mark.asyncio
    async def test_list_drafts_delegates_to_mcp_tool(self):
        from pulseguard.gateway.routes import list_drafts

        mock_list = AsyncMock(return_value={"drafts": [], "count": 0})
        with patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list):
            result = await list_drafts(status="pending")

        mock_list.assert_awaited_once_with(status="pending")
        assert result == {"drafts": [], "count": 0}

    @pytest.mark.asyncio
    async def test_reject_draft_marks_status(self):
        from pulseguard.gateway.routes import DraftReviewRequest, reject_draft

        mock_update = AsyncMock(return_value={"signal_id": "sig-1", "status": "rejected"})
        with patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update):
            result = await reject_draft("sig-1", DraftReviewRequest(reviewed_by="vinoth"))

        mock_update.assert_awaited_once_with("sig-1", "rejected", reviewed_by="vinoth")
        assert result["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_draft_not_found_raises_404(self):
        from pulseguard.gateway.routes import DraftReviewRequest, reject_draft

        mock_update = AsyncMock(return_value={"error": "Draft sig-missing not found", "code": "NOT_FOUND"})
        with patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update):
            with pytest.raises(HTTPException) as exc:
                await reject_draft("sig-missing", DraftReviewRequest(reviewed_by="vinoth"))
        assert exc.value.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gateway.py::TestDraftEndpoints -v`
Expected: FAIL — none of `list_drafts`/`reject_draft`/`DraftReviewRequest` exist yet.

- [ ] **Step 3: Add the request model and endpoints to `pulseguard/gateway/routes.py`**

Add near `AckRequest` (around line 155):
```python
class DraftReviewRequest(BaseModel):
    reviewed_by: str
```

Add a new section after the existing `# ── Infrastructure endpoints ──` block's admin endpoints (from Task 4):
```python
# ── Draft review queue endpoints ────────────────────────────────────────────


@router.get("/drafts", dependencies=[Depends(require_api_key)])
async def list_drafts(status: str | None = Query(default=None)) -> dict[str, Any]:
    from pulseguard.mcp_servers.output_mcp import list_pending_drafts

    return await list_pending_drafts(status=status)


@router.post("/drafts/{signal_id}/reject", dependencies=[Depends(require_api_key)])
async def reject_draft(signal_id: str, req: DraftReviewRequest) -> dict[str, Any]:
    from pulseguard.mcp_servers.output_mcp import update_draft_status

    result = await update_draft_status(signal_id, "rejected", reviewed_by=req.reviewed_by)
    if result.get("code") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=result["error"])
    return result
```

(The `/approve` endpoint is added in Task 10, once the X publisher it needs to call exists — adding it here with no publisher behind it would leave a step that claims to "approve and send" but doesn't actually send anything.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_gateway.py::TestDraftEndpoints -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add pulseguard/gateway/routes.py tests/unit/test_gateway.py
git commit -m "Add draft list/reject endpoints (approve lands in Task 10 with the publisher)"
```

---

## Task 9: X reply publisher

**Files:**
- Create: `pulseguard/publishers/__init__.py`
- Create: `pulseguard/publishers/x_publisher.py`
- Modify: `pulseguard/config.py`
- Test: `tests/unit/test_publishers.py` (new)

**Interfaces:**
- Produces: `async def post_reply(in_reply_to_tweet_id: str, text: str) -> dict[str, Any]` from `pulseguard.publishers.x_publisher` — consumed by Task 10's approve endpoint.

**Important credential distinction:** the existing `XAdapter` (`pulseguard/adapters/x_adapter.py`) uses `settings.x_bearer_token` — an app-only Bearer token, valid for read-only search, but X's API rejects it for tweet creation. Posting a reply requires **OAuth 1.0a user-context credentials** (the account's own API key/secret + access token/secret) or OAuth 2.0 user-context — this task adds the OAuth 1.0a path since it's the simpler single-account credential model appropriate for Phase 0's single-tenant pilot deployment.

- [ ] **Step 1: Add publisher credentials to `pulseguard/config.py`**

Add after the `# X / Twitter` block:
```python
    # X publishing — separate, user-context OAuth 1.0a credentials from
    # x_bearer_token above (that one is app-only/read-only search; posting
    # a reply requires the connected account's own signing credentials).
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_publishers.py
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from pulseguard.publishers.x_publisher import PublishError, post_reply


class TestXPublisher:
    @pytest.mark.asyncio
    async def test_posts_reply_with_correct_payload(self):
        with (
            patch("pulseguard.publishers.x_publisher.settings.x_api_key", "key"),
            patch("pulseguard.publishers.x_publisher.settings.x_api_secret", "secret"),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token", "token"),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token_secret", "token-secret"),
            respx.mock,
        ):
            route = respx.post("https://api.twitter.com/2/tweets").mock(
                return_value=httpx.Response(201, json={"data": {"id": "999", "text": "reply text"}})
            )
            result = await post_reply(in_reply_to_tweet_id="123", text="reply text")

        assert result == {"posted": True, "tweet_id": "999"}
        sent = route.calls[0].request
        import json as _json

        body = _json.loads(sent.content)
        assert body["text"] == "reply text"
        assert body["reply"]["in_reply_to_tweet_id"] == "123"

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_publish_error(self):
        with (
            patch("pulseguard.publishers.x_publisher.settings.x_api_key", ""),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token", ""),
        ):
            with pytest.raises(PublishError, match="not configured"):
                await post_reply(in_reply_to_tweet_id="123", text="reply text")

    @pytest.mark.asyncio
    async def test_api_error_raises_publish_error(self):
        with (
            patch("pulseguard.publishers.x_publisher.settings.x_api_key", "key"),
            patch("pulseguard.publishers.x_publisher.settings.x_api_secret", "secret"),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token", "token"),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token_secret", "token-secret"),
            respx.mock,
        ):
            respx.post("https://api.twitter.com/2/tweets").mock(
                return_value=httpx.Response(403, json={"detail": "Forbidden"})
            )
            with pytest.raises(PublishError):
                await post_reply(in_reply_to_tweet_id="123", text="reply text")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_publishers.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Add `requests-oauthlib` for OAuth 1.0a signing**

X API v2's tweet-creation endpoint requires OAuth 1.0a request signing, which `httpx` doesn't do natively. Add the dependency:
```bash
cd pulseguard-ai
uv add requests-oauthlib
```

- [ ] **Step 5: Implement `pulseguard/publishers/__init__.py`**

```python
```
(empty — marks the package)

- [ ] **Step 6: Implement `pulseguard/publishers/x_publisher.py`**

```python
"""Publishes an approved draft reply back to X. Requires OAuth 1.0a
user-context credentials (distinct from XAdapter's read-only app-only
bearer token) — see config.py's x_api_key/x_api_secret/x_access_token/
x_access_token_secret. Single-account credentials, matching Phase 0's
single-tenant-per-deployment scope (spec §15); per-tenant OAuth is a
Phase 2 concern once multi-tenancy exists."""

from typing import Any

import httpx
from requests_oauthlib import OAuth1

from pulseguard.config import settings
from pulseguard.logging_config import get_logger

logger = get_logger(__name__)

_TWEETS_URL = "https://api.twitter.com/2/tweets"


class PublishError(Exception):
    """Raised when a reply could not be published — credentials missing,
    or the platform API rejected the request."""


def _oauth1_auth() -> OAuth1:
    return OAuth1(
        settings.x_api_key,
        client_secret=settings.x_api_secret,
        resource_owner_key=settings.x_access_token,
        resource_owner_secret=settings.x_access_token_secret,
    )


async def post_reply(in_reply_to_tweet_id: str, text: str) -> dict[str, Any]:
    if not (
        settings.x_api_key
        and settings.x_api_secret
        and settings.x_access_token
        and settings.x_access_token_secret
    ):
        raise PublishError("X publishing credentials not configured")

    auth = _oauth1_auth()
    headers = auth(
        httpx.Request("POST", _TWEETS_URL, json={"text": text}).headers
    )  # placeholder to satisfy type checkers; real signing happens via httpx's auth= below

    payload = {"text": text, "reply": {"in_reply_to_tweet_id": in_reply_to_tweet_id}}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(_TWEETS_URL, json=payload, auth=auth)
        if resp.status_code >= 400:
            raise PublishError(f"X API error {resp.status_code}: {resp.text}")
        data = resp.json()

    tweet_id = data.get("data", {}).get("id")
    logger.info("x_reply_posted", in_reply_to=in_reply_to_tweet_id, tweet_id=tweet_id)
    return {"posted": True, "tweet_id": tweet_id}
```

Note on the `headers = auth(...)` line above: `httpx.AsyncClient.post(..., auth=auth)` already applies an `OAuth1` auth object correctly per-request (httpx supports any callable/`httpx.Auth`-compatible object, and `requests_oauthlib.OAuth1` implements the interface `httpx` expects) — remove the placeholder `headers = auth(...)` line entirely, it was scaffolding only; the `auth=auth` kwarg on the `client.post(...)` call is what actually signs the request. Delete that line before running the tests in the next step.

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_publishers.py -v`
Expected: PASS, all 3 tests.

- [ ] **Step 8: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add pulseguard/publishers/ pulseguard/config.py pyproject.toml uv.lock tests/unit/test_publishers.py
git commit -m "Add X reply publisher (OAuth 1.0a user-context, single-account for Phase 0)"
```

---

## Task 10: Wire the publisher into a real Approve & Send endpoint

**Files:**
- Modify: `pulseguard/gateway/routes.py`
- Test: `tests/unit/test_gateway.py` (extend `TestDraftEndpoints`)

**Interfaces:**
- Produces: `POST /api/v1/drafts/{signal_id}/approve` — the one endpoint in this entire plan that causes something to actually post publicly, and only ever as a direct result of an explicit human action.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_gateway.py`'s `TestDraftEndpoints`:
```python
    @pytest.mark.asyncio
    async def test_approve_draft_publishes_and_marks_approved(self):
        from pulseguard.gateway.routes import DraftReviewRequest, approve_draft

        draft = {
            "signal_id": "sig-1",
            "carrier": "verizon",
            "category": "eSIM activation",
            "source_platform": "x",
            "source_url": "https://x.com/i/web/status/999",
            "draft_text": "Try Settings > Cellular > Add eSIM.",
            "confidence_score": 0.9,
            "status": "pending",
            "created_at": "2026-09-07T00:00:00+00:00",
        }
        mock_list = AsyncMock(return_value={"drafts": [draft], "count": 1})
        mock_publish = AsyncMock(return_value={"posted": True, "tweet_id": "999"})
        mock_update = AsyncMock(return_value={**draft, "status": "approved"})

        with (
            patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list),
            patch("pulseguard.publishers.x_publisher.post_reply", mock_publish),
            patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update),
        ):
            result = await approve_draft("sig-1", DraftReviewRequest(reviewed_by="vinoth"))

        mock_publish.assert_awaited_once_with(in_reply_to_tweet_id="999", text="Try Settings > Cellular > Add eSIM.")
        assert result["status"] == "approved"

    @pytest.mark.asyncio
    async def test_approve_draft_not_found_raises_404(self):
        from pulseguard.gateway.routes import DraftReviewRequest, approve_draft

        mock_list = AsyncMock(return_value={"drafts": [], "count": 0})
        with patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list):
            with pytest.raises(HTTPException) as exc:
                await approve_draft("sig-missing", DraftReviewRequest(reviewed_by="vinoth"))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_draft_publish_failure_returns_502_and_leaves_draft_pending(self):
        from pulseguard.gateway.routes import DraftReviewRequest, approve_draft
        from pulseguard.publishers.x_publisher import PublishError

        draft = {
            "signal_id": "sig-1",
            "source_platform": "x",
            "source_url": "https://x.com/i/web/status/999",
            "draft_text": "draft",
            "status": "pending",
        }
        mock_list = AsyncMock(return_value={"drafts": [draft], "count": 1})
        mock_publish = AsyncMock(side_effect=PublishError("X API error 403"))
        mock_update = AsyncMock()

        with (
            patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list),
            patch("pulseguard.publishers.x_publisher.post_reply", mock_publish),
            patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update),
        ):
            with pytest.raises(HTTPException) as exc:
                await approve_draft("sig-1", DraftReviewRequest(reviewed_by="vinoth"))

        assert exc.value.status_code == 502
        mock_update.assert_not_awaited()  # never marked approved if the publish itself failed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gateway.py::TestDraftEndpoints -v`
Expected: FAIL — `approve_draft` doesn't exist yet.

- [ ] **Step 3: Extract the tweet ID from `source_url` and implement `approve_draft`**

Add a small helper and the endpoint to `pulseguard/gateway/routes.py`, right after `reject_draft`:
```python
def _extract_x_tweet_id(source_url: str) -> str | None:
    # https://x.com/i/web/status/<id> — the id is the last path segment.
    if "/status/" not in source_url:
        return None
    return source_url.rstrip("/").rsplit("/", 1)[-1]


@router.post("/drafts/{signal_id}/approve", dependencies=[Depends(require_api_key)])
async def approve_draft(signal_id: str, req: DraftReviewRequest) -> dict[str, Any]:
    from pulseguard.mcp_servers.output_mcp import list_pending_drafts, update_draft_status
    from pulseguard.publishers.x_publisher import PublishError, post_reply

    listing = await list_pending_drafts()
    draft = next((d for d in listing["drafts"] if d["signal_id"] == signal_id), None)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Draft {signal_id} not found")

    if draft["source_platform"] == "x":
        tweet_id = _extract_x_tweet_id(draft["source_url"])
        if not tweet_id:
            raise HTTPException(status_code=422, detail="Could not determine tweet id to reply to")
        try:
            await post_reply(in_reply_to_tweet_id=tweet_id, text=draft["draft_text"])
        except PublishError as exc:
            logger.error("draft_publish_failed", signal_id=signal_id, error=str(exc))
            raise HTTPException(status_code=502, detail=f"Publish failed: {exc}") from exc
    else:
        raise HTTPException(
            status_code=422, detail=f"No publisher available for source '{draft['source_platform']}'"
        )

    return await update_draft_status(signal_id, "approved", reviewed_by=req.reviewed_by)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_gateway.py::TestDraftEndpoints -v`
Expected: PASS, all tests including the 3 new ones.

- [ ] **Step 5: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add pulseguard/gateway/routes.py tests/unit/test_gateway.py
git commit -m "Wire X publisher into a real Approve & Send endpoint"
```

---

## Task 11: Minimal eval set with a CI regression gate

**Files:**
- Create: `tests/fixtures/evals/eval_cases.json`
- Create: `tests/evals/test_resolver_quality.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- No production interfaces — this is a test-only addition, but it is a *required, blocking* CI job per spec §12/§13, not an optional nightly check.

- [ ] **Step 1: Create the eval fixture set**

```json
[
  {
    "id": "eval-esim-clear",
    "category": "eSIM activation",
    "carrier": "verizon",
    "content": "eSIM won't activate, tried scanning the QR code 3 times, please help",
    "rubric": "Draft must mention rescanning the QR code or an alternative eSIM setup path, stay under 280 characters if source is x, and must not promise a device replacement."
  },
  {
    "id": "eval-billing-overcharge",
    "category": "Billing dispute",
    "carrier": "verizon",
    "content": "Verizon overcharged me again this month, third time in a row, I want a refund or I'm switching carriers",
    "rubric": "Draft must acknowledge the specific complaint (repeat overcharge), must not promise an exact refund dollar amount, and must invite the customer to a resolution path (credit review, account check) rather than a generic apology only."
  },
  {
    "id": "eval-network-outage",
    "category": "Network outage (area-wide)",
    "carrier": "att",
    "content": "No signal at all in downtown for 2 days, is there an outage?",
    "rubric": "Draft must acknowledge a possible area outage and point to a status-check path, must not claim network status the draft can't actually know, and must not sound dismissive of a 2-day duration."
  },
  {
    "id": "eval-device-troubleshoot",
    "category": "Device troubleshooting",
    "carrier": "tmobile",
    "content": "My phone keeps dropping calls since the last update",
    "rubric": "Draft must suggest at least one concrete troubleshooting step (restart, network reset, or update check), must not blame the customer's device without evidence."
  },
  {
    "id": "eval-account-lock",
    "category": "Account access / lock",
    "carrier": "att",
    "content": "Locked out of my account, tried resetting password 5 times, nothing works",
    "rubric": "Draft must treat this as security-sensitive (no casual tone), must direct to an identity-verification path, must not ask the customer to share a password or PIN in the reply itself."
  }
]
```

- [ ] **Step 2: Write the eval runner as a real, assertable pytest test**

```python
# tests/evals/test_resolver_quality.py
"""Regression gate for Resolver's drafted output quality — required,
blocking CI per spec §12/§13, not an optional nightly check. Uses an
LLM-as-judge (Haiku, cheap and fast) to score each eval case's actual
draft against its rubric, and fails the build if the average score
drops below threshold. This is intentionally a real assertion, not a
report — a build that regresses draft quality should not merge, the
same way a build that fails a unit test should not merge."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from pulseguard.models.signals import RawSignal, ValidatedSignal
from pulseguard.models.triage import TriageReport

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "evals" / "eval_cases.json"
_JUDGE = ChatAnthropic(model="claude-haiku-4-5", temperature=0, timeout=30, max_retries=1)
_SCORE_THRESHOLD = 3.5  # out of 5 — a build failing below this blocks merge


def _load_cases() -> list[dict]:
    return json.loads(_FIXTURES.read_text())


async def _judge_score(draft: str, rubric: str) -> float:
    prompt = (
        f"Rubric: {rubric}\n\nDraft reply to score:\n{draft}\n\n"
        "Score this draft 1-5 against the rubric (5 = fully satisfies it, "
        "1 = violates it). Return ONLY the number."
    )
    response = await _JUDGE.ainvoke(
        [SystemMessage(content="You score customer-support drafts against a rubric."), HumanMessage(content=prompt)]
    )
    return float(str(response.content).strip())


@pytest.mark.asyncio
async def test_resolver_draft_quality_meets_threshold():
    """This test makes real Anthropic API calls (both to draft and to judge)
    — it is deliberately excluded from the fast local loop and run as its
    own required CI job (see ci.yml) so PR authors aren't blocked by API
    latency on every local test run, but merges are still blocked on it."""
    from pulseguard.agents.resolver import draft_response

    cases = _load_cases()
    scores = []
    for case in cases:
        vs = ValidatedSignal(
            signal_id=case["id"],
            raw=RawSignal(
                signal_id=case["id"],
                source="x",
                source_id=case["id"],
                author_handle="hash-placeholder",
                content=case["content"],
                url=f"https://x.com/i/web/status/{case['id']}",
                posted_at="2026-01-01T00:00:00+00:00",
            ),
            detected_carrier=case["carrier"],
            is_valid=True,
            validity_reason="eval fixture",
            content_hash="eval-hash",
            sentinel_trace_id="eval-trace",
            validated_at="2026-01-01T00:00:00+00:00",
        )
        tr = TriageReport(
            signal_id=case["id"],
            category=case["category"],
            resolution_tier=0,
            severity_score=2,
            sentiment_score=-0.5,
            churn_risk=False,
            routing_decision="RESOLVER",
            routing_rationale="eval fixture",
            triage_trace_id="eval-trace",
            triaged_at="2026-01-01T00:00:00+00:00",
        )
        state = {
            "triage_report": tr.model_dump(),
            "validated_signal": vs.model_dump(),
            "kb_script": None,
            "draft_response": "",
            "trace_id": "eval-trace",
        }
        result = await draft_response(state)
        score = await _judge_score(result["draft_response"], case["rubric"])
        scores.append(score)

    average = sum(scores) / len(scores)
    assert average >= _SCORE_THRESHOLD, f"Resolver draft quality regressed: {average:.2f} < {_SCORE_THRESHOLD}"


@pytest.mark.asyncio
async def test_judge_correctly_penalizes_a_deliberately_bad_draft():
    """Sanity-checks the judge itself: if it can't tell a bad draft from a
    good one, the threshold assertion above is meaningless."""
    bad_draft = "idk, not my problem, figure it out yourself"
    rubric = "Draft must acknowledge the specific complaint and offer a concrete next step, professionally."
    score = await _judge_score(bad_draft, rubric)
    assert score <= 2.0, f"Judge failed to penalize an obviously bad draft (scored {score})"
```

- [ ] **Step 3: Run the eval locally to confirm it works end-to-end**

Run: `uv run pytest tests/evals/test_resolver_quality.py -v` (requires a real `ANTHROPIC_API_KEY` in `.env` — this is the one test file in the repo that makes real API calls by design)
Expected: PASS. If the quality test fails, that's real signal about Resolver's actual draft quality — investigate the prompt in `resolver.py`, don't lower `_SCORE_THRESHOLD` to make the failure go away.

- [ ] **Step 4: Add the eval job to CI as a separate, required job**

Modify `.github/workflows/ci.yml` — add a new job alongside the existing `verify` job (evals need a real API key as a repo secret, so they run as their own job, not folded into `verify`'s `pytest tests/ -v` which must stay runnable with no secrets for contributors without one):
```yaml
  evals:
    runs-on: ubuntu-latest
    needs: verify
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Resolver draft-quality regression gate
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: uv run pytest tests/evals/ -v
```

Also add `tests/evals/` to the existing `verify` job's exclusion so its real-API test isn't accidentally picked up there too — change the `Unit + integration tests` step to:
```yaml
      - name: Unit + integration tests
        run: uv run pytest tests/ -v --ignore=tests/evals
```

- [ ] **Step 5: Run static checks on the new test file**

Run: `uv run ruff check tests/evals/ && uv run mypy pulseguard/` (the eval test file itself is test code, not part of the `mypy --strict` package scope, matching how the rest of `tests/` is already excluded from that check)
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/evals/ tests/evals/ .github/workflows/ci.yml
git commit -m "Add a minimal eval set with a required, blocking CI regression gate"
```

---

## Task 12: CI dependency and secret scanning

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- No code interfaces — this is CI configuration only.

- [ ] **Step 1: Add a dependency-vulnerability scan to the existing `verify` job**

In `.github/workflows/ci.yml`, add a new step to the `verify` job, after `Install dependencies` and before `Lint (ruff)`:
```yaml
      - name: Dependency vulnerability scan (pip-audit)
        run: uvx pip-audit
```

- [ ] **Step 2: Add a secret-leak scan as its own job**

Add a new job alongside `verify` and `evals`:
```yaml
  secrets-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Scan for leaked secrets (gitleaks)
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 3: Run `pip-audit` locally first to confirm it doesn't fail on this repo's current dependencies**

Run: `cd ~/project/pulseguard-ai && uvx pip-audit`
Expected: no known vulnerabilities reported for the current dependency set. If it reports a real vulnerability in an existing dependency, that is real signal to address (upgrade the affected package) before merging this task — do not suppress or ignore the finding to make this task easier to close.

- [ ] **Step 4: Push a throwaway branch to confirm gitleaks doesn't false-positive on this repo's history**

This can't be fully verified without pushing to GitHub Actions — note in the commit message that this should be confirmed on the first real CI run after merge, and any false-positive on existing committed content (e.g., a test fixture that looks like a credential, such as the `pulseguard_api_key` test values already in `tests/unit/test_gateway.py`) should be handled with a `.gitleaksignore` entry for that specific finding, not a broad exclusion.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "Add dependency vulnerability scanning and secret-leak scanning to CI"
```

---

## Task 13: Frontend — Draft review UI (Approve & Send / Reject)

**Files:**
- Create: `frontend/app/drafts/page.tsx`
- Create: `frontend/components/DraftQueue.tsx`
- Modify: `frontend/components/AppShell.tsx` (add nav item)
- Modify: `frontend/lib/types.ts` (add `PendingDraft` type)
- Modify: `frontend/lib/api.ts` or equivalent proxy usage (reuse existing `/api/proxy/[...path]` pattern — no new proxy code needed, it already forwards arbitrary paths to the gateway)
- Modify: `frontend/e2e/mock-backend.mjs` (add draft fixtures + endpoints)
- Create: `frontend/e2e/drafts.spec.ts`

**Interfaces:**
- Consumes: `GET /api/v1/drafts`, `POST /api/v1/drafts/{id}/approve`, `POST /api/v1/drafts/{id}/reject` (Tasks 8 and 10), proxied through the existing `/api/proxy/[...path]` route unchanged.

- [ ] **Step 1: Add the `PendingDraft` type to `frontend/lib/types.ts`**

Add near the other response-shape types:
```typescript
export interface PendingDraft {
  signal_id: string;
  carrier: string;
  category: string;
  severity: string | null;
  source_platform: SignalSource;
  source_url: string;
  draft_text: string;
  confidence_score: number;
  status: 'pending' | 'approved' | 'rejected';
  screen_flag: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export interface DraftsResponse {
  drafts: PendingDraft[];
  count: number;
}
```

- [ ] **Step 2: Add draft fixtures and endpoints to the e2e mock backend**

In `frontend/e2e/mock-backend.mjs`, add near the other fixture data (after `escalationBrief`):
```javascript
const pendingDrafts = [
  {
    signal_id: 'e2e-draft-0001',
    carrier: 'verizon',
    category: 'eSIM activation',
    severity: '2',
    source_platform: 'x',
    source_url: 'https://example.com/x/e2e-draft-0001',
    draft_text: 'To activate your eSIM: Settings > Cellular > Add eSIM, then rescan the QR code.',
    confidence_score: 0.91,
    status: 'pending',
    screen_flag: null,
    created_at: minutesAgo(3),
    reviewed_at: null,
    reviewed_by: null,
  },
];
```

Add route handling in the request switch (find where `/escalations/:id/ack` is handled and add alongside it):
```javascript
  if (pathname === '/drafts' && req.method === 'GET') {
    const status = searchParams.get('status');
    const filtered = status ? pendingDrafts.filter((d) => d.status === status) : pendingDrafts;
    return send(res, 200, { drafts: filtered, count: filtered.length });
  }

  const approveMatch = pathname.match(/^\/drafts\/([^/]+)\/approve$/);
  if (approveMatch && req.method === 'POST') {
    const draft = pendingDrafts.find((d) => d.signal_id === approveMatch[1]);
    if (!draft) return send(res, 404, { detail: 'not found' });
    draft.status = 'approved';
    return send(res, 200, draft);
  }

  const rejectMatch = pathname.match(/^\/drafts\/([^/]+)\/reject$/);
  if (rejectMatch && req.method === 'POST') {
    const draft = pendingDrafts.find((d) => d.signal_id === rejectMatch[1]);
    if (!draft) return send(res, 404, { detail: 'not found' });
    draft.status = 'rejected';
    return send(res, 200, draft);
  }
```

- [ ] **Step 3: Write the failing e2e test**

```typescript
// frontend/e2e/drafts.spec.ts
import { test, expect } from './fixtures';

test.describe('Draft review queue', () => {
  test('lists a pending draft and approves it', async ({ page }) => {
    await page.goto('/drafts');

    await expect(page.getByTestId('draft-card')).toHaveCount(1);
    await expect(page.getByText(/To activate your eSIM/)).toBeVisible();

    await page.getByRole('button', { name: 'Approve & Send' }).click();
    await expect(page.getByTestId('draft-card')).toHaveCount(0);
  });

  test('rejects a draft', async ({ page }) => {
    await page.goto('/drafts');
    await page.getByRole('button', { name: 'Reject' }).click();
    await expect(page.getByTestId('draft-card')).toHaveCount(0);
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd frontend && npx playwright test e2e/drafts.spec.ts`
Expected: FAIL — `/drafts` route doesn't exist yet (404).

- [ ] **Step 5: Implement `frontend/components/DraftQueue.tsx`**

```tsx
'use client';

import { useState } from 'react';
import type { DraftsResponse, PendingDraft } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { requestRefresh } from '@/lib/usePolling';
import { Button } from '@/components/ui/button';
import { Check, X, TriangleAlert } from 'lucide-react';

export default function DraftQueue() {
  const { data, loading } = usePolling<DraftsResponse>('/drafts?status=pending', 10000);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const drafts = data?.drafts ?? [];

  async function act(signalId: string, action: 'approve' | 'reject') {
    setActingOn(signalId);
    try {
      await fetch(`/api/proxy/drafts/${signalId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: 'vinoth@pulseguard.local' }),
      });
      requestRefresh();
    } finally {
      setActingOn(null);
    }
  }

  if (loading && drafts.length === 0) {
    return <div className="p-14 text-center text-muted">Loading drafts…</div>;
  }

  if (drafts.length === 0) {
    return <div data-testid="empty-state" className="p-14 text-center text-muted">Nothing waiting for review.</div>;
  }

  return (
    <div className="flex flex-col gap-3.5">
      {drafts.map((draft: PendingDraft) => (
        <div
          key={draft.signal_id}
          data-testid="draft-card"
          className="rounded-[13px] border border-border bg-surface p-4 shadow-[var(--shadow-card)]"
        >
          <div className="flex items-center justify-between">
            <div className="text-[12.5px] font-semibold">
              {draft.category} — {draft.carrier}
            </div>
            <div className="font-mono text-[11px] text-muted">
              {(draft.confidence_score * 100).toFixed(0)}% confidence
            </div>
          </div>
          {draft.screen_flag && (
            <div className="mt-2 flex items-center gap-1.5 rounded-[8px] bg-warning-tint px-2.5 py-1.5 text-[11.5px] text-warning">
              <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
              {draft.screen_flag}
            </div>
          )}
          <div className="mt-2.5 rounded-[10px] border border-border bg-bg px-3.5 py-2.5 text-[12.5px] leading-normal">
            {draft.draft_text}
          </div>
          <div className="mt-3 flex gap-2">
            <Button
              className="flex-1 bg-gradient-to-r from-brand to-jewel-violet text-white hover:opacity-90"
              disabled={actingOn === draft.signal_id}
              onClick={() => act(draft.signal_id, 'approve')}
            >
              <Check className="h-3.5 w-3.5" />
              Approve & Send
            </Button>
            <Button
              variant="outline"
              disabled={actingOn === draft.signal_id}
              onClick={() => act(draft.signal_id, 'reject')}
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Implement `frontend/app/drafts/page.tsx`**

```tsx
import DraftQueue from '@/components/DraftQueue';

export default function DraftsPage() {
  return (
    <div className="p-6">
      <div data-testid="page-title" className="font-display text-[23px] font-extrabold">
        Drafts
      </div>
      <div className="mt-1 text-[13px] text-muted">Every drafted reply waits here until you approve it.</div>
      <div className="mt-5">
        <DraftQueue />
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Add the nav item to `AppShell.tsx`**

In `frontend/components/AppShell.tsx`, add to the `NAV_ITEMS` array (import `FileCheck` from `lucide-react` alongside the existing icon imports):
```tsx
  { href: '/drafts', label: 'Drafts', icon: FileCheck },
```

- [ ] **Step 8: Run the e2e test to verify it passes**

Run: `cd frontend && npx playwright test e2e/drafts.spec.ts`
Expected: PASS, both tests.

- [ ] **Step 9: Run the full frontend verify suite**

Run: `cd frontend && npm run verify`
Expected: lint, typecheck, vitest, build, and the full Playwright suite (including the new file) all pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/app/drafts frontend/components/DraftQueue.tsx frontend/components/AppShell.tsx frontend/lib/types.ts frontend/e2e/mock-backend.mjs frontend/e2e/drafts.spec.ts
git commit -m "Add the Drafts review queue UI — Approve & Send / Reject"
```

---

## Task 14: Prompt caching on static system prompts

**Files:**
- Modify: `pulseguard/agents/sentinel.py:121` (`_VALIDITY_SYSTEM` call site)
- Modify: `pulseguard/agents/triage.py:113` (`_TRIAGE_SYSTEM` call site)
- Modify: `pulseguard/agents/resolver.py:150,186,235` (`_DRAFT_SYSTEM`, `_CONFIDENCE_SYSTEM`, `_FORMAT_SYSTEM` call sites)
- Modify: `pulseguard/agents/escalation.py:96` (`_BRIEF_SYSTEM` call site)
- Modify: `pulseguard/agents/llm_guard.py` (extract cache token details from the response)
- Modify: `pulseguard/security/budget_guard.py` (`record_spend` becomes cache-aware)
- Test: `tests/unit/test_budget_guard.py`, `tests/unit/test_agents.py::TestInvokeWithBudgetGuard` (extend both)

**Interfaces:**
- Modifies: `record_spend(model, input_tokens, output_tokens, cache_creation_tokens=0, cache_read_tokens=0) -> float` — the two new parameters are keyword-only-by-convention (not enforced) and default to 0, so every existing call site from Task 2/3 keeps working unchanged; only `llm_guard.py`'s call site is updated to pass real values.

Every agent's system prompt is a long, static string sent unchanged on every single call — exactly what Anthropic's prompt caching exists for. A cached prefix costs a one-time ~25% premium to write, then ~90% less than base input pricing on every subsequent read within the cache's lifetime — on a system prompt reused across every signal, this is a direct, compounding reduction in the spend BudgetGuard (Task 2) is already tracking, not a separate feature living alongside it.

**Known constraint, not asserted as fact — verify at implementation time:** Anthropic requires a minimum prefix length for a cache breakpoint to take effect (historically 1024 tokens for Sonnet/Opus-class models, 2048 for Haiku-class — confirm against Anthropic's current published minimums when implementing, since these are Anthropic-side values this codebase doesn't control). A system prompt shorter than the minimum is not an error — `cache_control` is simply a no-op on it — so this task is safe to apply uniformly across all four agents' system prompts even if one turns out to be too short to benefit.

- [ ] **Step 1: Write the failing test for cache-aware cost calculation**

Add to `tests/unit/test_budget_guard.py`'s `TestRecordSpend` class:
```python
    @pytest.mark.asyncio
    async def test_cache_write_and_read_priced_differently_from_base_input(self, monkeypatch):
        monkeypatch.setattr(
            "pulseguard.security.budget_guard.settings.model_pricing_per_million_tokens",
            "claude-haiku-4-5:1.00,5.00",
        )
        mock_redis = _mock_redis()
        with patch("pulseguard.security.budget_guard.get_async_redis", return_value=mock_redis):
            cost = await record_spend(
                "claude-haiku-4-5",
                input_tokens=0,
                output_tokens=0,
                cache_creation_tokens=1_000_000,
                cache_read_tokens=1_000_000,
            )
        # cache write: 1M tokens @ $1.00/M * 1.25 = $1.25
        # cache read:  1M tokens @ $1.00/M * 0.1  = $0.10
        assert cost == pytest.approx(1.35)

    @pytest.mark.asyncio
    async def test_zero_cache_tokens_matches_original_behavior(self, monkeypatch):
        monkeypatch.setattr(
            "pulseguard.security.budget_guard.settings.model_pricing_per_million_tokens",
            "claude-haiku-4-5:1.00,5.00",
        )
        mock_redis = _mock_redis()
        with patch("pulseguard.security.budget_guard.get_async_redis", return_value=mock_redis):
            cost = await record_spend("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=200_000)
        assert cost == pytest.approx(2.00)  # unchanged from Task 2's original test
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_budget_guard.py::TestRecordSpend -v`
Expected: FAIL — `record_spend()` doesn't accept `cache_creation_tokens`/`cache_read_tokens` yet.

- [ ] **Step 3: Extend `record_spend` in `pulseguard/security/budget_guard.py`**

Replace the existing `record_spend` function with:
```python
async def record_spend(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    pricing = settings.model_pricing_map
    if model not in pricing:
        logger.warning("budget_guard_unknown_model_pricing", model=model)
        return 0.0

    input_rate, output_rate = pricing[model]
    # Anthropic prompt caching: a cache write costs a 25% premium over base
    # input pricing (paid once, when the prefix is first cached); a cache
    # read costs 90% less than base input pricing (paid on every subsequent
    # call that hits the cached prefix). These are Anthropic's own standard
    # multipliers, not a PulseGuard-chosen approximation — confirm they
    # still match Anthropic's current published pricing at deploy time.
    cost = (
        (input_tokens / 1_000_000) * input_rate
        + (output_tokens / 1_000_000) * output_rate
        + (cache_creation_tokens / 1_000_000) * input_rate * 1.25
        + (cache_read_tokens / 1_000_000) * input_rate * 0.1
    )

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
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        cost_usd=round(cost, 6),
        recorded_at=datetime.now(UTC).isoformat(),
    )
    return cost
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_budget_guard.py -v`
Expected: PASS, all tests including the 2 new ones.

- [ ] **Step 5: Write the failing test for `llm_guard.py` extracting cache details**

Add to `tests/unit/test_agents.py`'s `TestInvokeWithBudgetGuard` class:
```python
    @pytest.mark.asyncio
    async def test_extracts_cache_token_details_when_present(self):
        from pulseguard.agents.llm_guard import invoke_with_budget_guard

        mock_response = MagicMock()
        mock_response.usage_metadata = {
            "input_tokens": 50,
            "output_tokens": 100,
            "input_token_details": {"cache_creation": 2000, "cache_read": 0},
        }
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with (
            patch("pulseguard.agents.llm_guard.check_budget", AsyncMock()),
            patch("pulseguard.agents.llm_guard.record_spend", AsyncMock(return_value=0.001)) as mock_record,
        ):
            await invoke_with_budget_guard(mock_model, [], model_name="claude-haiku-4-5")

        mock_record.assert_awaited_once_with(
            "claude-haiku-4-5",
            input_tokens=50,
            output_tokens=100,
            cache_creation_tokens=2000,
            cache_read_tokens=0,
        )

    @pytest.mark.asyncio
    async def test_missing_input_token_details_defaults_cache_fields_to_zero(self):
        from pulseguard.agents.llm_guard import invoke_with_budget_guard

        mock_response = MagicMock()
        mock_response.usage_metadata = {"input_tokens": 50, "output_tokens": 100}
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with (
            patch("pulseguard.agents.llm_guard.check_budget", AsyncMock()),
            patch("pulseguard.agents.llm_guard.record_spend", AsyncMock()) as mock_record,
        ):
            await invoke_with_budget_guard(mock_model, [], model_name="claude-haiku-4-5")

        mock_record.assert_awaited_once_with(
            "claude-haiku-4-5", input_tokens=50, output_tokens=100, cache_creation_tokens=0, cache_read_tokens=0
        )
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agents.py::TestInvokeWithBudgetGuard -v`
Expected: FAIL — `record_spend` is currently called without the two new keyword arguments.

- [ ] **Step 7: Update `invoke_with_budget_guard` in `pulseguard/agents/llm_guard.py`**

Replace the function body with:
```python
async def invoke_with_budget_guard(
    model: BaseChatModel, messages: list[BaseMessage], *, model_name: str
) -> Any:
    await check_budget()
    response = await model.ainvoke(messages)
    usage = getattr(response, "usage_metadata", None) or {}
    details = usage.get("input_token_details", {}) or {}
    await record_spend(
        model_name,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_creation_tokens=details.get("cache_creation", 0),
        cache_read_tokens=details.get("cache_read", 0),
    )
    return response
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_agents.py::TestInvokeWithBudgetGuard -v`
Expected: PASS, all 5 tests (3 from Task 3, 2 new).

- [ ] **Step 9: Add `cache_control` to every static system prompt call site**

In `pulseguard/agents/sentinel.py:121`, change:
```python
        SystemMessage(content=_VALIDITY_SYSTEM),
```
to:
```python
        SystemMessage(
            content=[{"type": "text", "text": _VALIDITY_SYSTEM, "cache_control": {"type": "ephemeral"}}]
        ),
```

Apply the identical transformation to the other four call sites:
- `pulseguard/agents/triage.py:113` — `_TRIAGE_SYSTEM`
- `pulseguard/agents/resolver.py:150` — `_DRAFT_SYSTEM`
- `pulseguard/agents/resolver.py:186` — `_CONFIDENCE_SYSTEM`
- `pulseguard/agents/resolver.py:235` — `_FORMAT_SYSTEM`
- `pulseguard/agents/escalation.py:96` — `_BRIEF_SYSTEM`

Each becomes `SystemMessage(content=[{"type": "text", "text": <the constant>, "cache_control": {"type": "ephemeral"}}])`, keeping every other line in each function unchanged.

- [ ] **Step 10: Run the full existing agent test suite to confirm the content-shape change doesn't break anything**

Run: `uv run pytest tests/unit/test_agents.py tests/integration/ -v`
Expected: all green — every existing test mocks `.ainvoke` at the model level and asserts on the mocked *response*, not on the exact shape of the `messages` argument passed in, so changing `SystemMessage(content=str)` to `SystemMessage(content=[{...}])` should not break any assertion. If any test does assert on message content shape, update that assertion to match the new list-of-blocks format rather than reverting the caching change.

- [ ] **Step 11: Manual verification note (not an automated test)**

Automated tests mock the LLM, so no unit test can prove caching actually reduces cost against the real Anthropic API. Before relying on this in a live pilot, run one real signal through the pipeline twice in quick succession with `LANGCHAIN_TRACING_V2=true` and a real `ANTHROPIC_API_KEY`, then check the LangSmith trace (or add a temporary log line reading `response.usage_metadata`) for the second call: `input_token_details.cache_read` should be greater than 0. If it reads 0 on the second call, the relevant system prompt is very likely below Anthropic's minimum cacheable prefix length (see this task's opening note) — that's an expected, non-broken outcome for a short prompt, not a bug to chase.

- [ ] **Step 12: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 13: Commit**

```bash
git add pulseguard/agents/sentinel.py pulseguard/agents/triage.py pulseguard/agents/resolver.py pulseguard/agents/escalation.py pulseguard/agents/llm_guard.py pulseguard/security/budget_guard.py tests/unit/test_budget_guard.py tests/unit/test_agents.py
git commit -m "Enable Anthropic prompt caching on static system prompts; make BudgetGuard cache-aware"
```

---

## Task 15: Structured decision logging (DecisionLogger)

**Files:**
- Create: `pulseguard/security/decision_log.py`
- Modify: `pulseguard/agents/sentinel.py` (`classify_validity` node)
- Modify: `pulseguard/agents/triage.py` (its category/severity/routing node)
- Modify: `pulseguard/agents/resolver.py:203-212` (`decide` node)
- Modify: `pulseguard/agents/escalation.py:132-149` (`assign_priority` node)
- Test: `tests/unit/test_decision_log.py` (new)

**Interfaces:**
- Produces: `class DecisionLogger` with `.log(decision_type, decision, reason, evidence=None, confidence=None, alternatives=None) -> None` and `.finalize() -> list[dict]` from `pulseguard.security.decision_log` — consumed by the four agent modifications below.

This closes the spec §10 gap flagged in the last review: `write_audit_entry` already logs that an action happened (a signal was resolved, an escalation was created), but not the reasoning behind the decision — the same distinction the founder's telecom-call-intelligence project already draws between an action log and a decision log. Every instrumentation point below already computes its own reasoning today (`validity_reason`, `routing_rationale`, `escalation_reason`) — this task doesn't invent new reasoning, it captures what's already computed into one structured, greppable, per-signal decision trail instead of leaving it scattered across separate Redis records.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_decision_log.py
import json
from pathlib import Path

from pulseguard.security.decision_log import DecisionLogger


class TestDecisionLogger:
    def test_log_and_finalize_returns_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "pulseguard.security.decision_log._DECISION_LOG_PATH", tmp_path / "decisions.jsonl"
        )
        dl = DecisionLogger("triage", "sig-001", "trace-001")
        dl.log(
            decision_type="routing_decision",
            decision="ESCALATION",
            reason="Billing dispute with churn risk routes direct to escalation",
            evidence={"category": "Billing dispute", "severity_score": 5, "churn_risk": True},
            confidence=0.9,
            alternatives=["RESOLVER"],
        )
        entries = dl.finalize()

        assert len(entries) == 1
        assert entries[0]["agent"] == "triage"
        assert entries[0]["signal_id"] == "sig-001"
        assert entries[0]["decision_type"] == "routing_decision"
        assert entries[0]["decision"] == "ESCALATION"
        assert entries[0]["alternatives"] == ["RESOLVER"]

    def test_finalize_writes_one_json_line_per_entry(self, tmp_path, monkeypatch):
        log_path = tmp_path / "decisions.jsonl"
        monkeypatch.setattr("pulseguard.security.decision_log._DECISION_LOG_PATH", log_path)
        dl = DecisionLogger("resolver", "sig-002", "trace-002")
        dl.log(decision_type="resolve_or_escalate", decision="resolved", reason="confidence 0.91 >= 0.85")
        dl.log(decision_type="resolve_or_escalate", decision="resolved", reason="second entry")
        dl.finalize()

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["decision"] == "resolved"

    def test_reason_truncated_to_500_chars(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "pulseguard.security.decision_log._DECISION_LOG_PATH", tmp_path / "decisions.jsonl"
        )
        dl = DecisionLogger("sentinel", "sig-003", "trace-003")
        dl.log(decision_type="validity_classification", decision="valid", reason="x" * 1000)
        entries = dl.finalize()
        assert len(entries[0]["reason"]) == 500

    def test_no_entries_writes_nothing(self, tmp_path, monkeypatch):
        log_path = tmp_path / "decisions.jsonl"
        monkeypatch.setattr("pulseguard.security.decision_log._DECISION_LOG_PATH", log_path)
        dl = DecisionLogger("escalation", "sig-004", "trace-004")
        entries = dl.finalize()
        assert entries == []
        assert not log_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_decision_log.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pulseguard/security/decision_log.py`**

```python
"""Structured decision traceability, distinct from write_audit_entry
(security/audit.py). write_audit_entry logs that an action happened — a
signal was resolved, an escalation was created. DecisionLogger logs the
*reasoning behind* a decision — why this category, why this routing, why
resolved instead of escalated — so "why did the AI decide this" is
answerable from one greppable log per signal, not by re-reading scattered
LLM output. Mirrors the DecisionLogger discipline already proven in a
sibling project (spec §10)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DECISION_LOG_PATH = Path(os.getenv("DECISION_LOG_PATH", "logs/decisions.jsonl"))


class DecisionLogger:
    def __init__(self, agent: str, signal_id: str, trace_id: str) -> None:
        self.agent = agent
        self.signal_id = signal_id
        self.trace_id = trace_id
        self._entries: list[dict[str, Any]] = []

    def log(
        self,
        decision_type: str,
        decision: str,
        reason: str,
        evidence: dict[str, Any] | None = None,
        confidence: float | None = None,
        alternatives: list[str] | None = None,
    ) -> None:
        self._entries.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "agent": self.agent,
                "signal_id": self.signal_id,
                "trace_id": self.trace_id,
                "decision_type": decision_type,
                "decision": decision,
                "reason": reason[:500],
                "evidence": evidence or {},
                "confidence": confidence,
                "alternatives": alternatives or [],
            }
        )

    def finalize(self) -> list[dict[str, Any]]:
        if not self._entries:
            return []
        _DECISION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_DECISION_LOG_PATH, "a", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(json.dumps(entry) + "\n")
        return self._entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_decision_log.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Instrument Sentinel's validity classification**

In `pulseguard/agents/sentinel.py`, find the `classify_validity` node (the function that sets `is_valid`/`validity_reason` on the state) and add, right before its `return {...}` statement:
```python
    from pulseguard.security.decision_log import DecisionLogger

    dl = DecisionLogger("sentinel", state["signal_id"], state.get("trace_id", ""))
    dl.log(
        decision_type="validity_classification",
        decision="valid" if is_valid else "invalid",
        reason=reason,
        evidence={"content_hash": state.get("content_hash", "")},
        alternatives=["valid", "invalid"],
    )
    dl.finalize()
```
(Use whatever the node's actual local variable names are for the computed validity boolean and reason string — do not rename them, wire the log call to reference the existing names.)

- [ ] **Step 6: Instrument Triage's routing decision**

In `pulseguard/agents/triage.py`, find the node that produces `routing_decision`/`routing_rationale` and add the equivalent block before its return:
```python
    from pulseguard.security.decision_log import DecisionLogger

    dl = DecisionLogger("triage", state["signal_id"], state.get("trace_id", ""))
    dl.log(
        decision_type="routing_decision",
        decision=routing_decision,
        reason=routing_rationale,
        evidence={
            "category": category,
            "severity_score": severity_score,
            "sentiment_score": sentiment_score,
            "churn_risk": churn_risk,
        },
        alternatives=["RESOLVER", "ESCALATION"],
    )
    dl.finalize()
```

- [ ] **Step 7: Instrument Resolver's `decide` node**

In `pulseguard/agents/resolver.py:203-212`, modify `decide` to log before returning:
```python
@node_trace("resolver", "decide")
async def decide(state: ResolverState) -> dict[str, Any]:
    from pulseguard.security.decision_log import DecisionLogger

    score = state.get("confidence_score", 0.0)
    dl = DecisionLogger("resolver", state["triage_report"].get("signal_id", "unknown"), state.get("trace_id", ""))
    if score >= _CONFIDENCE_THRESHOLD:
        logger.info("resolver_decided_resolve", score=score)
        dl.log(
            decision_type="resolve_or_escalate",
            decision="resolved",
            reason=f"Confidence {score:.2f} meets threshold {_CONFIDENCE_THRESHOLD}",
            evidence={"confidence_score": score, "threshold": _CONFIDENCE_THRESHOLD},
            confidence=score,
            alternatives=["escalate"],
        )
        dl.finalize()
        return {"resolved": True, "escalation_reason": None}
    else:
        reason = f"Confidence {score:.2f} below threshold {_CONFIDENCE_THRESHOLD}"
        logger.info("resolver_decided_escalate", score=score, reason=reason)
        dl.log(
            decision_type="resolve_or_escalate",
            decision="escalate",
            reason=reason,
            evidence={"confidence_score": score, "threshold": _CONFIDENCE_THRESHOLD},
            confidence=score,
            alternatives=["resolved"],
        )
        dl.finalize()
        return {"resolved": False, "escalation_reason": reason}
```

- [ ] **Step 8: Instrument Escalation's `assign_priority` node**

In `pulseguard/agents/escalation.py:132-149`, add the equivalent logging before `assign_priority`'s return, capturing whichever priority rule fired as `reason` and the P1/P2/P3 outcome as `decision`, with `alternatives=["P1", "P2", "P3"]` minus whichever was chosen.

- [ ] **Step 9: Write tests confirming each agent calls the logger**

Add one assertion per agent to the corresponding existing test in `tests/unit/test_agents.py` (e.g. in `TestResolverAgent::test_priority_assignment_rules`-equivalent or a new small test per agent), patching `pulseguard.security.decision_log.DecisionLogger` with a `MagicMock()` and asserting `.log` and `.finalize` were each called at least once when the node runs. Follow the existing patch-and-assert style already used throughout `test_agents.py` rather than introducing a new test pattern.

- [ ] **Step 10: Run full suite and static checks**

Run: `uv run ruff check . && uv run mypy pulseguard/ && uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 11: Commit**

```bash
git add pulseguard/security/decision_log.py pulseguard/agents/sentinel.py pulseguard/agents/triage.py pulseguard/agents/resolver.py pulseguard/agents/escalation.py tests/unit/test_decision_log.py tests/unit/test_agents.py
git commit -m "Add structured DecisionLogger — captures existing reasoning, not just actions"
```

---

## Post-plan: what's deliberately not in this plan

Per spec §15/§16 — do not add these without a fresh spec update first:
- Multi-tenancy (Workspace/Client Brand/Seats, Postgres) — Phase 2, gated on Phase 0/1 revenue validation.
- Google Business Profile or Reddit publish adapters — future work once X is proven in a real pilot.
- Any auto-send path that skips the approve endpoint — permanently out of scope per spec §9, not a Phase 0 limitation to lift later.
- The business-development tasks from spec §15 Phase 0 (discovery calls with named carriers, MVNE outreach) — those are Vinoth's own work, not something this implementation plan produces.
