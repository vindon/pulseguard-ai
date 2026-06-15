"""
TRIAGE — Classification and Routing Agent
Model: claude-sonnet-4-6 (nuanced classification, mid-volume)

Nodes: classify_issue_type → assign_resolution_tier → score_severity → enrich_context → emit_routed
"""

import json
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pulseguard.logging_config import get_logger
from pulseguard.models.signals import ValidatedSignal
from pulseguard.models.triage import TriageReport
from pulseguard.security.audit import write_audit_entry
from pulseguard.tracing import node_trace

logger = get_logger(__name__)

_MODEL = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)

_TRIAGE_SYSTEM = """You are a telecom customer support triage specialist.

Given a customer post, return a JSON object with exactly these fields:

{
  "category": "<one of the categories below>",
  "severity_score": <integer 1-5>,
  "sentiment_score": <float -1.0 to 1.0>,
  "churn_risk": <true|false>,
  "routing_rationale": "<one sentence explaining the routing decision>"
}

Categories (use exact spelling):
- Network outage (area-wide)
- Network signal (individual)
- Billing dispute
- Bill explanation
- Trade-in status
- Order status
- eSIM activation
- Device troubleshooting
- Port/number transfer
- Contract/plan change
- Roaming issues
- App not working
- Account access / lock
- General complaint / NPS risk

Severity score guide:
1 = Minor inconvenience, no urgency
2 = Moderate issue, non-urgent
3 = Significant impact on service
4 = Major impact, customer frustrated
5 = Critical — outage, security, imminent churn

Sentiment: -1.0 = extremely negative, 0 = neutral, 1.0 = very positive
Churn risk: true if customer mentions switching, cancelling, leaving, or is extremely negative

Return ONLY the JSON object, no other text."""

_TIER_MAP = {
    "Network outage (area-wide)": 2,
    "Network signal (individual)": 1,
    "Billing dispute": 2,
    "Bill explanation": 1,
    "Trade-in status": 0,
    "Order status": 0,
    "eSIM activation": 0,
    "Device troubleshooting": 1,
    "Port/number transfer": 1,
    "Contract/plan change": 2,
    "Roaming issues": 1,
    "App not working": 0,
    "Account access / lock": 2,
    "General complaint / NPS risk": 2,
}


class TriageState(TypedDict):
    validated_signal: dict[str, Any]
    category: str
    resolution_tier: int
    severity_score: int
    sentiment_score: float
    churn_risk: bool
    routing_decision: str
    routing_rationale: str
    kb_context: str | None
    trace_id: str
    error: str | None


@node_trace("triage", "classify_issue_type")
async def classify_issue_type(state: TriageState) -> dict[str, Any]:
    vs_data = state["validated_signal"]
    content = vs_data.get("raw", {}).get("content", "")
    source = vs_data.get("raw", {}).get("source", "")
    carrier = vs_data.get("detected_carrier", "unknown")

    prompt = f"Carrier: {carrier}\nSource: {source}\nCustomer post:\n{content}"
    messages = [SystemMessage(content=_TRIAGE_SYSTEM), HumanMessage(content=prompt)]

    try:
        response = await _MODEL.ainvoke(messages)
        # Extract text from response — langchain-anthropic may return list of content blocks
        raw = response.content
        if isinstance(raw, list):
            text = next(
                (
                    b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
                    for b in raw
                    if (isinstance(b, dict) and b.get("type") == "text") or hasattr(b, "text")
                ),
                "",
            )
        else:
            text = str(raw)
        # Strip markdown code fences if present
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(text)
        category = result.get("category", "General complaint / NPS risk")
        logger.info("triage_classified", category=category, carrier=carrier)
        return {
            "category": category,
            "severity_score": max(1, min(5, int(result.get("severity_score", 3)))),
            "sentiment_score": max(-1.0, min(1.0, float(result.get("sentiment_score", 0.0)))),
            "churn_risk": bool(result.get("churn_risk", False)),
            "routing_rationale": result.get("routing_rationale", ""),
            "error": None,
        }
    except Exception as exc:
        logger.error("triage_classify_error", error=str(exc))
        return {
            "category": "General complaint / NPS risk",
            "severity_score": 3,
            "sentiment_score": -0.5,
            "churn_risk": False,
            "routing_rationale": f"Classification error — defaulting to Tier 2: {exc}",
            "error": str(exc),
        }


