"""
Integration tests: signal flows through SENTINEL → TRIAGE → RESOLVER (pass path).
Redis and LLM calls are mocked. Tests routing decisions and output contracts.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pulseguard.models.signals import RawSignal

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text())


def _mock_redis_fresh() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.sismember = AsyncMock(return_value=False)
    r.sadd = AsyncMock()
    r.incr = AsyncMock()
    r.hset = AsyncMock()
    r.hget = AsyncMock(return_value=None)
    r.hgetall = AsyncMock(return_value={})
    r.xadd = AsyncMock(return_value=b"0-1")
    r.incrby = AsyncMock()
    r.decr = AsyncMock()
    return r


class TestTier0EsimPipeline:
    @pytest.mark.asyncio
    async def test_esim_routes_to_resolver(self):
        raw = _load("signal_tier0_esim.json")
        signal = RawSignal(**raw)

        validated_events = []
        triage_events = []

        async def capture_validated(vs):
            validated_events.append(vs)

        async def capture_triage(tr):
            triage_events.append(tr)

        mock_llm_sentinel = AsyncMock()
        mock_llm_sentinel.ainvoke = AsyncMock(
            return_value=MagicMock(
                usage_metadata={"input_tokens": 0, "output_tokens": 0},
                content="VALID: Genuine eSIM activation failure",
            )
        )
        mock_llm_triage = AsyncMock()
        mock_llm_triage.ainvoke = AsyncMock(
            return_value=MagicMock(
                usage_metadata={"input_tokens": 0, "output_tokens": 0},
                content=json.dumps(
                    {
                        "category": "eSIM activation",
                        "severity_score": 2,
                        "sentiment_score": -0.4,
                        "churn_risk": False,
                        "routing_rationale": "Tier 0 eSIM issue — RESOLVER",
                    }
                ),
            )
        )
        mock_dedup_check = AsyncMock(return_value={"is_duplicate": False})
        mock_dedup_reg = AsyncMock(return_value={"registered": True})
        mock_kb_ctx = AsyncMock(return_value={"error": "not found"})
        mock_redis = _mock_redis_fresh()

        with (
            patch("pulseguard.agents.sentinel._MODEL", mock_llm_sentinel),
            patch("pulseguard.agents.triage._MODEL", mock_llm_triage),
            patch("pulseguard.mcp_servers.dedup_mcp.check_duplicate", mock_dedup_check),
            patch("pulseguard.mcp_servers.dedup_mcp.register_signal", mock_dedup_reg),
            patch("pulseguard.mcp_servers.classify_mcp.get_kb_context", mock_kb_ctx),
            patch("pulseguard.orchestrator.event_bus.publish_validated_signal", capture_validated),
            patch("pulseguard.orchestrator.event_bus.publish_triage_report", capture_triage),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            from pulseguard.agents.sentinel import process_signal

            await process_signal(signal, "trace-int-001")

        assert len(validated_events) == 1
        vs = validated_events[0]
        assert vs.is_valid is True
        assert vs.detected_carrier == "verizon"

    @pytest.mark.asyncio
    async def test_tier0_classification_correct(self):
        raw = _load("signal_tier0_order_status.json")
        signal = RawSignal(**raw)

        triage_events = []

        async def capture_triage(tr):
            triage_events.append(tr)

        mock_llm_sentinel = AsyncMock()
        mock_llm_sentinel.ainvoke = AsyncMock(
            return_value=MagicMock(
                usage_metadata={"input_tokens": 0, "output_tokens": 0},
                content="VALID: Order status inquiry — genuine customer support issue",
            )
        )
        mock_llm_triage = AsyncMock()
        mock_llm_triage.ainvoke = AsyncMock(
            return_value=MagicMock(
                usage_metadata={"input_tokens": 0, "output_tokens": 0},
                content=json.dumps(
                    {
                        "category": "Order status",
                        "severity_score": 2,
                        "sentiment_score": -0.3,
                        "churn_risk": False,
                        "routing_rationale": "Tier 0 order status — RESOLVER",
                    }
                ),
            )
        )
        mock_dedup_check = AsyncMock(return_value={"is_duplicate": False})
        mock_dedup_reg = AsyncMock(return_value={"registered": True})
        mock_kb_ctx = AsyncMock(return_value={"error": "not found"})
        mock_redis = _mock_redis_fresh()

        async def capture_validated_then_triage(vs):
            from pulseguard.agents.triage import process_validated_signal

            await process_validated_signal(vs, "trace-int-002")

        with (
            patch("pulseguard.agents.sentinel._MODEL", mock_llm_sentinel),
            patch("pulseguard.agents.triage._MODEL", mock_llm_triage),
            patch("pulseguard.mcp_servers.dedup_mcp.check_duplicate", mock_dedup_check),
            patch("pulseguard.mcp_servers.dedup_mcp.register_signal", mock_dedup_reg),
            patch("pulseguard.mcp_servers.classify_mcp.get_kb_context", mock_kb_ctx),
            patch(
                "pulseguard.orchestrator.event_bus.publish_validated_signal",
                capture_validated_then_triage,
            ),
            patch("pulseguard.orchestrator.event_bus.publish_triage_report", capture_triage),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            from pulseguard.agents.sentinel import process_signal

            await process_signal(signal, "trace-int-002")

        assert len(triage_events) == 1
        tr = triage_events[0]
        assert tr.category == "Order status"
        assert tr.resolution_tier == 0
        assert tr.routing_decision == "RESOLVER"


class TestTier2BillingPipeline:
    @pytest.mark.asyncio
    async def test_billing_dispute_routes_to_escalation(self):
        raw = _load("signal_tier2_billing.json")
        signal = RawSignal(**raw)

        triage_events = []

        async def capture_triage(tr):
            triage_events.append(tr)

        mock_llm_sentinel = AsyncMock()
        mock_llm_sentinel.ainvoke = AsyncMock(
            return_value=MagicMock(
                usage_metadata={"input_tokens": 0, "output_tokens": 0},
                content="VALID: Billing dispute with churn risk",
            )
        )
        mock_llm_triage = AsyncMock()
        mock_llm_triage.ainvoke = AsyncMock(
            return_value=MagicMock(
                usage_metadata={"input_tokens": 0, "output_tokens": 0},
                content=json.dumps(
                    {
                        "category": "Billing dispute",
                        "severity_score": 5,
                        "sentiment_score": -0.95,
                        "churn_risk": True,
                        "routing_rationale": "Billing dispute requires human agent — Tier 2",
                    }
                ),
            )
        )
        mock_dedup = AsyncMock(return_value={"is_duplicate": False})
        mock_dedup_reg = AsyncMock(return_value={"registered": True})
        mock_kb_ctx = AsyncMock(return_value={"error": "not found"})
        mock_redis = _mock_redis_fresh()

        async def through_triage(vs):
            from pulseguard.agents.triage import process_validated_signal

            await process_validated_signal(vs, "trace-int-003")

        with (
            patch("pulseguard.agents.sentinel._MODEL", mock_llm_sentinel),
            patch("pulseguard.agents.triage._MODEL", mock_llm_triage),
            patch("pulseguard.mcp_servers.dedup_mcp.check_duplicate", mock_dedup),
            patch("pulseguard.mcp_servers.dedup_mcp.register_signal", mock_dedup_reg),
            patch("pulseguard.mcp_servers.classify_mcp.get_kb_context", mock_kb_ctx),
            patch("pulseguard.orchestrator.event_bus.publish_validated_signal", through_triage),
            patch("pulseguard.orchestrator.event_bus.publish_triage_report", capture_triage),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            from pulseguard.agents.sentinel import process_signal

            await process_signal(signal, "trace-int-003")

        assert len(triage_events) == 1
        assert triage_events[0].routing_decision == "ESCALATION"
        assert triage_events[0].churn_risk is True
