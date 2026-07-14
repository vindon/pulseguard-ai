"""
Quora adapter — Quora has no public API, so this goes through SerpAPI's Google
Search REST endpoint (`site:quora.com ...`), the path the original stub
recommended as production-ready (stable, respects robots.txt, no scraping).

Endpoint: https://serpapi.com/search.json
  ?engine=google&q=site:quora.com+{carrier}+(problem+OR+issue+OR+complaint...)
  &tbs=qdr:d&num=20&api_key={SERPAPI_API_KEY}

`tbs=qdr:d` restricts results to the past 24 hours server-side, so no
client-side cutoff filtering is needed (unlike the other adapters). Quora
search results carry no stable native ID, so `source_id` is derived from
FeedAdapter.content_hash(url) to stay idempotent across polls. SerpAPI does
not reliably expose an exact publish timestamp for organic web results, so
`posted_at` falls back to ingestion time — documented limitation, not a bug.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS
from pulseguard.config import settings
from pulseguard.logging_config import get_logger
from pulseguard.models.adapters import AdapterHealth, CarrierConfig
from pulseguard.models.signals import RawSignal

logger = get_logger(__name__)

_SERPAPI_URL = "https://serpapi.com/search.json"
_COMPLAINT_CLAUSE = "(problem OR issue OR complaint OR billing OR outage OR scam OR overcharged)"


def _extract_author(snippet: str) -> str:
    """Best-effort author extraction from a SerpAPI snippet. Quora snippets are
    often formatted like 'Jane Doe: I had the same problem...' — fall back to
    'anonymous' when no such pattern is present so a bad snippet never raises.
    """
    prefix = snippet[:40]
    if ":" in prefix:
        candidate = prefix.split(":", 1)[0].strip()
        if 0 < len(candidate) <= 40:
            return candidate
    return "anonymous"


class QuoraAdapter(FeedAdapter):
    name = "quora"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self) -> None:
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None

    async def fetch(self) -> list[RawSignal]:
        signals: list[RawSignal] = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for carrier_name, config in CARRIER_CONFIGS.items():
                try:
                    carrier_signals = await self._fetch_carrier(client, carrier_name, config)
                    signals.extend(carrier_signals)
                    self._consecutive_errors = 0
                    self._last_successful_fetch = datetime.now(UTC)
                except Exception as exc:
                    self._consecutive_errors += 1
                    logger.error("quora_fetch_error", carrier=carrier_name, error=str(exc))

        logger.info("quora_fetched", count=len(signals))
        return signals

    async def _fetch_carrier(
        self,
        client: httpx.AsyncClient,
        carrier_name: str,
        config: CarrierConfig,
    ) -> list[RawSignal]:
        query = f"site:quora.com {config.display_name} {_COMPLAINT_CLAUSE}"
        params: dict[str, Any] = {
            "engine": "google",
            "q": query,
            "tbs": "qdr:d",  # past 24 hours only
            "num": 20,
            "api_key": settings.serpapi_api_key,
        }

        resp = await client.get(_SERPAPI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        signals: list[RawSignal] = []
        for result in data.get("organic_results", []):
            url = result.get("link", "")
            if not url or "quora.com" not in url:
                continue

            title = result.get("title", "")
            snippet = result.get("snippet", "")
            content = f"{title} {snippet}".strip()
            if not content:
                continue

            signals.append(
                self._make_signal(
                    source="quora",
                    source_id=self.content_hash(url),
                    author_handle=_extract_author(snippet),
                    content=content,
                    url=url,
                    posted_at=datetime.now(UTC),
                    carrier_hint=carrier_name,
                    adapter_metadata={"position": result.get("position")},
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
            adapter_name="quora",
            status=status,
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
        )
