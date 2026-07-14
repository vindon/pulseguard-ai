from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AdapterHealth(BaseModel):
    adapter_name: str
    status: Literal["HEALTHY", "DEGRADED", "DOWN"]
    last_successful_fetch: datetime | None = None
    consecutive_errors: int = 0
    monthly_cap_used: int | None = None  # X adapter only
    monthly_cap_limit: int | None = None  # X adapter only
    error_message: str | None = None


class CarrierConfig(BaseModel):
    name: str  # e.g. "verizon"
    display_name: str  # e.g. "Verizon"
    handles: list[str]  # e.g. ["@Verizon", "@VerizonSupport"]
    keywords: list[str]  # brand-specific complaint keywords
    app_store_id: str | None = None  # Apple App Store app ID
    play_store_id: str | None = None  # Google Play package name
    trustpilot_slug: str | None = None
    subreddits: list[str] = []
    youtube_channel_id: str | None = None  # Official YouTube channel ID
