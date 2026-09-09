from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PendingDraft(BaseModel):
    """A drafted response awaiting human review — the copilot's core unit.
    Written for every signal that reaches a draft, whether Resolver judged
    it high-confidence or not; confidence affects queue priority, never
    whether a human sees it (spec §9 — this product never auto-sends)."""

    signal_id: str
    carrier: str
    category: str
    severity: str | None = None
    source_platform: str
    source_url: str
    draft_text: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    status: Literal["pending", "approved", "rejected"] = "pending"
    screen_flag: str | None = None  # set by Task 7's output screening, None means it passed
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    published_result: dict[str, Any] | None = None  # set by Task 10 once actually posted
