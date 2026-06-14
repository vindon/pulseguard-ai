import asyncio
from datetime import UTC, datetime, timedelta

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS, CarrierConfig
from pulseguard.logging_config import get_logger
from pulseguard.models.adapters import AdapterHealth
from pulseguard.models.signals import RawSignal

logger = get_logger(__name__)

_CUTOFF_HOURS = 24


class GooglePlayAdapter(FeedAdapter):
    name = "google_play"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self) -> None:
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None

    async def fetch(self) -> list[RawSignal]:
        return await asyncio.get_event_loop().run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> list[RawSignal]:
        from google_play_scraper import Sort, reviews

        signals: list[RawSignal] = []
        cutoff = datetime.now(UTC) - timedelta(hours=_CUTOFF_HOURS)

        for carrier_name, config in CARRIER_CONFIGS.items():
            if not config.play_store_id:
                continue
            try:
                result, _ = reviews(
                    config.play_store_id,
                    lang="en",
                    country="us",
                    sort=Sort.NEWEST,
                    count=100,
                )
                for review in result:
                    at: datetime = review.get("at") or datetime.now(UTC)
                    if at.tzinfo is None:
                        at = at.replace(tzinfo=UTC)
                    if at < cutoff:
                        continue
                    # Only ingest negative reviews (rating ≤ 3 = complaint signal)
                    if review.get("score", 5) > 3:
                        continue
                    signals.append(
                        self._make_signal(
                            source="google_play",
                            source_id=review.get("reviewId", ""),
                            author_handle=review.get("userName", "anonymous"),
                            content=review.get("content", ""),
                            url=f"https://play.google.com/store/apps/details?id={config.play_store_id}",
                            posted_at=at,
                            carrier_hint=carrier_name,
                            adapter_metadata={
                                "rating": review.get("score"),
                                "app_version": review.get("appVersion"),
                                "thumbs_up": review.get("thumbsUpCount", 0),
                            },
                        )
                    )
            except Exception as exc:
                self._consecutive_errors += 1
                logger.error("google_play_fetch_error", carrier=carrier_name, error=str(exc))
                continue

        if signals or self._consecutive_errors == 0:
            self._consecutive_errors = 0
            self._last_successful_fetch = datetime.now(UTC)
        logger.info("google_play_fetched", count=len(signals))
        return signals

    async def health_check(self) -> AdapterHealth:
        status = "HEALTHY"
        if self._consecutive_errors >= 5:
            status = "DOWN"
        elif self._consecutive_errors >= 3:
            status = "DEGRADED"
        return AdapterHealth(
            adapter_name="google_play",
            status=status,  # type: ignore[arg-type]
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
        )
