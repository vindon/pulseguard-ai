from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TriageReport(BaseModel):
    signal_id: str
    category: str  # from telecom taxonomy
    resolution_tier: Literal[0, 1, 2]
    severity_score: int = Field(ge=1, le=5)
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    churn_risk: bool
    routing_decision: Literal["RESOLVER", "ESCALATION"]
    routing_rationale: str
    kb_context: str | None = None
    triage_trace_id: str
    triaged_at: datetime
