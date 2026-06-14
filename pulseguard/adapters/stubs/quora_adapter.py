"""
Quora adapter — stub.

Quora has no public API. Two implementation paths when ready:
1. SerpAPI Google search: site:quora.com (verizon OR t-mobile OR att) (problem OR issue)
   - Requires SERPAPI_API_KEY; cost ~$50/mo for moderate volume
2. Unofficial Quora scraping via httpx + BeautifulSoup (fragile, may violate ToS)

Recommended: SerpAPI path — stable, respects robots.txt, defensible in production.
"""

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS, CarrierConfig
from pulseguard.models.adapters import AdapterHealth
from pulseguard.models.signals import RawSignal


class QuoraAdapter(FeedAdapter):
    name = "quora"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    async def fetch(self) -> list[RawSignal]:
        raise NotImplementedError(
            "QuoraAdapter is a stub. Implement via SerpAPI or scraping. "
            "See module docstring for guidance."
        )

    async def health_check(self) -> AdapterHealth:
        return AdapterHealth(
            adapter_name="quora",
            status="DOWN",
            error_message="Stub — not yet implemented",
        )
