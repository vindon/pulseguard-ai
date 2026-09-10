"""Shared wrapper every agent's LLM call site uses: check the spend cap
before invoking, record actual spend from the response's real token
counts after. One helper here instead of six near-identical inline
try/except blocks across the four agent modules."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from pulseguard.security.budget_guard import check_budget, record_spend


async def invoke_with_budget_guard(
    model: BaseChatModel, messages: list[BaseMessage], *, model_name: str
) -> Any:
    await check_budget()
    response = await model.ainvoke(messages)
    usage = getattr(response, "usage_metadata", None) or {}
    details = usage.get("input_token_details", {}) or {}
    await record_spend(
        model_name,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_creation_tokens=details.get("cache_creation", 0),
        cache_read_tokens=details.get("cache_read", 0),
    )
    return response
