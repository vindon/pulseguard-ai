"""
MCP tool unit tests — Redis and ChromaDB are mocked.
Tests validate: input validation, happy path, error handling, idempotency.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sample_brief() -> dict:
    return dict(
        signal_id="sig-001",
        summary="Customer reports billing overcharge for 3 months",
        source_platform="x",
        carrier="verizon",
        category="Billing dispute",
        severity="P1",
        sentiment_score=-0.9,
        churn_risk=True,
        original_post_url="https://x.com/i/web/status/abc",
        recommended_action="Review account and issue credit",
        escalation_trace_id="trace-001",
        escalated_at=_now_iso(),
    )


def _sample_resolution() -> dict:
    return dict(
        signal_id="sig-002",
        category="eSIM activation",
        carrier="verizon",
        draft_response="To activate your eSIM: Settings > Cellular > Add eSIM...",
        source_platform="x",
        confidence_score=0.92,
        resolved=True,
        resolver_trace_id="trace-002",
        resolved_at=_now_iso(),
    )


# ── feed_mcp ───────────────────────────────────────────────────────────────


class TestFeedMcp:
    @pytest.mark.asyncio
    async def test_list_pending_signals_happy_path(self):
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(
            return_value=[
                json.dumps({"signal_id": "sig-001", "source": "x"}),
                json.dumps({"signal_id": "sig-002", "source": "reddit"}),
            ]
        )
        with patch("pulseguard.mcp_servers.feed_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.feed_mcp import list_pending_signals

            result = await list_pending_signals(limit=10)
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_list_pending_signals_source_filter(self):
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(
            return_value=[
                json.dumps({"signal_id": "sig-001", "source": "x"}),
                json.dumps({"signal_id": "sig-002", "source": "reddit"}),
            ]
        )
        with patch("pulseguard.mcp_servers.feed_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.feed_mcp import list_pending_signals

            result = await list_pending_signals(source="x", limit=10)
        assert result["count"] == 1
        assert result["signals"][0]["source"] == "x"

    @pytest.mark.asyncio
    async def test_list_pending_signals_invalid_limit(self):
        from pulseguard.mcp_servers.feed_mcp import list_pending_signals

        result = await list_pending_signals(limit=0)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mark_signal_processed_valid(self):
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        with patch("pulseguard.mcp_servers.feed_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.feed_mcp import mark_signal_processed

            result = await mark_signal_processed("sig-001", "validated")
        assert result["success"] is True
        assert result["outcome"] == "validated"

    @pytest.mark.asyncio
    async def test_mark_signal_processed_invalid_outcome(self):
        from pulseguard.mcp_servers.feed_mcp import mark_signal_processed

        result = await mark_signal_processed("sig-001", "ignored")
        assert "error" in result


# ── dedup_mcp ──────────────────────────────────────────────────────────────


class TestDedupMcp:
    @pytest.mark.asyncio
    async def test_check_duplicate_not_seen(self):
        mock_redis = AsyncMock()
        mock_redis.sismember = AsyncMock(return_value=False)
        with patch("pulseguard.mcp_servers.dedup_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.dedup_mcp import check_duplicate

            result = await check_duplicate("hash123", "source-id-1")
        assert result["is_duplicate"] is False

    @pytest.mark.asyncio
    async def test_check_duplicate_seen(self):
        mock_redis = AsyncMock()
        mock_redis.sismember = AsyncMock(return_value=True)
        with patch("pulseguard.mcp_servers.dedup_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.dedup_mcp import check_duplicate

            result = await check_duplicate("hash123", "source-id-1")
        assert result["is_duplicate"] is True

    @pytest.mark.asyncio
    async def test_check_duplicate_missing_params(self):
        from pulseguard.mcp_servers.dedup_mcp import check_duplicate

        result = await check_duplicate("", "source-id-1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_register_signal(self):
        mock_redis = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.incr = AsyncMock()
        with patch("pulseguard.mcp_servers.dedup_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.dedup_mcp import register_signal

            result = await register_signal("hash456", "source-id-2")
        assert result["registered"] is True
        mock_redis.sadd.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_dedup_stats(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=lambda k: "100" if "seen" in k else "15")
        with patch("pulseguard.mcp_servers.dedup_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.dedup_mcp import get_dedup_stats

            result = await get_dedup_stats()
        assert result["total_seen"] == 100


# ── classify_mcp ───────────────────────────────────────────────────────────


class TestClassifyMcp:
    @pytest.mark.asyncio
    async def test_lookup_esim_category(self):
        from pulseguard.mcp_servers.classify_mcp import lookup_taxonomy

        result = await lookup_taxonomy("My eSIM activation code isn't working")
        assert result["category"] == "eSIM activation"
        assert result["tier"] == 0

    @pytest.mark.asyncio
    async def test_lookup_billing_dispute(self):
        from pulseguard.mcp_servers.classify_mcp import lookup_taxonomy

        result = await lookup_taxonomy("I was overcharged and double charged this month")
        assert result["category"] == "Billing dispute"

    @pytest.mark.asyncio
    async def test_lookup_outage(self):
        from pulseguard.mcp_servers.classify_mcp import lookup_taxonomy

        result = await lookup_taxonomy(
            "There's a service outage in my area affecting the whole neighbourhood"
        )
        assert result["category"] == "Network outage (area-wide)"

    @pytest.mark.asyncio
    async def test_lookup_empty_input(self):
        from pulseguard.mcp_servers.classify_mcp import lookup_taxonomy

        result = await lookup_taxonomy("")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_tier_known_category(self):
        from pulseguard.mcp_servers.classify_mcp import get_tier

        result = await get_tier("eSIM activation")
        assert result["tier"] == 0

    @pytest.mark.asyncio
    async def test_get_tier_unknown_category(self):
        from pulseguard.mcp_servers.classify_mcp import get_tier

        result = await get_tier("Quantum teleportation issue")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_kb_context(self):
        from pulseguard.mcp_servers.classify_mcp import get_kb_context

        result = await get_kb_context("eSIM activation", "verizon")
        assert result["tier"] == 0
        assert len(result["steps_preview"]) > 0

    @pytest.mark.asyncio
    async def test_get_kb_context_missing_carrier(self):
        from pulseguard.mcp_servers.classify_mcp import get_kb_context

        result = await get_kb_context("eSIM activation", "")
        assert "error" in result


# ── output_mcp ─────────────────────────────────────────────────────────────


class TestOutputMcp:
    @pytest.mark.asyncio
    async def test_write_resolution_happy_path(self):
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.output_mcp import write_resolution

            result = await write_resolution("sig-002", _sample_resolution())
        assert result["written"] is True

    @pytest.mark.asyncio
    async def test_write_resolution_invalid_model(self):
        mock_redis = AsyncMock()
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.output_mcp import write_resolution

            result = await write_resolution("sig-003", {"bad": "data"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_write_escalation_happy_path(self):
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.incr = AsyncMock()
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.output_mcp import write_escalation

            result = await write_escalation("sig-001", _sample_brief())
        assert result["written"] is True
        mock_redis.incr.assert_awaited_once()  # queue depth incremented

    @pytest.mark.asyncio
    async def test_get_signal_status_found(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(
            return_value={
                "stage": "escalated",
                "severity": "P1",
                "acknowledged": "False",
                "last_updated": _now_iso(),
            }
        )
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.output_mcp import get_signal_status

            result = await get_signal_status("sig-001")
        assert result["stage"] == "escalated"

    @pytest.mark.asyncio
    async def test_get_signal_status_not_found(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.output_mcp import get_signal_status

            result = await get_signal_status("sig-999")
        assert "error" in result
        assert result["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_export_escalation_json(self):
        mock_redis = AsyncMock()
        brief = _sample_brief()
        brief["escalated_at"] = _now_iso()
        brief["acknowledged"] = False
        mock_redis.hget = AsyncMock(return_value=json.dumps(brief))
        mock_redis.hgetall = AsyncMock(return_value={"stage": "escalated"})
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.output_mcp import export_escalation_json

            result = await export_escalation_json("sig-001")
        assert result["signal_id"] == "sig-001"
        assert "escalation_brief" in result
        assert "export_generated_at" in result

    @pytest.mark.asyncio
    async def test_export_escalation_not_found(self):
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        with patch("pulseguard.mcp_servers.output_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.output_mcp import export_escalation_json

            result = await export_escalation_json("sig-missing")
        assert result["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_list_resolved_hours_validation(self):
        from pulseguard.mcp_servers.output_mcp import list_resolved

        result = await list_resolved(hours=200)
        assert "error" in result


# ── notify_mcp ───────────────────────────────────────────────────────────────


class TestNotifyMcp:
    @pytest.mark.asyncio
    async def test_acknowledge_escalation_happy_path(self):
        brief = _sample_brief()
        brief["acknowledged"] = False
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=json.dumps(brief))
        mock_redis.hset = AsyncMock()
        mock_redis.decr = AsyncMock()
        with patch("pulseguard.mcp_servers.notify_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.notify_mcp import acknowledge_escalation

            result = await acknowledge_escalation("sig-001", "vinoth")

        assert result == {"acknowledged": True, "signal_id": "sig-001", "acknowledged_by": "vinoth"}
        # Must persist onto the *same* record other reads (list_escalations,
        # the gateway's lifecycle endpoint) pull from, not a side key nothing
        # else looks at.
        mock_redis.hset.assert_awaited_once()
        written_hash_key, written_signal_id, written_json = mock_redis.hset.call_args[0]
        assert written_hash_key == "pulseguard:escalations"
        assert written_signal_id == "sig-001"
        written = json.loads(written_json)
        assert written["acknowledged"] is True
        assert written["acknowledged_by"] == "vinoth"
        assert written["acknowledged_at"] is not None
        mock_redis.decr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acknowledge_escalation_not_found(self):
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        with patch("pulseguard.mcp_servers.notify_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.notify_mcp import acknowledge_escalation

            result = await acknowledge_escalation("sig-missing", "vinoth")
        assert result["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_acknowledge_escalation_missing_params(self):
        from pulseguard.mcp_servers.notify_mcp import acknowledge_escalation

        result = await acknowledge_escalation("", "vinoth")
        assert result["code"] == "INVALID_PARAM"

    @pytest.mark.asyncio
    async def test_acknowledge_escalation_idempotent(self):
        """Re-acknowledging an already-acked escalation must not decrement
        the queue depth a second time."""
        brief = _sample_brief()
        brief["acknowledged"] = True
        brief["acknowledged_by"] = "someone_else"
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=json.dumps(brief))
        mock_redis.hset = AsyncMock()
        mock_redis.decr = AsyncMock()
        with patch("pulseguard.mcp_servers.notify_mcp.get_async_redis", return_value=mock_redis):
            from pulseguard.mcp_servers.notify_mcp import acknowledge_escalation

            result = await acknowledge_escalation("sig-001", "vinoth")

        assert result["acknowledged_by"] == "someone_else"
        mock_redis.hset.assert_not_awaited()
        mock_redis.decr.assert_not_awaited()


class TestEnterpriseIntegrations:
    """The four outbound integrations (generic webhook, Teams, Zendesk,
    Freshdesk) share one contract with existing Slack/email: unconfigured
    means a graceful no-op, configured means a real, verifiable HTTP call."""

    @pytest.mark.asyncio
    async def test_webhook_alert_not_configured(self):
        from pulseguard.mcp_servers.notify_mcp import send_webhook_alert

        with patch("pulseguard.mcp_servers.notify_mcp.settings.webhook_url", ""):
            result = await send_webhook_alert(_sample_brief())
        assert result == {"sent": False, "reason": "WEBHOOK_URL not configured"}

    @pytest.mark.asyncio
    async def test_webhook_alert_signs_body_when_secret_configured(self):
        import hashlib
        import hmac

        from pulseguard.mcp_servers.notify_mcp import send_webhook_alert

        captured = {}

        def _capture(request):
            captured["body"] = request.content
            captured["signature"] = request.headers.get("x-pulseguard-signature")
            return httpx.Response(200, json={"ok": True})

        with (
            patch("pulseguard.mcp_servers.notify_mcp.settings.webhook_url", "https://hooks.example.com/pg"),
            patch("pulseguard.mcp_servers.notify_mcp.settings.webhook_secret", "shh"),
            respx.mock,
        ):
            respx.post("https://hooks.example.com/pg").mock(side_effect=_capture)
            result = await send_webhook_alert(_sample_brief())

        assert result["sent"] is True
        expected_sig = "sha256=" + hmac.new(b"shh", captured["body"], hashlib.sha256).hexdigest()
        assert captured["signature"] == expected_sig

    @pytest.mark.asyncio
    async def test_teams_alert_not_configured(self):
        from pulseguard.mcp_servers.notify_mcp import send_teams_alert

        with patch("pulseguard.mcp_servers.notify_mcp.settings.teams_webhook_url", ""):
            result = await send_teams_alert(_sample_brief())
        assert result == {"sent": False, "reason": "TEAMS_WEBHOOK_URL not configured"}

    @pytest.mark.asyncio
    async def test_teams_alert_posts_adaptive_card(self):
        from pulseguard.mcp_servers.notify_mcp import send_teams_alert

        with (
            patch(
                "pulseguard.mcp_servers.notify_mcp.settings.teams_webhook_url",
                "https://teams.example.com/workflow-url",
            ),
            respx.mock,
        ):
            route = respx.post("https://teams.example.com/workflow-url").mock(
                return_value=httpx.Response(200)
            )
            result = await send_teams_alert(_sample_brief())

        assert result["sent"] is True
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"

    @pytest.mark.asyncio
    async def test_zendesk_ticket_not_configured(self):
        from pulseguard.mcp_servers.notify_mcp import send_zendesk_ticket

        with patch("pulseguard.mcp_servers.notify_mcp.settings.zendesk_subdomain", ""):
            result = await send_zendesk_ticket(_sample_brief())
        assert result == {"sent": False, "reason": "Zendesk credentials not configured"}

    @pytest.mark.asyncio
    async def test_zendesk_ticket_created_without_customer_pii(self):
        from pulseguard.mcp_servers.notify_mcp import send_zendesk_ticket

        with (
            patch("pulseguard.mcp_servers.notify_mcp.settings.zendesk_subdomain", "acme"),
            patch("pulseguard.mcp_servers.notify_mcp.settings.zendesk_email", "cx@acme.com"),
            patch("pulseguard.mcp_servers.notify_mcp.settings.zendesk_api_token", "tok123"),
            respx.mock,
        ):
            route = respx.post("https://acme.zendesk.com/api/v2/tickets.json").mock(
                return_value=httpx.Response(201, json={"ticket": {"id": 42}})
            )
            result = await send_zendesk_ticket(_sample_brief())

        assert result == {"sent": True, "signal_id": "sig-001", "ticket_id": 42}
        sent = json.loads(route.calls[0].request.content)
        # No real customer identity is ever sent — only the hashed signal_id.
        assert sent["ticket"]["requester"]["unique_external_id"] == "pulseguard-sig-001"
        assert "email" not in sent["ticket"]["requester"]

    @pytest.mark.asyncio
    async def test_freshdesk_ticket_not_configured(self):
        from pulseguard.mcp_servers.notify_mcp import send_freshdesk_ticket

        with patch("pulseguard.mcp_servers.notify_mcp.settings.freshdesk_domain", ""):
            result = await send_freshdesk_ticket(_sample_brief())
        assert result == {"sent": False, "reason": "Freshdesk credentials not configured"}

    @pytest.mark.asyncio
    async def test_freshdesk_ticket_created_without_customer_pii(self):
        from pulseguard.mcp_servers.notify_mcp import send_freshdesk_ticket

        with (
            patch("pulseguard.mcp_servers.notify_mcp.settings.freshdesk_domain", "acme"),
            patch("pulseguard.mcp_servers.notify_mcp.settings.freshdesk_api_key", "key123"),
            respx.mock,
        ):
            route = respx.post("https://acme.freshdesk.com/api/v2/tickets").mock(
                return_value=httpx.Response(201, json={"id": 99})
            )
            result = await send_freshdesk_ticket(_sample_brief())

        assert result == {"sent": True, "signal_id": "sig-001", "ticket_id": 99}
        sent = json.loads(route.calls[0].request.content)
        assert sent["unique_external_id"] == "pulseguard-sig-001"
        assert "email" not in sent
