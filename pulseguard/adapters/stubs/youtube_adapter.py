"""
YouTube Comments adapter — stub.

Interface is fully defined; implementation is deferred until YouTube Data API v3
quota allocation is confirmed (free tier: 10,000 units/day).

When implementing:
- Use googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
- Monitor official carrier channels: UCq5p3aOFCNkDFg3ZLNTULpw (Verizon), etc.
- Pull commentThreads.list on recent uploads; filter by complaint keywords
- Each unit = 1 quota; commentThreads.list costs 1 unit per page of 100 results
"""

from pulseguard.adapters.base import FeedAdapter
from pulseguard.adapters.carrier_configs import CARRIER_CONFIGS, CarrierConfig
from pulseguard.models.adapters import AdapterHealth
from pulseguard.models.signals import RawSignal


class YouTubeAdapter(FeedAdapter):
    name = "youtube"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    async def fetch(self) -> list[RawSignal]:
        raise NotImplementedError(
            "YouTubeAdapter is a stub. Implement using YouTube Data API v3. "
            "See module docstring for guidance."
        )

    async def health_check(self) -> AdapterHealth:
        return AdapterHealth(
            adapter_name="youtube",
            status="DOWN",
            error_message="Stub — not yet implemented",
        )
