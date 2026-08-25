import os
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from langsmith import traceable as _traceable

from pulseguard.config import settings
from pulseguard.logging_config import get_logger

os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
os.environ.setdefault("LANGCHAIN_TRACING_V2", str(settings.langchain_tracing_v2).lower())
os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

_trace_logger = get_logger("pulseguard.trace")

F = TypeVar("F", bound=Callable[..., Any])


def _with_latency_log(func: Callable[..., Any], event: str, **tags: str) -> Callable[..., Any]:
    """Log call/duration/outcome via structlog regardless of whether LangSmith
    tracing is configured — CLAUDE.md requires every agent-node/MCP-tool call
    to carry a latency record, and LangSmith is opt-in (off unless a
    LANGCHAIN_API_KEY is set), so that requirement can't depend on it alone.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.monotonic()
        try:
            result = await func(*args, **kwargs)
        except Exception as exc:
            _trace_logger.error(
                event,
                outcome="error",
                error=str(exc),
                duration_ms=round((time.monotonic() - start) * 1000, 1),
                **tags,
            )
            raise
        _trace_logger.info(
            event, outcome="ok", duration_ms=round((time.monotonic() - start) * 1000, 1), **tags
        )
        return result

    return wrapper


def node_trace(agent: str, node: str) -> Callable[[F], F]:
    """Decorator that wraps a LangGraph node with a named LangSmith span
    (when tracing is enabled) plus an always-on latency log."""

    def decorator(func: F) -> F:
        traced = _traceable(
            name=f"{agent}.{node}",
            tags=[f"agent:{agent}", f"node:{node}"],
        )(func)

        @wraps(func)
        async def call_traced(*args: Any, **kwargs: Any) -> Any:
            return await traced(*args, **kwargs)

        return _with_latency_log(call_traced, f"{agent}.{node}", agent=agent, node=node)  # type: ignore[return-value]

    return decorator


def tool_trace(server: str, tool: str) -> Callable[[F], F]:
    """Decorator for MCP tool calls — logs name, inputs, outputs (via
    LangSmith when enabled), and always logs latency + outcome."""

    def decorator(func: F) -> F:
        traced = _traceable(
            name=f"mcp.{server}.{tool}",
            tags=[f"server:{server}", f"tool:{tool}", "mcp"],
        )(func)

        @wraps(func)
        async def call_traced(*args: Any, **kwargs: Any) -> Any:
            return await traced(*args, **kwargs)

        return _with_latency_log(call_traced, f"mcp.{server}.{tool}", server=server, tool=tool)  # type: ignore[return-value]

    return decorator
