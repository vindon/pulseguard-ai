import hashlib
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pulseguard.models.adapters import AdapterHealth, CarrierConfig
from pulseguard.models.signals import RawSignal
from pulseguard.security.sanitise import hash_handle, sanitise_pii


class FeedAdapter(ABC):
    name: str
    carrier_configs: list[CarrierConfig]

    @abstractmethod
    async def fetch(self) -> list[RawSignal]:
        """Fetch new signals since last run. Must be idempotent."""

    @abstractmethod
    async def health_check(self) -> AdapterHealth:
        """Return current adapter health: HEALTHY | DEGRADED | DOWN + reason."""

    def _make_signal(
        self,
        source: str,
        source_id: str,
        author_handle: str,
        content: str,
        url: str,
        posted_at: datetime,
        carrier_hint: str | None = None,
        adapter_metadata: dict[str, Any] | None = None,
    ) -> RawSignal:
        """Build a RawSignal with PII sanitisation and handle hashing applied."""
        return RawSignal(
            signal_id=str(uuid.uuid4()),
            source=source,
            source_id=source_id,
            carrier_hint=carrier_hint,
            author_handle=hash_handle(author_handle),
            content=sanitise_pii(content),
            url=url,
            posted_at=posted_at,
            ingested_at=datetime.now(UTC),
            adapter_metadata=adapter_metadata or {},
        )

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()
