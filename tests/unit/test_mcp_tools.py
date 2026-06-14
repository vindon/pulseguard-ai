"""
MCP tool unit tests — Redis and ChromaDB are mocked.
Tests validate: input validation, happy path, error handling, idempotency.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sample_brief() -> dict:
    return dict(
        signal_id="sig-001",
        summary="Customer reports billing overcharge for 3 months",
        source_platform="trustpilot",
        carrier="verizon",
        category="Billing dispute",
        severity="P1",
        sentiment_score=-0.9,
        churn_risk=True,
        original_post_url="https://trustpilot.com/review/abc",
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
