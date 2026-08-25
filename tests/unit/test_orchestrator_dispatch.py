"""
_dispatch_safely wraps every downstream-agent asyncio.create_task in the
orchestrator's stream consumers (_consume_validated_signals,
_consume_triage_reports, _consume_escalation_needed). Before this, a
failure inside process_validated_signal/process_triage_report/
process_escalation was silent except for an unlogged asyncio "Task
exception was never retrieved" warning — the signal just vanished with
no audit trail. These test the wrapper directly.
"""

from unittest.mock import AsyncMock, patch

from pulseguard.orchestrator.graph import _dispatch_safely


class TestDispatchSafely:
    async def test_failure_is_logged_and_audited(self):
        async def failing() -> None:
            raise RuntimeError("boom")

        with patch("pulseguard.security.audit.write_audit_entry") as mock_audit:
            await _dispatch_safely(failing(), "triage", "sig-001", "trace-001")

        mock_audit.assert_called_once_with(
            "triage", "sig-001", "triage_dispatch_failed", "trace-001", {"reason": "boom"}
        )

    async def test_success_does_not_touch_the_audit_trail(self):
        mock_coro = AsyncMock(return_value=None)()

        with patch("pulseguard.security.audit.write_audit_entry") as mock_audit:
            await _dispatch_safely(mock_coro, "escalation", "sig-002", "trace-002")

        mock_audit.assert_not_called()
