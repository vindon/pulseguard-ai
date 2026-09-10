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
            source="x",
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

    @pytest.mark.asyncio
    async def test_three_consecutive_failures_trip_the_halt(self):
        """_safe_process_signal is now routed through _dispatch_safely so it
        contributes to the same shared per-agent halt counter as every
        other entrypoint — this was the gap: manual ingest used to have its
        own inline try/except with no halt-counting at all."""
        signal = self._signal()
        mock_redis = AsyncMock()
        with (
            patch(
                "pulseguard.agents.sentinel.process_signal",
                new=AsyncMock(side_effect=RuntimeError("bad api key")),
            ),
            patch("pulseguard.orchestrator.halt.get_async_redis", return_value=mock_redis),
            patch("pulseguard.redis_client.get_async_redis", return_value=mock_redis),
        ):
            for i in range(3):
                await _safe_process_signal(signal, f"trace-halt-{i}")

        halt_calls = [c for c in mock_redis.set.await_args_list if c.args[0] == "pulseguard:halted"]
        assert len(halt_calls) == 1


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

        mock_update = AsyncMock(
            return_value={"error": "Draft sig-missing not found", "code": "NOT_FOUND"}
        )
        with patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update):
            with pytest.raises(HTTPException) as exc:
                await reject_draft("sig-missing", DraftReviewRequest(reviewed_by="vinoth"))
        assert exc.value.status_code == 404

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

        mock_publish.assert_awaited_once_with(
            in_reply_to_tweet_id="999", text="Try Settings > Cellular > Add eSIM."
        )
        assert result["status"] == "approved"
        # The real post_reply() return value must be captured and handed to
        # update_draft_status, so what actually got posted is queryable from
        # the product itself, not only from a log line.
        mock_update.assert_awaited_once_with(
            "sig-1",
            "approved",
            reviewed_by="vinoth",
            published_result={"posted": True, "tweet_id": "999"},
        )

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

    @pytest.mark.asyncio
    async def test_approve_draft_already_approved_returns_409_without_publishing(self):
        """Sequential double-approve (double-click, UI retry, back-button
        resubmit) must not publish twice: a draft that's already been
        actioned is rejected with 409 before any publish attempt."""
        from pulseguard.gateway.routes import DraftReviewRequest, approve_draft

        draft = {
            "signal_id": "sig-1",
            "source_platform": "x",
            "source_url": "https://x.com/i/web/status/999",
            "draft_text": "draft",
            "status": "approved",
        }
        mock_list = AsyncMock(return_value={"drafts": [draft], "count": 1})
        mock_publish = AsyncMock()
        mock_update = AsyncMock()

        with (
            patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list),
            patch("pulseguard.publishers.x_publisher.post_reply", mock_publish),
            patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update),
        ):
            with pytest.raises(HTTPException) as exc:
                await approve_draft("sig-1", DraftReviewRequest(reviewed_by="vinoth"))

        assert exc.value.status_code == 409
        mock_publish.assert_not_awaited()
        mock_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_approve_draft_already_rejected_returns_409_without_publishing(self):
        from pulseguard.gateway.routes import DraftReviewRequest, approve_draft

        draft = {
            "signal_id": "sig-1",
            "source_platform": "x",
            "source_url": "https://x.com/i/web/status/999",
            "draft_text": "draft",
            "status": "rejected",
        }
        mock_list = AsyncMock(return_value={"drafts": [draft], "count": 1})
        mock_publish = AsyncMock()
        mock_update = AsyncMock()

        with (
            patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list),
            patch("pulseguard.publishers.x_publisher.post_reply", mock_publish),
            patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update),
        ):
            with pytest.raises(HTTPException) as exc:
                await approve_draft("sig-1", DraftReviewRequest(reviewed_by="vinoth"))

        assert exc.value.status_code == 409
        mock_publish.assert_not_awaited()
        mock_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_approve_draft_unsupported_platform_returns_422_without_publishing(self):
        from pulseguard.gateway.routes import DraftReviewRequest, approve_draft

        draft = {
            "signal_id": "sig-1",
            "source_platform": "reddit",
            "source_url": "https://reddit.com/r/verizon/comments/abc123/some_thread",
            "draft_text": "draft",
            "status": "pending",
        }
        mock_list = AsyncMock(return_value={"drafts": [draft], "count": 1})
        mock_publish = AsyncMock()
        mock_update = AsyncMock()

        with (
            patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list),
            patch("pulseguard.publishers.x_publisher.post_reply", mock_publish),
            patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update),
        ):
            with pytest.raises(HTTPException) as exc:
                await approve_draft("sig-1", DraftReviewRequest(reviewed_by="vinoth"))

        assert exc.value.status_code == 422
        mock_publish.assert_not_awaited()
        mock_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_approve_draft_unparseable_source_url_returns_422_without_publishing(self):
        from pulseguard.gateway.routes import DraftReviewRequest, approve_draft

        draft = {
            "signal_id": "sig-1",
            "source_platform": "x",
            "source_url": "https://x.com/someuser",
            "draft_text": "draft",
            "status": "pending",
        }
        mock_list = AsyncMock(return_value={"drafts": [draft], "count": 1})
        mock_publish = AsyncMock()
        mock_update = AsyncMock()

        with (
            patch("pulseguard.mcp_servers.output_mcp.list_pending_drafts", mock_list),
            patch("pulseguard.publishers.x_publisher.post_reply", mock_publish),
            patch("pulseguard.mcp_servers.output_mcp.update_draft_status", mock_update),
        ):
            with pytest.raises(HTTPException) as exc:
                await approve_draft("sig-1", DraftReviewRequest(reviewed_by="vinoth"))

        assert exc.value.status_code == 422
        mock_publish.assert_not_awaited()
        mock_update.assert_not_awaited()
