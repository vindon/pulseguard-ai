"""
Integration tests: escalation path — RESOLVER fails confidence → ESCALATION fires.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pulseguard.models.signals import RawSignal, ValidatedSignal
from pulseguard.models.triage import TriageReport

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text())


def _now() -> datetime:
    return datetime.now(UTC)


class _FakeAsyncRedis:
    """Minimal in-memory stand-in for the subset of redis-py's async API this
    pipeline touches (hset/hget/get/decr), so a test can exercise the real
    write_escalation / acknowledge_escalation / await_ack functions against a
    single shared store instead of mocking each of them away."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._strings: dict[str, str] = {}

    async def hset(self, name, key=None, value=None, mapping=None):  # noqa: ANN001
        table = self._hashes.setdefault(name, {})
        if mapping:
            table.update({k: str(v) for k, v in mapping.items()})
        else:
            table[key] = value

    async def hget(self, name, key):  # noqa: ANN001
        return self._hashes.get(name, {}).get(key)

    async def get(self, key):  # noqa: ANN001
        return self._strings.get(key)

    async def decr(self, key):  # noqa: ANN001
        current = int(self._strings.get(key, "0"))
        current -= 1
        self._strings[key] = str(current)
        return current


def _make_validated_signal(raw_dict: dict, carrier: str = "att") -> ValidatedSignal:
    raw = RawSignal(**raw_dict)
    return ValidatedSignal(
        signal_id=raw.signal_id,
        raw=raw,
        detected_carrier=carrier,
        is_valid=True,
        validity_reason="Genuine signal",
        content_hash="hash123",
        sentinel_trace_id="trace-test",
        validated_at=_now(),
    )


