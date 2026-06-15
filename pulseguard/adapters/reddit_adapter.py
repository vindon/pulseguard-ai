import asyncio
from datetime import UTC, datetime
from typing import Any

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS, detect_carrier
from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.models.adapters import AdapterHealth, CarrierConfig
from pulseguard.models.signals import RawSignal

logger = get_logger(__name__)

_MONITORED_SUBREDDITS = list(
    {sub for config in CARRIER_CONFIGS.values() for sub in config.subreddits}
) + ["NoContract", "mobilecarriers", "techsupport"]

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
    return any(kw in text_lower for kw in _COMPLAINT_KEYWORDS) and detect_carrier(text) is not None


class RedditAdapter(FeedAdapter):
    name = "reddit"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self, praw_reddit: Any = None) -> None:
        self._reddit = praw_reddit
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None

    def _init_praw(self) -> Any:
        import praw

        return praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
            read_only=True,
        )

    async def fetch(self) -> list[RawSignal]:
        return await asyncio.get_event_loop().run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> list[RawSignal]:
        if self._reddit is None:
            self._reddit = self._init_praw()

        signals: list[RawSignal] = []
        try:
            subreddit_str = "+".join(_MONITORED_SUBREDDITS)
            subreddit = self._reddit.subreddit(subreddit_str)
            # Use .new() with a reasonable limit for polling; streaming is used in orchestrator
            for post in subreddit.new(limit=100):
                text = f"{post.title} {post.selftext}"
                if not _is_relevant(text):
                    continue
                signals.append(
                    self._make_signal(
                        source="reddit",
                        source_id=post.id,
                        author_handle=str(post.author) if post.author else "deleted",
                        content=text,
                        url=f"https://reddit.com{post.permalink}",
                        posted_at=datetime.fromtimestamp(post.created_utc, tz=UTC),
                        carrier_hint=detect_carrier(text),
                        adapter_metadata={
                            "subreddit": post.subreddit.display_name,
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "flair": post.link_flair_text,
                        },
                    )
                )
            self._consecutive_errors = 0
            self._last_successful_fetch = datetime.now(UTC)
        except Exception as exc:
            self._consecutive_errors += 1
            logger.error(
                "reddit_adapter_error", error=str(exc), consecutive=self._consecutive_errors
            )
        return signals

    async def stream_submissions(self) -> None:
        """Long-running streaming loop — called by orchestrator, not fetch()."""
        from pulseguard.orchestrator.event_bus import publish_raw_signal

        if self._reddit is None:
            self._reddit = await asyncio.get_event_loop().run_in_executor(None, self._init_praw)

        def _stream() -> None:
            subreddit_str = "+".join(_MONITORED_SUBREDDITS)
            subreddit = self._reddit.subreddit(subreddit_str)
            for post in subreddit.stream.submissions(skip_existing=True):
                text = f"{post.title} {post.selftext}"
                if not _is_relevant(text):
                    continue
                signal = self._make_signal(
                    source="reddit",
                    source_id=post.id,
                    author_handle=str(post.author) if post.author else "deleted",
                    content=text,
                    url=f"https://reddit.com{post.permalink}",
                    posted_at=datetime.fromtimestamp(post.created_utc, tz=UTC),
                    carrier_hint=detect_carrier(text),
                    adapter_metadata={
                        "subreddit": post.subreddit.display_name,
                        "score": post.score,
                        "num_comments": post.num_comments,
                    },
                )
                asyncio.get_event_loop().run_until_complete(publish_raw_signal(signal))

        await asyncio.get_event_loop().run_in_executor(None, _stream)

    async def health_check(self) -> AdapterHealth:
        status = "HEALTHY"
        if self._consecutive_errors >= 5:
            status = "DOWN"
        elif self._consecutive_errors >= 3:
            status = "DEGRADED"
        return AdapterHealth(
            adapter_name="reddit",
            status=status,
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
        )