@node_trace("triage", "assign_resolution_tier")
async def assign_resolution_tier(state: TriageState) -> dict[str, Any]:
    tier = _TIER_MAP.get(state.get("category", "General complaint / NPS risk"), 2)
    routing = "ESCALATION" if tier == 2 else "RESOLVER"
    logger.info("triage_tier_assigned", tier=tier, routing=routing, category=state.get("category"))
    return {"resolution_tier": tier, "routing_decision": routing}


@node_trace("triage", "score_severity")
async def score_severity(state: TriageState) -> dict[str, Any]:
    # Severity already computed in classify_issue_type — this node applies override rules
    score = state.get("severity_score", 3)
    # Force escalation for extreme cases regardless of tier
    if state.get("churn_risk") and state.get("sentiment_score", 0) < -0.8:
        score = max(score, 4)
    logger.info("triage_severity", score=score)
    return {"severity_score": score}


@node_trace("triage", "enrich_context")
async def enrich_context(state: TriageState) -> dict[str, Any]:
    carrier = state["validated_signal"].get("detected_carrier", "unknown")
    category = state.get("category", "")

    from pulseguard.mcp_servers.classify_mcp import get_kb_context

    result = await get_kb_context(category, carrier)
    if "error" not in result:
        ctx = (
            f"KB: {result.get('title', '')} | Tier: {result.get('tier')} | "
            f"Steps preview: {'; '.join(result.get('steps_preview', []))}"
        )
        return {"kb_context": ctx}
    return {"kb_context": None}


@node_trace("triage", "emit_routed")
async def emit_routed(state: TriageState) -> dict[str, Any]:
    signal_id = state["validated_signal"].get("signal_id", "unknown")

    report = TriageReport(
        signal_id=signal_id,
        category=state.get("category", "General complaint / NPS risk"),
        resolution_tier=state.get("resolution_tier", 2),
        severity_score=state.get("severity_score", 3),
        sentiment_score=state.get("sentiment_score", 0.0),
        churn_risk=state.get("churn_risk", False),
        routing_decision=state.get("routing_decision", "ESCALATION"),
        routing_rationale=state.get("routing_rationale", ""),
        kb_context=state.get("kb_context"),
        triage_trace_id=state.get("trace_id", ""),
        triaged_at=datetime.now(UTC),
    )

    from pulseguard.orchestrator.event_bus import publish_triage_report

    await publish_triage_report(report)

    # Store triage report in Redis so ESCALATION can look it up when processing needs_escalation events
    from pulseguard.redis_client import get_async_redis

    redis = get_async_redis()
    await redis.hset("pulseguard:triage_reports", signal_id, report.model_dump_json())

    from pulseguard.gateway.metrics import signals_by_routing

    carrier = state["validated_signal"].get("detected_carrier", "unknown")
    signals_by_routing.labels(tier=str(report.resolution_tier), carrier=carrier).inc()

    write_audit_entry(
        "triage",
        signal_id,
        "signal_triaged",
        state.get("trace_id", ""),
        {
            "category": report.category,
            "tier": report.resolution_tier,
            "routing": report.routing_decision,
        },
    )
    logger.info("triage_emitted", signal_id=signal_id, routing=report.routing_decision)
    return {}


def build_triage_graph() -> CompiledStateGraph:
    graph = StateGraph(TriageState)
    graph.add_node("classify_issue_type", classify_issue_type)
    graph.add_node("assign_resolution_tier", assign_resolution_tier)
    graph.add_node("score_severity", score_severity)
    graph.add_node("enrich_context", enrich_context)
    graph.add_node("emit_routed", emit_routed)

    graph.set_entry_point("classify_issue_type")
    graph.add_edge("classify_issue_type", "assign_resolution_tier")
    graph.add_edge("assign_resolution_tier", "score_severity")
    graph.add_edge("score_severity", "enrich_context")
    graph.add_edge("enrich_context", "emit_routed")
    graph.add_edge("emit_routed", END)

    return graph.compile()


triage_graph = build_triage_graph()


async def process_validated_signal(validated: ValidatedSignal, trace_id: str) -> None:
    import uuid

    state: TriageState = {
        "validated_signal": validated.model_dump(),
        "category": "",
        "resolution_tier": 2,
        "severity_score": 3,
        "sentiment_score": 0.0,
        "churn_risk": False,
        "routing_decision": "ESCALATION",
        "routing_rationale": "",
        "kb_context": None,
        "trace_id": trace_id or str(uuid.uuid4()),
        "error": None,
    }
    await triage_graph.ainvoke(state)
