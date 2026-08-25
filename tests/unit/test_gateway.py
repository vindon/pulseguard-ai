"""
Gateway unit tests — auth and request-validation, without spinning up the
full FastAPI app (that would require the orchestrator lifespan + a real
or heavily-mocked Redis). These test the pieces directly.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from pulseguard.gateway.auth import require_api_key
from pulseguard.gateway.routes import IngestRequest, _safe_process_signal
from pulseguard.models.signals import RawSignal


class TestRequireApiKey:
    async def test_missing_key_rejected(self, monkeypatch):
        monkeypatch.setattr("pulseguard.gateway.auth.settings.pulseguard_api_key", "secret-key")
        with pytest.raises(HTTPException) as exc:
            await require_api_key(api_key=None)
        assert exc.value.status_code == 401

    async def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setattr("pulseguard.gateway.auth.settings.pulseguard_api_key", "secret-key")
        with pytest.raises(HTTPException) as exc:
            await require_api_key(api_key="wrong-key")
        assert exc.value.status_code == 401

    async def test_correct_key_accepted(self, monkeypatch):
        monkeypatch.setattr("pulseguard.gateway.auth.settings.pulseguard_api_key", "secret-key")
        result = await require_api_key(api_key="secret-key")
        assert result == "secret-key"

    async def test_empty_configured_key_rejects_everything(self, monkeypatch):
        # An unset PULSEGUARD_API_KEY must fail closed, not fail open.
        monkeypatch.setattr("pulseguard.gateway.auth.settings.pulseguard_api_key", "")
        with pytest.raises(HTTPException) as exc:
            await require_api_key(api_key="")
        assert exc.value.status_code == 401


class TestIngestRequestBounds:
    def _base(self, **overrides):
        payload = dict(
            source="app_store",
            source_id="id-1",
            author_handle="someone",
            content="short post",
            url="https://example.com/1",
            posted_at="2026-01-01T00:00:00Z",
        )
        payload.update(overrides)
        return payload

    def test_normal_payload_accepted(self):
        req = IngestRequest(**self._base())
        assert req.content == "short post"

    def test_oversized_content_rejected(self):
        with pytest.raises(ValueError):
            IngestRequest(**self._base(content="x" * 40_001))

    def test_max_length_content_accepted(self):
        req = IngestRequest(**self._base(content="x" * 40_000))
        assert len(req.content) == 40_000

    def test_oversized_url_rejected(self):
        with pytest.raises(ValueError):
            IngestRequest(**self._base(url="https://example.com/" + "a" * 2000))


class TestSafeProcessSignal:
    """Manual ingest used to fire process_signal via a bare
    asyncio.create_task with no exception handler at all — a failure (bad
    Anthropic response, Redis hiccup) vanished except for an unlogged
    asyncio warning, while the caller had already gotten 200/queued. This
    covers the fix: a failure must be logged and hit the audit trail,
    matching what the orchestrator's own scheduled polling already does.
    """

    def _signal(self) -> RawSignal:
        return RawSignal(
            signal_id="sig-fail-001",
            source="x",
            source_id="src-1",
            author_handle="handle",
            content="some content",
            url="https://example.com/1",
            posted_at=datetime.now(UTC),
            ingested_at=datetime.now(UTC),
        )

    async def test_failure_is_logged_and_audited(self):
        signal = self._signal()
        with (
            patch(
                "pulseguard.agents.sentinel.process_signal",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch("pulseguard.security.audit.write_audit_entry") as mock_audit,
        ):
            await _safe_process_signal(signal, "trace-1")

        mock_audit.assert_called_once_with(
            "sentinel",
            "sig-fail-001",
            "signal_processing_failed",
            "trace-1",
            {"reason": "boom"},
        )

    async def test_success_does_not_touch_the_audit_trail(self):
        signal = self._signal()
        with (
            patch("pulseguard.agents.sentinel.process_signal", new=AsyncMock(return_value=None)),
            patch("pulseguard.security.audit.write_audit_entry") as mock_audit,
        ):
            await _safe_process_signal(signal, "trace-2")

        mock_audit.assert_not_called()
