"""Publishes an approved draft reply back to X. Requires OAuth 1.0a
user-context credentials (distinct from XAdapter's read-only app-only
bearer token) — see config.py's x_api_key/x_api_secret/x_access_token/
x_access_token_secret. Single-account credentials, matching Phase 0's
single-tenant-per-deployment scope (spec §15); per-tenant OAuth is a
Phase 2 concern once multi-tenancy exists."""

import json
from typing import Any

import httpx
from requests_oauthlib import OAuth1

from pulseguard.config import settings
from pulseguard.logging_config import get_logger

logger = get_logger(__name__)

_TWEETS_URL = "https://api.twitter.com/2/tweets"


class PublishError(Exception):
    """Raised when a reply could not be published — credentials missing,
    or the platform API rejected the request."""


def _sign_request(method: str, url: str, headers: dict[str, str]) -> dict[str, str]:
    """Compute OAuth 1.0a signed headers for a request.

    `requests_oauthlib.OAuth1` cannot be passed directly as httpx's `auth=`
    kwarg: its `__call__` expects a `requests.PreparedRequest` (it invokes
    `.prepare_headers()` / `.prepare_body()`, which `httpx.Request` doesn't
    have) — confirmed by an `AttributeError` when tested against a real
    httpx client. Its underlying `oauthlib.oauth1.Client`, however, is
    HTTP-library-agnostic: `.sign(uri, http_method, headers=...)` returns
    the signed URI/headers/body without touching any `requests` internals,
    so we call it directly and attach the resulting `Authorization` header
    ourselves.
    """
    oauth1 = OAuth1(
        settings.x_api_key,
        client_secret=settings.x_api_secret,
        resource_owner_key=settings.x_access_token,
        resource_owner_secret=settings.x_access_token_secret,
    )
    _signed_url, signed_headers, _signed_body = oauth1.client.sign(
        url, http_method=method, headers=headers
    )
    return dict(signed_headers)


async def post_reply(in_reply_to_tweet_id: str, text: str) -> dict[str, Any]:
    if not (
        settings.x_api_key
        and settings.x_api_secret
        and settings.x_access_token
        and settings.x_access_token_secret
    ):
        raise PublishError("X publishing credentials not configured")

    payload = {"text": text, "reply": {"in_reply_to_tweet_id": in_reply_to_tweet_id}}
    body = json.dumps(payload).encode("utf-8")
    headers = _sign_request("POST", _TWEETS_URL, {"Content-Type": "application/json"})

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(_TWEETS_URL, content=body, headers=headers)
        if resp.status_code >= 400:
            raise PublishError(f"X API error {resp.status_code}: {resp.text}")
        data = resp.json()

    tweet_id = data.get("data", {}).get("id")
    logger.info("x_reply_posted", in_reply_to=in_reply_to_tweet_id, tweet_id=tweet_id)
    return {"posted": True, "tweet_id": tweet_id}
