from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RawSignal(BaseModel):
    signal_id: str
    source: Literal["x", "reddit", "google_play", "app_store", "trustpilot", "youtube", "quora"]
    source_id: str
    carrier_hint: str | None = None
    author_handle: str  # SHA-256 hashed before storage
    content: str  # PII-sanitised before storage
    url: str
    posted_at: datetime
    ingested_at: datetime
    adapter_metadata: dict[str, Any] = Field(default_factory=dict)


class ValidatedSignal(BaseModel):
    signal_id: str
    raw: RawSignal
    detected_carrier: str
    is_valid: bool
    validity_reason: str
    content_hash: str  # SHA-256 of sanitised content for deduplication
    sentinel_trace_id: str
    validated_at: datetime