class TestEscalationPath:
    @pytest.mark.asyncio
    async def test_low_confidence_triggers_escalation_chain(self):
        raw = _load("signal_tier1_network.json")
        vs = _make_validated_signal(raw, carrier="att")
        tr = TriageReport(
            signal_id=vs.signal_id,
            category="Network signal (individual)",
            resolution_tier=1,
            severity_score=4,
            sentiment_score=-0.7,
            churn_risk=False,
            routing_decision="RESOLVER",
            routing_rationale="Tier 1 network signal — try resolver first",
            triage_trace_id="trace-esc-int-001",
            triaged_at=_now(),
        )

        escalation_events = []

        async def capture_escalation(signal_id, resolution):
            escalation_events.append({"signal_id": signal_id, "resolution": resolution})

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                MagicMock(content=[{"type": "text", "text": "Try airplane mode..."}]),  # draft
                MagicMock(
                    content="0.55 | Incomplete — missing carrier settings step"
                ),  # confidence
            ]
        )
        mock_kb = AsyncMock(return_value={"error": "not found"})
        mock_write_res = AsyncMock(return_value={"written": True})

        with (
            patch("pulseguard.agents.resolver._MODEL", mock_llm),
            patch("pulseguard.agents.resolver._MODEL_THINKING", mock_llm),
            patch("pulseguard.mcp_servers.kb_mcp.get_resolution_script", mock_kb),
            patch("pulseguard.mcp_servers.output_mcp.write_resolution", mock_write_res),
            patch(
                "pulseguard.orchestrator.event_bus.publish_escalation_needed", capture_escalation
            ),
        ):
            from pulseguard.agents.resolver import process_triage_report

            await process_triage_report(tr, vs.model_dump(), "trace-esc-int-001")

        assert len(escalation_events) == 1
        assert escalation_events[0]["signal_id"] == vs.signal_id
        assert escalation_events[0]["resolution"].resolved is False

    @pytest.mark.asyncio
    async def test_escalation_brief_composed_and_notified(self):
        raw = _load("signal_tier2_billing.json")
        vs = _make_validated_signal(raw, carrier="verizon")
        tr = TriageReport(
            signal_id=vs.signal_id,
            category="Billing dispute",
            resolution_tier=2,
            severity_score=5,
            sentiment_score=-0.95,
            churn_risk=True,
            routing_decision="ESCALATION",
            routing_rationale="Billing dispute — direct escalation",
            triage_trace_id="trace-esc-int-002",
            triaged_at=_now(),
        )

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "summary": "Customer reports repeated billing overcharge and imminent churn.",
                        "recommended_action": "Review billing history and issue credit.",
                    }
                )
            )
        )
        mock_slack = AsyncMock(return_value={"sent": True})
        mock_email = AsyncMock(return_value={"sent": True})
        mock_write_esc = AsyncMock(return_value={"written": True})

        with (
            patch("pulseguard.agents.escalation._MODEL", mock_llm),
            patch("pulseguard.mcp_servers.notify_mcp.send_slack_alert", mock_slack),
            patch("pulseguard.mcp_servers.notify_mcp.send_email_brief", mock_email),
            patch("pulseguard.mcp_servers.output_mcp.write_escalation", mock_write_esc),
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
                "triage_report": tr.model_dump(),
                "validated_signal": vs.model_dump(),
                "attempted_resolution": None,
                "brief_summary": "",
                "recommended_action": "",
                "severity": "P2",
                "trace_id": "trace-esc-int-002",
                "acknowledged": False,
                "error": None,
            }
            state.update(await compose_brief(state))
            state.update(await assign_priority(state))
            await notify(state)
            await park_in_queue(state)

        assert state["severity"] == "P1"  # severity=5 + churn risk
        assert (
            "overcharge" in state["brief_summary"].lower()
            or "billing" in state["brief_summary"].lower()
        )
        mock_slack.assert_awaited_once()
        mock_email.assert_awaited_once()
        mock_write_esc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_await_ack_sees_a_real_human_acknowledgement(self):
        """Regression test for the ack-path key mismatch: `park_in_queue` writes
        the EscalationBrief via the real `output_mcp.write_escalation`, a human
        acknowledges via the real `notify_mcp.acknowledge_escalation` (the same
        function the /escalations/{id}/ack endpoint calls), and `await_ack` must
        see that acknowledgement by reading the same `pulseguard:escalations`
        hash entry — not a separate, never-written key.
        """
        raw = _load("signal_tier2_billing.json")
        vs = _make_validated_signal(raw, carrier="verizon")
        tr = TriageReport(
            signal_id=vs.signal_id,
            category="Billing dispute",
            resolution_tier=2,
            severity_score=5,
            sentiment_score=-0.95,
            churn_risk=True,
            routing_decision="ESCALATION",
            routing_rationale="Billing dispute — direct escalation",
            triage_trace_id="trace-esc-int-003",
            triaged_at=_now(),
        )

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "summary": "Customer reports repeated billing overcharge.",
                        "recommended_action": "Review billing history and issue credit.",
                    }
                )
            )
        )
        fake_redis = _FakeAsyncRedis()

        with (
            patch("pulseguard.agents.escalation._MODEL", mock_llm),
            patch("pulseguard.mcp_servers.notify_mcp.send_slack_alert", AsyncMock(return_value={"sent": True})),
            patch("pulseguard.mcp_servers.notify_mcp.send_email_brief", AsyncMock(return_value={"sent": True})),
            patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=fake_redis),
            patch("pulseguard.mcp_servers.notify_mcp.get_async_redis", return_value=fake_redis),
            patch("pulseguard.redis_client.get_async_redis", return_value=fake_redis),
        ):
            from pulseguard.agents.escalation import (
                EscalationState,
                assign_priority,
                await_ack,
                compose_brief,
                notify,
                park_in_queue,
            )
            from pulseguard.mcp_servers.notify_mcp import acknowledge_escalation

            state: EscalationState = {
                "signal_id": vs.signal_id,
                "triage_report": tr.model_dump(),
                "validated_signal": vs.model_dump(),
                "attempted_resolution": None,
                "brief_summary": "",
                "recommended_action": "",
                "severity": "P2",
                "trace_id": "trace-esc-int-003",
                "acknowledged": False,
                "error": None,
            }
            state.update(await compose_brief(state))
            state.update(await assign_priority(state))
            await notify(state)
            await park_in_queue(state)

            # Sanity check: the brief exists but isn't acknowledged yet — this
            # is the state a freshly-parked escalation is in before a human
            # acts on it.
            parked_raw = await fake_redis.hget("pulseguard:escalations", vs.signal_id)
            assert json.loads(parked_raw)["acknowledged"] is False

            # A human hits POST /escalations/{id}/ack — the real production
            # call, not a mock.
            ack_result = await acknowledge_escalation(vs.signal_id, "agent@pulseguard.local")
            assert ack_result["acknowledged"] is True

            # await_ack must observe that acknowledgement immediately, via the
            # same hash entry acknowledge_escalation just wrote to.
            result = await await_ack(state)

        assert result == {"acknowledged": True}
