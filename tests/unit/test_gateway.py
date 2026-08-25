"""
Gateway unit tests — auth and request-validation, without spinning up the
full FastAPI app (that would require the orchestrator lifespan + a real
or heavily-mocked Redis). These test the pieces directly.
"""

import pytest
from fastapi import HTTPException

from pulseguard.gateway.auth import require_api_key
from pulseguard.gateway.routes import IngestRequest


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
