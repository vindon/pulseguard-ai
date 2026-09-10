from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import detect_carrier
from pulseguard.adapters.reddit_adapter import RedditAdapter, _is_relevant
from pulseguard.adapters.x_adapter import XAdapter, _build_query
from pulseguard.security.sanitise import hash_handle

# ── helpers ────────────────────────────────────────────────────────────────


def _mock_redis(cap: int = 0, newest_id: str | None = None) -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(side_effect=lambda key: (str(cap) if "monthly_reads" in key else newest_id))
    r.set = AsyncMock()
    r.incrby = AsyncMock()
    return r


def _tweet_response(newest_id: str = "99999") -> dict:
    return {
        "data": [
            {
                "id": "99999",
                "text": "My Verizon signal keeps dropping near downtown",
                "author_id": "user1",
                "created_at": "2026-01-01T12:00:00Z",
                "public_metrics": {"like_count": 5},
            }
        ],
        "includes": {"users": [{"id": "user1", "username": "angry_customer"}]},
        "meta": {"newest_id": newest_id, "result_count": 1},
    }


# ── carrier detection ───────────────────────────────────────────────────────


class TestCarrierDetection:
    def test_detects_verizon(self):
        assert detect_carrier("my verizon bill is wrong") == "verizon"

    def test_detects_tmobile(self):
        assert detect_carrier("t-mobile service is terrible") == "tmobile"

    def test_detects_att(self):
        assert detect_carrier("at&t keeps dropping my calls") == "att"

    def test_returns_none_for_unrelated(self):
        assert detect_carrier("I love pizza so much") is None

    def test_detects_via_handle(self):
        assert detect_carrier("hey @TMobileHelp my data is slow") == "tmobile"


# ── X adapter ──────────────────────────────────────────────────────────────


class TestXAdapter:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_returns_signals(self):
        redis = _mock_redis(cap=100, newest_id=None)
        adapter = XAdapter(redis_client=redis)

        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(200, json=_tweet_response())
        )

        signals = await adapter.fetch()
        assert len(signals) == 1
        assert signals[0].source == "x"
        assert signals[0].source_id == "99999"

    @pytest.mark.asyncio
    @respx.mock
    async def test_cursor_advances_after_fetch(self):
        redis = _mock_redis(cap=0, newest_id=None)
        adapter = XAdapter(redis_client=redis)

        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(200, json=_tweet_response(newest_id="99999"))
        )

        await adapter.fetch()
        # Verify cursor was written
        redis.set.assert_awaited_once()
        call_args = redis.set.call_args
        assert call_args[0][1] == "99999"

    @pytest.mark.asyncio
    @respx.mock
    async def test_since_id_used_when_cursor_exists(self):
        redis = _mock_redis(cap=0, newest_id="50000")
        adapter = XAdapter(redis_client=redis)

        route = respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(200, json=_tweet_response())
        )

        await adapter.fetch()
        request = route.calls[0].request
        assert "since_id=50000" in str(request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_author_handle_is_hashed(self):
        redis = _mock_redis()
        adapter = XAdapter(redis_client=redis)

        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(200, json=_tweet_response())
        )

        signals = await adapter.fetch()
        assert signals[0].author_handle == hash_handle("angry_customer")
        assert "angry_customer" not in signals[0].author_handle

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_returns_empty_list(self):
        redis = _mock_redis()
        adapter = XAdapter(redis_client=redis)

        respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )

        signals = await adapter.fetch()
        assert signals == []
        assert adapter._consecutive_errors == 1

    @pytest.mark.asyncio
    async def test_cap_alert_at_80_percent(self, caplog):
        redis = _mock_redis(cap=12001)  # 80.007% of 15000
        adapter = XAdapter(redis_client=redis)

        with respx.mock:
            respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
                return_value=httpx.Response(200, json={"data": [], "meta": {}})
            )
            # Should not raise; warning is logged
            signals = await adapter.fetch()
        assert signals == []

    @pytest.mark.asyncio
    async def test_cap_exhausted_raises(self):
        redis = _mock_redis(cap=15000)
        adapter = XAdapter(redis_client=redis)
        with pytest.raises(RuntimeError, match="cap exhausted"):
            await adapter._fetch_recent_search()

    def test_query_contains_all_carriers(self):
        query = _build_query()
        assert "verizon" in query
        assert "t-mobile" in query.lower() or "tmobile" in query.lower()
        assert "att" in query.lower() or "at&t" in query.lower()
        assert "-is:retweet" in query

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        adapter = XAdapter(redis_client=_mock_redis(cap=1000))
        health = await adapter.health_check()
        assert health.status == "HEALTHY"
        assert health.monthly_cap_used == 1000

    @pytest.mark.asyncio
    async def test_health_check_degraded_at_80pct(self):
        adapter = XAdapter(redis_client=_mock_redis(cap=12500))
        health = await adapter.health_check()
        assert health.status == "DEGRADED"


