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
    subreddits: list[str] = []
