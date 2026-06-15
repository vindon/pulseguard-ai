"""
App Store Reviews adapter — uses Apple's public RSS JSON API (no third-party library).

Endpoint: https://itunes.apple.com/{country}/rss/customerreviews/page={n}/id={app_id}/sortby=mostrecent/json
No authentication required. Public data only.
"""

from datetime import UTC, datetime, timedelta

import httpx

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS
from pulseguard.logging_config import get_logger
from pulseguard.models.adapters import AdapterHealth, CarrierConfig
from pulseguard.models.signals import RawSignal

logger = get_logger(__name__)

_BASE_URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
_CUTOFF_HOURS = 24
_MAX_PAGES = 5  # Each page = 50 reviews; cap at 250 to stay within reasonable limits


class AppStoreAdapter(FeedAdapter):
    name = "app_store"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self) -> None:
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None

    async def fetch(self) -> list[RawSignal]:
        signals: list[RawSignal] = []
        cutoff = datetime.now(UTC) - timedelta(hours=_CUTOFF_HOURS)

        async with httpx.AsyncClient(timeout=15.0) as client:
            for carrier_name, config in CARRIER_CONFIGS.items():
                if not config.app_store_id:
                    continue
                try:
                    carrier_signals = await self._fetch_carrier(
                        client, carrier_name, config.app_store_id, cutoff
                    )
                    signals.extend(carrier_signals)
                    self._consecutive_errors = 0
                    self._last_successful_fetch = datetime.now(UTC)
                except Exception as exc:
                    self._consecutive_errors += 1
                    logger.error("app_store_fetch_error", carrier=carrier_name, error=str(exc))

        logger.info("app_store_fetched", count=len(signals))
        return signals

    async def _fetch_carrier(
        self,
        client: httpx.AsyncClient,
        carrier_name: str,
        app_id: str,
        cutoff: datetime,
    ) -> list[RawSignal]:
        signals: list[RawSignal] = []

        for page in range(1, _MAX_PAGES + 1):
            url = _BASE_URL.format(country="us", page=page, app_id=app_id)
            resp = await client.get(url, headers={"Accept": "application/json"})

            if resp.status_code == 404:
                break  # No more pages
            resp.raise_for_status()

            data = resp.json()
            entries = data.get("feed", {}).get("entry", [])
            if not entries:
                break

            # First entry in feed is app metadata (not a review) — skip it
            if page == 1 and isinstance(entries, list) and entries:
                entries = entries[1:]

            for entry in entries:
                updated_str = entry.get("updated", {}).get("label", "")
                try:
                    reviewed_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    reviewed_at = datetime.now(UTC)

                if reviewed_at < cutoff:
                    return signals  # Reviews are newest-first; stop when we pass cutoff

                rating_label = entry.get("im:rating", {}).get("label", "5")
                rating = int(rating_label) if rating_label.isdigit() else 5
                if rating > 3:
                    continue  # Only ingest complaint signals (1-3 stars)

                content = entry.get("content", {}).get("label", "")
                title = entry.get("title", {}).get("label", "")
                author = entry.get("author", {}).get("name", {}).get("label", "anonymous")
                review_id = entry.get("id", {}).get("label", "")
                version = entry.get("im:version", {}).get("label", "")

                signals.append(
                    self._make_signal(
                        source="app_store",
                        source_id=review_id,
                        author_handle=author,
                        content=f"{title} {content}".strip(),
                        url=f"https://apps.apple.com/us/app/id{app_id}",
                        posted_at=reviewed_at,
                        carrier_hint=carrier_name,
                        adapter_metadata={
                            "rating": rating,
                            "app_version": version,
                            "title": title,
                        },
                    )
                )

        return signals

    async def health_check(self) -> AdapterHealth:
        status = "HEALTHY"
        if self._consecutive_errors >= 5:
            status = "DOWN"
        elif self._consecutive_errors >= 3:
            status = "DEGRADED"
        return AdapterHealth(
            adapter_name="app_store",
            status=status,
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
        )
