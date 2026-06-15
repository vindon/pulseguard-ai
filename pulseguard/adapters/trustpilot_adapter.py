import asyncio
import time
from datetime import UTC, datetime, timedelta
from itertools import cycle
from typing import Any

import httpx

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS
from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.models.adapters import AdapterHealth, CarrierConfig
from pulseguard.models.signals import RawSignal

logger = get_logger(__name__)

_BASE_URL = "https://www.trustpilot.com/api/categoriespages"
_REVIEWS_URL = "https://www.trustpilot.com/api/public/v1/reviews/query"
_CUTOFF_HOURS = 24

_USER_AGENTS = cycle(
    [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    ]
)


class TrustpilotAdapter(FeedAdapter):
    name = "trustpilot"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self) -> None:
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None

    async def fetch(self) -> list[RawSignal]:
        return await asyncio.get_event_loop().run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> list[RawSignal]:
        signals: list[RawSignal] = []
        cutoff = datetime.now(UTC) - timedelta(hours=_CUTOFF_HOURS)

        for carrier_name, config in CARRIER_CONFIGS.items():
            if not config.trustpilot_slug:
                continue
            try:
                reviews = self._fetch_carrier_reviews(config.trustpilot_slug, cutoff)
                for review in reviews:
                    signals.append(
                        self._make_signal(
                            source="trustpilot",
                            source_id=review["id"],
                            author_handle=review.get("consumer", {}).get(
                                "displayName", "anonymous"
                            ),
                            content=f"{review.get('title', '')} {review.get('text', '')}".strip(),
                            url=f"https://www.trustpilot.com/reviews/{review['id']}",
                            posted_at=datetime.fromisoformat(
                                review["createdAt"].replace("Z", "+00:00")
                            ),
                            carrier_hint=carrier_name,
                            adapter_metadata={
                                "rating": review.get("stars"),
                                "verified": review.get("isVerified", False),
                            },
                        )
                    )
                time.sleep(settings.trustpilot_request_delay_seconds)
            except Exception as exc:
                self._consecutive_errors += 1
                logger.error("trustpilot_fetch_error", carrier=carrier_name, error=str(exc))
                continue

        self._consecutive_errors = 0
        self._last_successful_fetch = datetime.now(UTC)
        logger.info("trustpilot_fetched", count=len(signals))
        return signals

    def _fetch_carrier_reviews(self, slug: str, cutoff: datetime) -> list[dict[str, Any]]:
        ua = next(_USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "application/json",
        }
        reviews: list[dict[str, Any]] = []
        page = 1
        with httpx.Client(headers=headers, timeout=15.0) as client:
            while True:
                resp = client.get(
                    "https://www.trustpilot.com/api/public/v1/reviews/query",
                    params={
                        "domain": f"{slug}.com",
                        "page": page,
                        "perPage": 20,
                        "orderBy": "createdat.desc",
                        "stars": "1,2,3",  # complaint signals only
                    },
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                batch = data.get("reviews", [])
                if not batch:
                    break
                for review in batch:
                    created = review.get("createdAt", "")
                    if not created:
                        continue
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if dt < cutoff:
                        return reviews  # sorted newest first; stop early
                    reviews.append(review)
                time.sleep(settings.trustpilot_request_delay_seconds)
                if not data.get("links", {}).get("next"):
                    break
                page += 1
        return reviews

    async def health_check(self) -> AdapterHealth:
        status = "HEALTHY"
        if self._consecutive_errors >= 5:
            status = "DOWN"
        elif self._consecutive_errors >= 3:
            status = "DEGRADED"
        return AdapterHealth(
            adapter_name="trustpilot",
            status=status,
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
        )
