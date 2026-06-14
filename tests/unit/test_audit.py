import json


class TestAuditLog:
    def test_write_creates_file(self, tmp_path, monkeypatch):
        log_path = tmp_path / "audit.jsonl"
        monkeypatch.setenv("AUDIT_LOG_PATH", str(log_path))
        # Re-import to pick up patched env var
        import importlib

        import pulseguard.security.audit as audit_mod

        importlib.reload(audit_mod)

        audit_mod.write_audit_entry(
            agent="sentinel",
            signal_id="sig-001",
            action="signal_validated",
            trace_id="trace-001",
        )
        assert log_path.exists()

    def test_write_valid_json(self, tmp_path, monkeypatch):
        log_path = tmp_path / "audit.jsonl"
        monkeypatch.setenv("AUDIT_LOG_PATH", str(log_path))
        import importlib

        import pulseguard.security.audit as audit_mod

        importlib.reload(audit_mod)

        audit_mod.write_audit_entry(
            agent="triage",
            signal_id="sig-002",
            action="signal_triaged",
            trace_id="trace-002",
            extra={"routing_decision": "RESOLVER"},
        )
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["agent"] == "triage"
        assert entry["signal_id"] == "sig-002"
        assert entry["routing_decision"] == "RESOLVER"

    def test_append_only(self, tmp_path, monkeypatch):
        log_path = tmp_path / "audit.jsonl"
        monkeypatch.setenv("AUDIT_LOG_PATH", str(log_path))
        import importlib

        import pulseguard.security.audit as audit_mod

        importlib.reload(audit_mod)

        for i in range(3):
            audit_mod.write_audit_entry(
                agent="resolver",
                signal_id=f"sig-{i:03d}",
                action="signal_resolved",
                trace_id=f"trace-{i:03d}",
            )
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_timestamp_present(self, tmp_path, monkeypatch):
        log_path = tmp_path / "audit.jsonl"
        monkeypatch.setenv("AUDIT_LOG_PATH", str(log_path))
        import importlib

        import pulseguard.security.audit as audit_mod

        importlib.reload(audit_mod)

        audit_mod.write_audit_entry(
            agent="escalation",
            signal_id="sig-999",
            action="signal_escalated",
            trace_id="trace-999",
        )
        entry = json.loads(log_path.read_text().strip())
        assert "timestamp" in entry
        assert "T" in entry["timestamp"]  # ISO format
