from unittest.mock import patch

import httpx
import pytest
import respx

from pulseguard.publishers.x_publisher import PublishError, post_reply


class TestXPublisher:
    @pytest.mark.asyncio
    async def test_posts_reply_with_correct_payload(self):
        with (
            patch("pulseguard.publishers.x_publisher.settings.x_api_key", "key"),
            patch("pulseguard.publishers.x_publisher.settings.x_api_secret", "secret"),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token", "token"),
            patch(
                "pulseguard.publishers.x_publisher.settings.x_access_token_secret", "token-secret"
            ),
            respx.mock,
        ):
            route = respx.post("https://api.twitter.com/2/tweets").mock(
                return_value=httpx.Response(201, json={"data": {"id": "999", "text": "reply text"}})
            )
            result = await post_reply(in_reply_to_tweet_id="123", text="reply text")

        assert result == {"posted": True, "tweet_id": "999"}
        sent = route.calls[0].request
        import json as _json

        body = _json.loads(sent.content)
        assert body["text"] == "reply text"
        assert body["reply"]["in_reply_to_tweet_id"] == "123"

        # Verify the request was actually OAuth 1.0a signed, not just sent.
        # Assert all six required OAuth 1.0a params so a future regression
        # (e.g. signature_method silently drifting off HMAC-SHA1, or nonce/
        # timestamp being dropped) fails loudly here instead of only at
        # real-pilot publish time.
        auth_header = sent.headers.get("authorization", "")
        assert "OAuth " in auth_header
        assert "oauth_consumer_key=" in auth_header
        assert "oauth_signature=" in auth_header
        assert "oauth_token=" in auth_header
        assert "oauth_nonce=" in auth_header
        assert "oauth_timestamp=" in auth_header
        assert 'oauth_version="1.0"' in auth_header
        assert 'oauth_signature_method="HMAC-SHA1"' in auth_header

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_publish_error(self):
        with (
            patch("pulseguard.publishers.x_publisher.settings.x_api_key", ""),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token", ""),
        ):
            with pytest.raises(PublishError, match="not configured"):
                await post_reply(in_reply_to_tweet_id="123", text="reply text")

    @pytest.mark.asyncio
    async def test_api_error_raises_publish_error(self):
        with (
            patch("pulseguard.publishers.x_publisher.settings.x_api_key", "key"),
            patch("pulseguard.publishers.x_publisher.settings.x_api_secret", "secret"),
            patch("pulseguard.publishers.x_publisher.settings.x_access_token", "token"),
            patch(
                "pulseguard.publishers.x_publisher.settings.x_access_token_secret", "token-secret"
            ),
            respx.mock,
        ):
            respx.post("https://api.twitter.com/2/tweets").mock(
                return_value=httpx.Response(403, json={"detail": "Forbidden"})
            )
            with pytest.raises(PublishError):
                await post_reply(in_reply_to_tweet_id="123", text="reply text")
