from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EscalationBrief(BaseModel):
    signal_id: str
    summary: str
    source_platform: str
    carrier: str
    category: str
    severity: Literal["P1", "P2", "P3"]
    sentiment_score: float
    churn_risk: bool
    original_post_url: str
    attempted_resolution: str | None = None
    recommended_action: str
    escalation_trace_id: str
    escalated_at: datetime
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
