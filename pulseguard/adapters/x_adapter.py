from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import redis.asyncio as aioredis

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS
from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.models.adapters import AdapterHealth, CarrierConfig
from pulseguard.models.signals import RawSignal

logger = get_logger(__name__)

_RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
_STREAM_URL = "https://api.twitter.com/2/tweets/search/stream"
_REDIS_CAP_KEY = "pulseguard:x:monthly_reads"
_REDIS_CURSOR_KEY = "pulseguard:x:newest_id"

_TWEET_FIELDS = "id,text,author_id,created_at,entities,public_metrics"
_EXPANSIONS = "author_id"
_USER_FIELDS = "username"

_COMPLAINT_KEYWORDS = (
    'problem OR issue OR outage OR billing OR "not working" OR "can\'t" OR slow OR dropped'
)


def _build_query() -> str:
    """Build a carrier-agnostic X search query from all configured carriers."""
    brand_terms = []
    for config in CARRIER_CONFIGS.values():
        brand_terms.extend(config.keywords)
    brand_clause = " OR ".join(f'"{t}"' if " " in t else t for t in brand_terms)
    return f"({brand_clause}) ({_COMPLAINT_KEYWORDS}) " "-is:retweet lang:en"


class XAdapter(FeedAdapter):
    name = "x"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self, redis_client: aioredis.Redis[str] | None = None) -> None:
        self._redis = redis_client
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
            timeout=30.0,
        )

    async def fetch(self) -> list[RawSignal]:
        if settings.x_api_tier == "pro":
            return await self._fetch_stream()
        return await self._fetch_recent_search()

    async def _fetch_recent_search(self) -> list[RawSignal]:
        await self._check_cap()
        newest_id = await self._get_cursor()

        params: dict[str, Any] = {
            "query": _build_query(),
            "max_results": 100,
            "tweet.fields": _TWEET_FIELDS,
            "expansions": _EXPANSIONS,
            "user.fields": _USER_FIELDS,
        }
        if newest_id:
            params["since_id"] = newest_id

        try:
            resp = await self._client.get(_RECENT_SEARCH_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._consecutive_errors += 1
            logger.error(
                "x_adapter_fetch_error", error=str(exc), consecutive=self._consecutive_errors
            )
            return []

        data = resp.json()
        tweets = data.get("data", [])
        users = {u["id"]: u["username"] for u in data.get("includes", {}).get("users", [])}
        meta = data.get("meta", {})

        if not tweets:
            return []

        # Advance cursor to newest tweet seen
        if meta.get("newest_id"):
            await self._set_cursor(meta["newest_id"])

        await self._increment_cap(len(tweets))
        self._consecutive_errors = 0
        self._last_successful_fetch = datetime.now(UTC)

        signals: list[RawSignal] = []
        for tweet in tweets:
            username = users.get(tweet.get("author_id", ""), "unknown")
            created_at = datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))
            signals.append(
                self._make_signal(
                    source="x",
                    source_id=tweet["id"],
                    author_handle=username,
                    content=tweet["text"],
                    url=f"https://x.com/i/web/status/{tweet['id']}",
                    posted_at=created_at,
                    adapter_metadata={
                        "public_metrics": tweet.get("public_metrics", {}),
                        "author_id": tweet.get("author_id"),
                    },
                )
            )

        logger.info("x_adapter_fetched", count=len(signals), newest_id=meta.get("newest_id"))
        return signals

    async def _fetch_stream(self) -> list[RawSignal]:
        # Pro tier: filtered stream — same interface, different transport
        # Used when X_API_TIER=pro. Collects events for one poll cycle duration.
        signals: list[RawSignal] = []
        try:
            async with self._client.stream(
                "GET",
                _STREAM_URL,
                params={
                    "tweet.fields": _TWEET_FIELDS,
                    "expansions": _EXPANSIONS,
                    "user.fields": _USER_FIELDS,
                },
            ) as response:
                response.raise_for_status()
                # Collect for a short window then return (non-blocking for orchestrator)
                deadline = asyncio.get_event_loop().time() + 10
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    import json

                    event = json.loads(line)
                    tweet = event.get("data", {})
                    users = {
                        u["id"]: u["username"] for u in event.get("includes", {}).get("users", [])
                    }
                    if not tweet.get("id"):
                        continue
                    username = users.get(tweet.get("author_id", ""), "unknown")
                    created_at = datetime.fromisoformat(
                        tweet.get("created_at", datetime.now(UTC).isoformat()).replace(
                            "Z", "+00:00"
                        )
                    )
                    signals.append(
                        self._make_signal(
                            source="x",
                            source_id=tweet["id"],
                            author_handle=username,
                            content=tweet.get("text", ""),
                            url=f"https://x.com/i/web/status/{tweet['id']}",
                            posted_at=created_at,
                            adapter_metadata={"public_metrics": tweet.get("public_metrics", {})},
                        )
                    )
                    if asyncio.get_event_loop().time() > deadline:
                        break
        except httpx.HTTPError as exc:
            self._consecutive_errors += 1
            logger.error("x_stream_error", error=str(exc))
        return signals

    async def health_check(self) -> AdapterHealth:
        cap_used = await self._get_cap_used()
        cap_pct = (cap_used / settings.x_monthly_cap) * 100

        if cap_pct >= 100:
            status = "DOWN"
        elif cap_pct >= 80 or self._consecutive_errors >= 3:
            status = "DEGRADED"
        elif self._consecutive_errors >= 5:
            status = "DOWN"
        else:
            status = "HEALTHY"

        return AdapterHealth(
            adapter_name="x",
            status=status,
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
            monthly_cap_used=cap_used,
            monthly_cap_limit=settings.x_monthly_cap,
            error_message=f"Cap at {cap_pct:.0f}%" if cap_pct >= 80 else None,
        )

    async def _check_cap(self) -> None:
        used = await self._get_cap_used()
        if used >= settings.x_monthly_cap:
            raise RuntimeError(
                f"X monthly read cap exhausted ({used}/{settings.x_monthly_cap}). "
                "Pausing adapter until next billing cycle."
            )
        if used >= settings.x_monthly_cap * 0.8:
            logger.warning(
                "x_cap_warning",
                used=used,
                cap=settings.x_monthly_cap,
                pct=round(used / settings.x_monthly_cap * 100, 1),
            )

    async def _get_cap_used(self) -> int:
        if self._redis is None:
            return 0
        val = await self._redis.get(_REDIS_CAP_KEY)
        return int(val) if val else 0

    async def _increment_cap(self, count: int) -> None:
        if self._redis is None:
            return
        await self._redis.incrby(_REDIS_CAP_KEY, count)

    async def _get_cursor(self) -> str | None:
        if self._redis is None:
            return None
        return await self._redis.get(_REDIS_CURSOR_KEY)

    async def _set_cursor(self, newest_id: str) -> None:
        if self._redis is None:
            return
        await self._redis.set(_REDIS_CURSOR_KEY, newest_id)

    async def close(self) -> None:
        await self._client.aclose()