# ── Reddit adapter ──────────────────────────────────────────────────────────


class TestRedditAdapter:
    def test_is_relevant_complaint(self):
        assert _is_relevant("My verizon signal keeps dropping") is True

    def test_is_relevant_no_carrier(self):
        assert _is_relevant("signal keeps dropping in my area") is False

    def test_is_relevant_no_complaint_keyword(self):
        assert _is_relevant("verizon is amazing and perfect") is False

    @pytest.mark.asyncio
    async def test_fetch_with_mock_praw(self):
        mock_reddit = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "post123"
        mock_post.title = "Verizon billing issue overcharged me"
        mock_post.selftext = "They charged me twice this month"
        mock_post.author = MagicMock(__str__=lambda self: "user123")
        mock_post.permalink = "/r/verizon/comments/post123"
        mock_post.created_utc = 1700000000.0
        mock_post.score = 42
        mock_post.num_comments = 7
        mock_post.link_flair_text = "Billing"
        mock_post.subreddit = MagicMock(display_name="verizon")

        mock_subreddit = MagicMock()
        mock_subreddit.new.return_value = [mock_post]
        mock_reddit.subreddit.return_value = mock_subreddit

        adapter = RedditAdapter(praw_reddit=mock_reddit)
        signals = await adapter.fetch()

        assert len(signals) == 1
        assert signals[0].source == "reddit"
        assert signals[0].source_id == "post123"
        assert signals[0].carrier_hint == "verizon"
        assert signals[0].author_handle == hash_handle("user123")

    @pytest.mark.asyncio
    async def test_irrelevant_posts_filtered(self):
        mock_reddit = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "post999"
        mock_post.title = "I love my new phone"
        mock_post.selftext = ""
        mock_post.author = MagicMock(__str__=lambda self: "happy_user")
        mock_post.permalink = "/r/tmobile/comments/post999"
        mock_post.created_utc = 1700000000.0
        mock_post.score = 1
        mock_post.num_comments = 0
        mock_post.link_flair_text = None
        mock_post.subreddit = MagicMock(display_name="tmobile")
        mock_reddit.subreddit.return_value = MagicMock(new=MagicMock(return_value=[mock_post]))

        adapter = RedditAdapter(praw_reddit=mock_reddit)
        signals = await adapter.fetch()
        assert signals == []


# ── FeedAdapter base ────────────────────────────────────────────────────────


class TestFeedAdapterBase:
    def test_make_signal_hashes_handle(self):
        adapter = XAdapter(redis_client=None)
        signal = adapter._make_signal(
            source="x",
            source_id="tweet-1",
            author_handle="RealUsername",
            content="My att bill is wrong",
            url="https://x.com/i/web/status/tweet-1",
            posted_at=datetime.now(UTC),
        )
        assert signal.author_handle == hash_handle("RealUsername")
        assert "RealUsername" not in signal.author_handle

    def test_make_signal_sanitises_pii(self):
        adapter = XAdapter(redis_client=None)
        signal = adapter._make_signal(
            source="x",
            source_id="tweet-2",
            author_handle="user",
            content="Call me at 555-867-5309 about my verizon bill",
            url="https://x.com/i/web/status/tweet-2",
            posted_at=datetime.now(UTC),
        )
        assert "555-867-5309" not in signal.content
        assert "[PHONE]" in signal.content

    def test_content_hash_deterministic(self):
        h1 = FeedAdapter.content_hash("same content")
        h2 = FeedAdapter.content_hash("same content")
        assert h1 == h2

    def test_content_hash_unique(self):
        assert FeedAdapter.content_hash("content A") != FeedAdapter.content_hash("content B")
