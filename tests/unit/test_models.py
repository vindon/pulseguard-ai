from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pulseguard.models import (
    AdapterHealth,
    CarrierConfig,
    EscalationBrief,
    RawSignal,
    ResolutionRecord,
    TriageReport,
    ValidatedSignal,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _raw_signal(**overrides) -> dict:
    base = dict(
        signal_id="sig-001",
        source="x",
        source_id="tweet-123",
        author_handle="a" * 64,  # pre-hashed
        content="My Verizon signal keeps dropping in downtown Chicago",
        url="https://x.com/user/status/tweet-123",
        posted_at=_now(),
        ingested_at=_now(),
    )
    base.update(overrides)
    return base


class TestRawSignal:
    def test_valid_construction(self):
        sig = RawSignal(**_raw_signal())
        assert sig.signal_id == "sig-001"
        assert sig.carrier_hint is None
        assert sig.adapter_metadata == {}

    def test_all_sources_accepted(self):
        for src in ("x", "reddit"):
            sig = RawSignal(**_raw_signal(source=src))
            assert sig.source == src

    def test_invalid_source_rejected(self):
        with pytest.raises(ValidationError):
            RawSignal(**_raw_signal(source="facebook"))

    def test_carrier_hint_optional(self):
        sig = RawSignal(**_raw_signal(carrier_hint="verizon"))
        assert sig.carrier_hint == "verizon"

    def test_adapter_metadata_populated(self):
        sig = RawSignal(**_raw_signal(adapter_metadata={"subreddit": "r/verizon", "score": 42}))
        assert sig.adapter_metadata["subreddit"] == "r/verizon"


class TestValidatedSignal:
    def test_valid_construction(self):
        raw = RawSignal(**_raw_signal())
        vs = ValidatedSignal(
            signal_id="sig-001",
            raw=raw,
            detected_carrier="verizon",
            is_valid=True,
            validity_reason="Genuine network complaint",
            content_hash="abc123",
            sentinel_trace_id="trace-001",
            validated_at=_now(),
        )
        assert vs.is_valid is True
        assert vs.detected_carrier == "verizon"


class TestTriageReport:
    def test_valid_construction(self):
        tr = TriageReport(
            signal_id="sig-001",
            category="Network signal (individual)",
            resolution_tier=1,
            severity_score=3,
            sentiment_score=-0.7,
            churn_risk=False,
            routing_decision="RESOLVER",
            routing_rationale="Tier 1 network issue, attempting autonomous resolution",
            triage_trace_id="trace-002",
            triaged_at=_now(),
        )
        assert tr.resolution_tier == 1
        assert tr.routing_decision == "RESOLVER"

    def test_invalid_tier_rejected(self):
        with pytest.raises(ValidationError):
            TriageReport(
                signal_id="sig-001",
                category="Billing dispute",
                resolution_tier=3,  # only 0, 1, 2 are valid
                severity_score=2,
                sentiment_score=0.0,
                churn_risk=False,
                routing_decision="ESCALATION",
                routing_rationale="...",
                triage_trace_id="trace-003",
                triaged_at=_now(),
            )

    def test_severity_score_bounds(self):
        with pytest.raises(ValidationError):
            TriageReport(
                signal_id="sig-001",
                category="App not working",
                resolution_tier=0,
                severity_score=6,  # max is 5
                sentiment_score=0.0,
                churn_risk=False,
                routing_decision="RESOLVER",
                routing_rationale="...",
                triage_trace_id="trace-004",
                triaged_at=_now(),
            )

    def test_sentiment_score_bounds(self):
        with pytest.raises(ValidationError):
            TriageReport(
                signal_id="sig-001",
                category="App not working",
                resolution_tier=0,
                severity_score=1,
                sentiment_score=1.5,  # max is 1.0
                churn_risk=False,
                routing_decision="RESOLVER",
                routing_rationale="...",
                triage_trace_id="trace-005",
                triaged_at=_now(),
            )

    def test_all_routing_decisions_valid(self):
        for decision in ("RESOLVER", "ESCALATION"):
            tr = TriageReport(
                signal_id="sig-001",
                category="Billing dispute",
                resolution_tier=2,
                severity_score=4,
                sentiment_score=-0.8,
                churn_risk=True,
                routing_decision=decision,
                routing_rationale="test",
                triage_trace_id="trace-006",
                triaged_at=_now(),
            )
            assert tr.routing_decision == decision


class TestResolutionRecord:
    def test_valid_construction(self):
        rr = ResolutionRecord(
            signal_id="sig-001",
            category="eSIM activation",
            carrier="verizon",
            draft_response="To activate your eSIM: 1) Go to Settings > Cellular...",
            source_platform="x",
            confidence_score=0.92,
            resolved=True,
            resolver_trace_id="trace-007",
            resolved_at=_now(),
        )
        assert rr.resolved is True
        assert rr.escalation_reason is None

    def test_unresolved_with_reason(self):
        rr = ResolutionRecord(
            signal_id="sig-001",
            category="Network signal (individual)",
            carrier="att",
            draft_response="",
            source_platform="reddit",
            confidence_score=0.60,
            resolved=False,
            escalation_reason="Confidence below threshold (0.60 < 0.85)",
            resolver_trace_id="trace-008",
            resolved_at=_now(),
        )
        assert rr.resolved is False
        assert "0.60" in rr.escalation_reason

    def test_confidence_score_bounds(self):
        with pytest.raises(ValidationError):
            ResolutionRecord(
                signal_id="sig-001",
                category="App not working",
                carrier="tmobile",
                draft_response="...",
                source_platform="x",
                confidence_score=1.1,  # max 1.0
                resolved=True,
                resolver_trace_id="trace-009",
                resolved_at=_now(),
            )


class TestEscalationBrief:
    def test_valid_construction(self):
        eb = EscalationBrief(
            signal_id="sig-001",
            summary="Customer reports persistent billing overcharge for 3 months",
            source_platform="x",
            carrier="verizon",
            category="Billing dispute",
            severity="P1",
            sentiment_score=-0.95,
            churn_risk=True,
            original_post_url="https://x.com/i/web/status/verizon",
            recommended_action="Review account billing history and issue credit if overcharge confirmed",
            escalation_trace_id="trace-010",
            escalated_at=_now(),
        )
        assert eb.acknowledged is False
        assert eb.acknowledged_by is None
        assert eb.severity == "P1"

    def test_acknowledged_state(self):
        now = _now()
        eb = EscalationBrief(
            signal_id="sig-001",
            summary="Account locked",
            source_platform="x",
            carrier="att",
            category="Account access / lock",
            severity="P2",
            sentiment_score=-0.5,
            churn_risk=False,
            original_post_url="https://x.com/user/123",
            recommended_action="Verify identity and unlock",
            escalation_trace_id="trace-011",
            escalated_at=now,
            acknowledged=True,
            acknowledged_by="agent_jane",
            acknowledged_at=now,
        )
        assert eb.acknowledged is True
        assert eb.acknowledged_by == "agent_jane"

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            EscalationBrief(
                signal_id="sig-001",
                summary="...",
                source_platform="x",
                carrier="verizon",
                category="Billing dispute",
                severity="P4",  # only P1, P2, P3 valid
                sentiment_score=0.0,
                churn_risk=False,
                original_post_url="https://x.com",
                recommended_action="...",
                escalation_trace_id="trace-012",
                escalated_at=_now(),
            )


class TestAdapterHealth:
    def test_healthy_status(self):
        ah = AdapterHealth(adapter_name="x", status="HEALTHY")
        assert ah.consecutive_errors == 0
        assert ah.monthly_cap_used is None

    def test_x_adapter_with_cap(self):
        ah = AdapterHealth(
            adapter_name="x",
            status="DEGRADED",
            monthly_cap_used=12500,
            monthly_cap_limit=15000,
            consecutive_errors=2,
            error_message="Rate limit warning at 83% capacity",
        )
        assert ah.monthly_cap_used == 12500
        assert ah.status == "DEGRADED"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            AdapterHealth(adapter_name="reddit", status="UNKNOWN")


class TestCarrierConfig:
    def test_verizon_config(self):
        cc = CarrierConfig(
            name="verizon",
            display_name="Verizon",
            handles=["@Verizon", "@VerizonSupport"],
            keywords=["verizon", "vzw"],
            play_store_id="com.verizon.mymobilesecure",
            subreddits=["r/verizon"],
        )
        assert cc.name == "verizon"
        assert len(cc.handles) == 2
