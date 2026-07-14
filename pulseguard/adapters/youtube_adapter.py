"""
YouTube Comments adapter — uses the YouTube Data API v3 (no third-party client
library; a plain httpx GET keeps this consistent with app_store_adapter.py).

Endpoint: https://www.googleapis.com/youtube/v3/commentThreads
  ?part=snippet&allThreadsRelatedToChannelId={channel_id}&order=time
  &maxResults=100&textFormat=plainText&key={YOUTUBE_API_KEY}

`allThreadsRelatedToChannelId` returns comment threads across all of a channel's
videos in one paginated call, so we don't need to first enumerate uploads.
Requires YOUTUBE_API_KEY (free tier: 10,000 quota units/day; commentThreads.list
costs 1 unit per page of up to 100 results). No OAuth needed — public data only.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS
from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.models.adapters import AdapterHealth, CarrierConfig
from pulseguard.models.signals import RawSignal

logger = get_logger(__name__)

_COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
_CUTOFF_HOURS = 24
_MAX_PAGES = 5  # Each page = up to 100 comments; cap at 500 to bound quota spend

_COMPLAINT_KEYWORDS = {
    "problem",
    "issue",
    "outage",
    "billing",
    "not working",
    "slow",
    "drop",
    "can't",
    "error",
    "broken",
    "awful",
    "terrible",
    "overcharged",
    "scam",
    "cancel",
    "switching",
}


def _is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _COMPLAINT_KEYWORDS)


class YouTubeAdapter(FeedAdapter):
    name = "youtube"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self) -> None:
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None

    async def fetch(self) -> list[RawSignal]:
        signals: list[RawSignal] = []
        cutoff = datetime.now(UTC) - timedelta(hours=_CUTOFF_HOURS)

        async with httpx.AsyncClient(timeout=15.0) as client:
            for carrier_name, config in CARRIER_CONFIGS.items():
                if not config.youtube_channel_id:
                    continue
                try:
                    carrier_signals = await self._fetch_carrier(
                        client, carrier_name, config.youtube_channel_id, cutoff
                    )
                    signals.extend(carrier_signals)
                    self._consecutive_errors = 0
                    self._last_successful_fetch = datetime.now(UTC)
                except Exception as exc:
                    self._consecutive_errors += 1
                    logger.error("youtube_fetch_error", carrier=carrier_name, error=str(exc))

        logger.info("youtube_fetched", count=len(signals))
        return signals

    async def _fetch_carrier(
        self,
        client: httpx.AsyncClient,
        carrier_name: str,
        channel_id: str,
        cutoff: datetime,
    ) -> list[RawSignal]:
        signals: list[RawSignal] = []
        page_token: str | None = None

        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {
                "part": "snippet",
                "allThreadsRelatedToChannelId": channel_id,
                "order": "time",
                "maxResults": 100,
                "textFormat": "plainText",
                "key": settings.youtube_api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(_COMMENT_THREADS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                thread_snippet = item.get("snippet", {})
                top_comment = thread_snippet.get("topLevelComment", {})
                comment_snippet = top_comment.get("snippet", {})
                text = comment_snippet.get("textOriginal") or comment_snippet.get("textDisplay", "")

                published_str = comment_snippet.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except ValueError:
                    published_at = datetime.now(UTC)

                if published_at < cutoff:
                    # order=time -> newest first; once we're past the cutoff
                    # everything remaining on this and later pages is older.
                    return signals

                if not _is_relevant(text):
                    continue

                comment_id = top_comment.get("id") or item.get("id", "")
                author = comment_snippet.get("authorDisplayName", "anonymous")
                video_id = thread_snippet.get("videoId", "")

                signals.append(
                    self._make_signal(
                        source="youtube",
                        source_id=comment_id,
                        author_handle=author,
                        content=text,
                        url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
                        posted_at=published_at,
                        carrier_hint=carrier_name,
                        adapter_metadata={
                            "video_id": video_id,
                            "like_count": comment_snippet.get("likeCount", 0),
                            "total_reply_count": thread_snippet.get("totalReplyCount", 0),
                        },
                    )
                )

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return signals

    async def health_check(self) -> AdapterHealth:
        status = "HEALTHY"
        if self._consecutive_errors >= 5:
            status = "DOWN"
        elif self._consecutive_errors >= 3:
            status = "DEGRADED"
        return AdapterHealth(
            adapter_name="youtube",
            status=status,
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
        )
