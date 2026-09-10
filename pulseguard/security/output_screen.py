"""Screens a drafted reply before it reaches the human review queue —
tone, discriminatory language, and unauthorized promises (e.g. a refund
amount the brand's KB doesn't sanction). A failed screen never blocks
the draft; it sets PendingDraft.screen_flag so the reviewer sees the
concern before clicking Approve & Send. This is deliberately a second,
independent check from Resolver's own confidence score — a high-
confidence draft can still say something the brand shouldn't send."""

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from pulseguard.agents.llm_guard import invoke_with_budget_guard
from pulseguard.logging_config import get_logger
from pulseguard.security.budget_guard import BudgetExceededError

logger = get_logger(__name__)

_MODEL = ChatAnthropic(model="claude-haiku-4-5", temperature=0, timeout=30, max_retries=1)

_SCREEN_SYSTEM = """You review a customer-support draft reply before a human sees it.

Flag it (passed=false) if it: promises a specific dollar amount, discount,
or account action the reply itself invents rather than reports; uses
discriminatory, dismissive, or unprofessional language; or makes a legal
or safety claim beyond a routine customer-service response.

Return ONLY a JSON object: {"passed": true|false, "reasons": ["<short reason>", ...]}
"reasons" must be empty when passed is true."""


class ScreenResult(BaseModel):
    passed: bool
    reasons: list[str] = []


async def screen_draft(draft_text: str, category: str) -> ScreenResult:
    try:
        messages = [
            SystemMessage(content=_SCREEN_SYSTEM),
            HumanMessage(content=f"Category: {category}\n\nDraft reply:\n{draft_text}"),
        ]
        response = await invoke_with_budget_guard(_MODEL, messages, model_name="claude-haiku-4-5")
        parsed = json.loads(str(response.content))
        return ScreenResult(**parsed)
    except BudgetExceededError as exc:
        # Unlike the production agents (sentinel/triage/escalation), screen_draft
        # never halts the pipeline -- a tripped budget cap fails open here too,
        # same as any other screening failure (see module docstring).
        logger.error("output_screen_budget_exceeded", error=str(exc))
        return ScreenResult(passed=False, reasons=[f"Screening skipped: spend cap reached ({exc})"])
    except Exception as exc:
        logger.error("output_screen_error", error=str(exc))
        return ScreenResult(passed=False, reasons=[f"Screening unavailable: {exc}"])
