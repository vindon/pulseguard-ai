import json
from pathlib import Path

from pulseguard.security.decision_log import DecisionLogger


class TestDecisionLogger:
    def test_log_and_finalize_returns_entries(self, tmp_path: Path, monkeypatch) -> None:
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

    def test_finalize_writes_one_json_line_per_entry(self, tmp_path: Path, monkeypatch) -> None:
        log_path = tmp_path / "decisions.jsonl"
        monkeypatch.setattr("pulseguard.security.decision_log._DECISION_LOG_PATH", log_path)
        dl = DecisionLogger("resolver", "sig-002", "trace-002")
        dl.log(
            decision_type="resolve_or_escalate",
            decision="resolved",
            reason="confidence 0.91 >= 0.85",
        )
        dl.log(decision_type="resolve_or_escalate", decision="resolved", reason="second entry")
        dl.finalize()

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["decision"] == "resolved"

    def test_reason_truncated_to_500_chars(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "pulseguard.security.decision_log._DECISION_LOG_PATH", tmp_path / "decisions.jsonl"
        )
        dl = DecisionLogger("sentinel", "sig-003", "trace-003")
        dl.log(decision_type="validity_classification", decision="valid", reason="x" * 1000)
        entries = dl.finalize()
        assert len(entries[0]["reason"]) == 500

    def test_no_entries_writes_nothing(self, tmp_path: Path, monkeypatch) -> None:
        log_path = tmp_path / "decisions.jsonl"
        monkeypatch.setattr("pulseguard.security.decision_log._DECISION_LOG_PATH", log_path)
        dl = DecisionLogger("escalation", "sig-004", "trace-004")
        entries = dl.finalize()
        assert entries == []
        assert not log_path.exists()
