from datetime import datetime

from pydantic import BaseModel, Field


class ResolutionRecord(BaseModel):
    signal_id: str
    category: str
    carrier: str
    draft_response: str  # platform-formatted, ready for human review — never posted automatically
    source_platform: str  # determines response format
    confidence_score: float = Field(ge=0.0, le=1.0)
    resolved: bool
    escalation_reason: str | None = None  # populated when resolved=False
    resolver_trace_id: str
    resolved_at: datetime
