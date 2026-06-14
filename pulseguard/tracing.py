import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from langsmith import traceable as _traceable

from pulseguard.config import settings

os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
os.environ.setdefault("LANGCHAIN_TRACING_V2", str(settings.langchain_tracing_v2).lower())
os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

F = TypeVar("F", bound=Callable[..., Any])


def node_trace(agent: str, node: str) -> Callable[[F], F]:
    """Decorator that wraps a LangGraph node with a named LangSmith span."""

    def decorator(func: F) -> F:
        traced = _traceable(
            name=f"{agent}.{node}",
            tags=[f"agent:{agent}", f"node:{node}"],
        )(func)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await traced(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def tool_trace(server: str, tool: str) -> Callable[[F], F]:
    """Decorator for MCP tool calls — logs name, inputs, outputs, latency."""

    def decorator(func: F) -> F:
        traced = _traceable(
            name=f"mcp.{server}.{tool}",
            tags=[f"server:{server}", f"tool:{tool}", "mcp"],
        )(func)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await traced(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
