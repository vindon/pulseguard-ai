"""
Phase 4 gate tests — each agent processes one fixture signal in isolation.
LLM calls and Redis/MCP calls are mocked to test agent graph logic only.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pulseguard.models.signals import RawSignal, ValidatedSignal
from pulseguard.models.triage import TriageReport

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text())


def _now() -> datetime:
    return datetime.now(UTC)


def _make_validated(raw_dict: dict, carrier: str = "verizon") -> ValidatedSignal:
    raw = RawSignal(**raw_dict)
    return ValidatedSignal(
        signal_id=raw.signal_id,
        raw=raw,
        detected_carrier=carrier,
        is_valid=True,
        validity_reason="Genuine telecom complaint",
        content_hash="abc123hash",
        sentinel_trace_id="trace-test-001",
        validated_at=_now(),
    )


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


def _make_triage(signal_id: str, category: str, tier: int, routing: str) -> TriageReport:
    return TriageReport(
        signal_id=signal_id,
        category=category,
        resolution_tier=tier,  # type: ignore[arg-type]
        severity_score=3,
        sentiment_score=-0.6,
        churn_risk=False,
        routing_decision=routing,  # type: ignore[arg-type]
        routing_rationale="Test routing",
        triage_trace_id="trace-triage-001",
        triaged_at=_now(),
    )


# ── SENTINEL ───────────────────────────────────────────────────────────────


class TestSentinelAgent:
    @pytest.mark.asyncio
    async def test_valid_signal_emitted(self):
        raw = _load_fixture("signal_tier0_esim.json")

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="VALID: Genuine eSIM activation issue with Verizon")
        )

        mock_dedup = AsyncMock(return_value={"is_duplicate": False})
        mock_register = AsyncMock(return_value={"registered": True})
        mock_publish = AsyncMock()
        mock_redis = _mock_redis_fresh()

        with (
            patch("pulseguard.agents.sentinel._MODEL", mock_llm),
            patch("pulseguard.agents.sentinel.process_signal.__wrapped__", None, create=True),
            patch("pulseguard.mcp_servers.dedup_mcp.check_duplicate", mock_dedup),
            patch("pulseguard.mcp_servers.dedup_mcp.register_signal", mock_register),
            patch("pulseguard.orchestrator.event_bus.publish_validated_signal", mock_publish),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            from pulseguard.agents.sentinel import (
                SentinelState,
                classify_validity,
                deduplicate,
                detect_carrier_node,
                emit_or_drop,
                validate_format,
            )

            state: SentinelState = {
                "raw_signal": raw,
                "is_valid": False,
                "validity_reason": "",
                "detected_carrier": "",
                "content_hash": "",
                "duplicate": False,
                "trace_id": "trace-001",
                "error": None,
            }
            state.update(await validate_format(state))
            state.update(await deduplicate(state))
            state.update(await detect_carrier_node(state))
            state.update(await classify_validity(state))
            await emit_or_drop(state)

        assert state["is_valid"] is True
        assert state["detected_carrier"] == "verizon"
        mock_publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_signal_dropped(self):
        raw = _load_fixture("signal_duplicate.json")

        mock_dedup = AsyncMock(return_value={"is_duplicate": True})
        mock_publish = AsyncMock()

        with (
            patch("pulseguard.mcp_servers.dedup_mcp.check_duplicate", mock_dedup),
            patch("pulseguard.orchestrator.event_bus.publish_validated_signal", mock_publish),
        ):
            from pulseguard.agents.sentinel import SentinelState, deduplicate, emit_or_drop

            state: SentinelState = {
                "raw_signal": raw,
                "is_valid": False,
                "validity_reason": "",
                "detected_carrier": "",
                "content_hash": "",
                "duplicate": False,
                "trace_id": "trace-002",
                "error": None,
            }
            state.update(await deduplicate(state))
            await emit_or_drop(state)

        assert state["duplicate"] is True
        mock_publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_spam_dropped(self):
        raw = _load_fixture("signal_invalid_spam.json")

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content="INVALID: Spam giveaway post, not a genuine support issue"
            )
        )
        mock_dedup = AsyncMock(return_value={"is_duplicate": False})
        mock_register = AsyncMock(return_value={"registered": True})
        mock_publish = AsyncMock()

        with (
            patch("pulseguard.agents.sentinel._MODEL", mock_llm),
            patch("pulseguard.mcp_servers.dedup_mcp.check_duplicate", mock_dedup),
            patch("pulseguard.mcp_servers.dedup_mcp.register_signal", mock_register),
            patch("pulseguard.orchestrator.event_bus.publish_validated_signal", mock_publish),
        ):
            from pulseguard.agents.sentinel import SentinelState, classify_validity, emit_or_drop

            state: SentinelState = {
                "raw_signal": raw,
                "is_valid": False,
                "validity_reason": "",
                "detected_carrier": "verizon",
                "content_hash": "somehash",
                "duplicate": False,
                "trace_id": "trace-003",
                "error": None,
            }
            state.update(await classify_validity(state))
            await emit_or_drop(state)

        assert state["is_valid"] is False
        mock_publish.assert_not_awaited()


# ── TRIAGE ─────────────────────────────────────────────────────────────────


class TestTriageAgent:
    @pytest.mark.asyncio
    async def test_tier0_routes_to_resolver(self):
        vs = _make_validated(_load_fixture("signal_tier0_esim.json"), carrier="verizon")

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "category": "eSIM activation",
                        "severity_score": 2,
                        "sentiment_score": -0.4,
                        "churn_risk": False,
                        "routing_rationale": "Tier 0 deterministic eSIM issue",
                    }
                )
            )
        )
        mock_publish = AsyncMock()
        mock_kb = AsyncMock(return_value={"error": "not found"})

        with (
            patch("pulseguard.agents.triage._MODEL", mock_llm),
            patch("pulseguard.orchestrator.event_bus.publish_triage_report", mock_publish),
            patch("pulseguard.mcp_servers.classify_mcp.get_kb_context", mock_kb),
        ):
            from pulseguard.agents.triage import (
                TriageState,
                assign_resolution_tier,
                classify_issue_type,
                emit_routed,
                enrich_context,
                score_severity,
            )

            state: TriageState = {
                "validated_signal": vs.model_dump(),
                "category": "",
                "resolution_tier": 2,
                "severity_score": 3,
                "sentiment_score": 0.0,
                "churn_risk": False,
                "routing_decision": "ESCALATION",
                "routing_rationale": "",
                "kb_context": None,
                "trace_id": "trace-triage-001",
                "error": None,
            }
            state.update(await classify_issue_type(state))
            state.update(await assign_resolution_tier(state))
            state.update(await score_severity(state))
            state.update(await enrich_context(state))
            await emit_routed(state)

        assert state["category"] == "eSIM activation"
        assert state["resolution_tier"] == 0
        assert state["routing_decision"] == "RESOLVER"
        mock_publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tier2_routes_to_escalation(self):
        vs = _make_validated(_load_fixture("signal_tier2_billing.json"), carrier="verizon")

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "category": "Billing dispute",
                        "severity_score": 5,
                        "sentiment_score": -0.95,
                        "churn_risk": True,
                        "routing_rationale": "Billing dispute requires account access — Tier 2",
                    }
                )
            )
        )
        mock_publish = AsyncMock()
        mock_kb = AsyncMock(return_value={"error": "not found"})
        mock_redis = _mock_redis_fresh()

        with (
            patch("pulseguard.agents.triage._MODEL", mock_llm),
            patch("pulseguard.orchestrator.event_bus.publish_triage_report", mock_publish),
            patch("pulseguard.mcp_servers.classify_mcp.get_kb_context", mock_kb),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            from pulseguard.agents.triage import (
                TriageState,
                assign_resolution_tier,
                classify_issue_type,
                emit_routed,
                enrich_context,
                score_severity,
            )

            state: TriageState = {
                "validated_signal": vs.model_dump(),
                "category": "",
                "resolution_tier": 2,
                "severity_score": 3,
                "sentiment_score": 0.0,
                "churn_risk": False,
                "routing_decision": "ESCALATION",
                "routing_rationale": "",
                "kb_context": None,
                "trace_id": "trace-triage-002",
                "error": None,
            }
            state.update(await classify_issue_type(state))
            state.update(await assign_resolution_tier(state))
            state.update(await score_severity(state))
            state.update(await enrich_context(state))
            await emit_routed(state)

        assert state["category"] == "Billing dispute"
        assert state["resolution_tier"] == 2
        assert state["routing_decision"] == "ESCALATION"
        assert state["churn_risk"] is True


# ── RESOLVER ───────────────────────────────────────────────────────────────


class TestResolverAgent:
    @pytest.mark.asyncio
    async def test_high_confidence_resolves(self):
        vs = _make_validated(_load_fixture("signal_tier0_esim.json"), carrier="verizon")
        tr = _make_triage(vs.signal_id, "eSIM activation", 0, "RESOLVER")

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                MagicMock(
                    content=[
                        {
                            "type": "text",
                            "text": "To activate your Verizon eSIM: go to Settings > Cellular > Add eSIM...",
                        }
                    ]
                ),
                MagicMock(content="0.92 | Response accurately covers all eSIM activation steps"),
                MagicMock(
                    content="To activate your Verizon eSIM: Settings > Cellular > Add eSIM > scan QR code > restart. ^PG"
                ),
            ]
        )
        mock_kb = AsyncMock(
            return_value={
                "category": "eSIM activation",
                "carrier": "verizon",
                "tier": 0,
                "title": "Verizon eSIM Activation Steps",
                "steps": ["Step 1: Settings > Cellular", "Step 2: Add eSIM", "Step 3: Scan QR"],
                "escalation_triggers": ["EE002 error"],
                "expected_resolution_minutes": 10,
                "platform_responses": {"x": "Settings > Cellular > Add eSIM > scan QR. ^PG"},
            }
        )
        mock_write = AsyncMock(return_value={"written": True})
        mock_escalate = AsyncMock()

        with (
            patch("pulseguard.agents.resolver._MODEL", mock_llm),
            patch("pulseguard.agents.resolver._MODEL_THINKING", mock_llm),
            patch("pulseguard.mcp_servers.kb_mcp.get_resolution_script", mock_kb),
            patch("pulseguard.mcp_servers.output_mcp.write_resolution", mock_write),
            patch("pulseguard.orchestrator.event_bus.publish_escalation_needed", mock_escalate),
        ):
            from pulseguard.agents.resolver import (
                ResolverState,
                decide,
                draft_response,
                emit_resolved,
                format_for_channel,
                retrieve_resolution,
                validate_confidence,
            )

            state: ResolverState = {
                "triage_report": tr.model_dump(),
                "validated_signal": vs.model_dump(),
                "kb_script": None,
                "draft_response": "",
                "confidence_score": 0.0,
                "confidence_reason": "",
                "formatted_response": "",
                "resolved": False,
                "escalation_reason": None,
                "trace_id": "trace-resolver-001",
            }
            state.update(await retrieve_resolution(state))
            state.update(await draft_response(state))
            state.update(await validate_confidence(state))
            state.update(await decide(state))
            state.update(await format_for_channel(state))
            await emit_resolved(state)

        assert state["resolved"] is True
        assert state["confidence_score"] >= 0.85
        mock_write.assert_awaited_once()
        mock_escalate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_low_confidence_escalates(self):
        vs = _make_validated(_load_fixture("signal_tier1_network.json"), carrier="att")
        tr = _make_triage(vs.signal_id, "Network signal (individual)", 1, "RESOLVER")

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                MagicMock(content=[{"type": "text", "text": "Try toggling airplane mode..."}]),
                MagicMock(
                    content="0.60 | Response incomplete, missing carrier settings update step"
                ),
            ]
        )
        mock_kb = AsyncMock(return_value={"error": "not found"})
        mock_write = AsyncMock(return_value={"written": True})
        mock_escalate = AsyncMock()

        with (
            patch("pulseguard.agents.resolver._MODEL", mock_llm),
            patch("pulseguard.agents.resolver._MODEL_THINKING", mock_llm),
            patch("pulseguard.mcp_servers.kb_mcp.get_resolution_script", mock_kb),
            patch("pulseguard.mcp_servers.output_mcp.write_resolution", mock_write),
            patch("pulseguard.orchestrator.event_bus.publish_escalation_needed", mock_escalate),
        ):
            from pulseguard.agents.resolver import (
                ResolverState,
                decide,
                draft_response,
                emit_resolved,
                retrieve_resolution,
                validate_confidence,
            )

            state: ResolverState = {
                "triage_report": tr.model_dump(),
                "validated_signal": vs.model_dump(),
                "kb_script": None,
                "draft_response": "",
                "confidence_score": 0.0,
                "confidence_reason": "",
                "formatted_response": "",
                "resolved": False,
                "escalation_reason": None,
                "trace_id": "trace-resolver-002",
            }
            state.update(await retrieve_resolution(state))
            state.update(await draft_response(state))
            state.update(await validate_confidence(state))
            state.update(await decide(state))
            await emit_resolved(state)

        assert state["resolved"] is False
        assert state["confidence_score"] < 0.85
        mock_escalate.assert_awaited_once()


# ── ESCALATION ─────────────────────────────────────────────────────────────


class TestEscalationAgent:
    @pytest.mark.asyncio
    async def test_billing_dispute_gets_p1(self):
        vs = _make_validated(_load_fixture("signal_tier2_billing.json"), carrier="verizon")
        tr = _make_triage(vs.signal_id, "Billing dispute", 2, "ESCALATION")
        # Billing dispute + churn risk + severity 5 = P1
        tr_dict = tr.model_dump()
        tr_dict["severity_score"] = 5
        tr_dict["churn_risk"] = True
        tr_dict["sentiment_score"] = -0.95

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "summary": "Customer reports billing overcharge for 3 consecutive months with unresolved promo discount.",
                        "recommended_action": "Review account billing history for last 3 months, identify discount application status, issue credit if overcharge confirmed.",
                    }
                )
            )
        )
        mock_slack = AsyncMock(return_value={"sent": True})
        mock_email = AsyncMock(return_value={"sent": True})
        mock_write = AsyncMock(return_value={"written": True})

        with (
            patch("pulseguard.agents.escalation._MODEL", mock_llm),
            patch("pulseguard.mcp_servers.notify_mcp.send_slack_alert", mock_slack),
            patch("pulseguard.mcp_servers.notify_mcp.send_email_brief", mock_email),
            patch("pulseguard.mcp_servers.output_mcp.write_escalation", mock_write),
        ):
            from pulseguard.agents.escalation import (
                EscalationState,
                assign_priority,
                compose_brief,
                notify,
                park_in_queue,
            )

            state: EscalationState = {
                "signal_id": vs.signal_id,
                "triage_report": tr_dict,
                "validated_signal": vs.model_dump(),
                "attempted_resolution": None,
                "brief_summary": "",
                "recommended_action": "",
                "severity": "P2",
                "trace_id": "trace-esc-001",
                "acknowledged": False,
                "error": None,
            }
            state.update(await compose_brief(state))
            state.update(await assign_priority(state))
            await notify(state)
            await park_in_queue(state)

        assert state["severity"] == "P1"
        assert (
            "billing" in state["brief_summary"].lower()
            or "overcharge" in state["brief_summary"].lower()
        )
        mock_slack.assert_awaited_once()
        mock_email.assert_awaited_once()
        mock_write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_priority_assignment_rules(self):
        from pulseguard.agents.escalation import assign_priority

        # Security-sensitive always P1
        base = {
            "signal_id": "test",
            "triage_report": {
                "category": "Account access / lock",
                "severity_score": 1,
                "churn_risk": False,
            },
            "validated_signal": {},
            "attempted_resolution": None,
            "brief_summary": "",
            "recommended_action": "",
            "severity": "P3",
            "trace_id": "t1",
            "acknowledged": False,
            "error": None,
        }
        result = await assign_priority(base)
        assert result["severity"] == "P1"

        # Churn risk bumps P3 to P2
        base["triage_report"] = {
            "category": "General complaint / NPS risk",
            "severity_score": 1,
            "churn_risk": True,
        }
        result = await assign_priority(base)
        assert result["severity"] == "P2"

    @pytest.mark.asyncio
    async def test_await_ack_times_out_when_never_acknowledged(self):
        """await_ack must poll the pulseguard:escalations hash (the entry
        acknowledge_escalation actually mutates) and, if the acknowledged flag
        never flips within the severity's timeout, return acknowledged=False
        without hanging for the real timeout duration."""
        from pulseguard.agents.escalation import await_ack

        state = {
            "signal_id": "sig-timeout-test",
            "severity": "P1",  # 3600s timeout
            "trace_id": "trace-timeout-001",
        }

        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)  # never acknowledged

        # Fake the event loop clock so the 3600s P1 timeout elapses after one
        # poll iteration instead of requiring a real hour of wall-clock time.
        fake_loop = MagicMock()
        fake_loop.time = MagicMock(side_effect=[0, 0, 4000])

        with (
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
            patch("asyncio.get_event_loop", return_value=fake_loop),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await await_ack(state)

        assert result == {"acknowledged": False}
        mock_redis.hget.assert_awaited_with("pulseguard:escalations", "sig-timeout-test")
