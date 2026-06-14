import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.tracing import tool_trace

configure_logging()
logger = get_logger(__name__)

mcp = FastMCP("pulseguard-classify-mcp")

_KB_PATH = Path(__file__).parent.parent / "kb" / "telecom_resolutions.json"

# Load taxonomy at startup
_kb_data: list[dict] = []
_taxonomy: dict[str, dict] = {}  # category -> {tier, carriers}


def _load_kb() -> None:
    global _kb_data, _taxonomy
    with open(_KB_PATH) as f:
        data = json.load(f)
    _kb_data = data["entries"]
    for entry in _kb_data:
        cat = entry["category"]
        if cat not in _taxonomy:
            _taxonomy[cat] = {"tier": entry["tier"], "carriers": []}
        _taxonomy[cat]["carriers"].append(entry["carrier"])


_load_kb()


class TaxonomyMatch(BaseModel):
    category: str
    tier: int
    confidence: float
    matched_on: str


class ErrorResponse(BaseModel):
    error: str
    code: str


@mcp.tool()
@tool_trace("classify", "lookup_taxonomy")
async def lookup_taxonomy(issue_description: str) -> dict[str, Any]:
    """Match an issue description to the telecom taxonomy. Returns best-match category and tier."""
    if not issue_description:
        return ErrorResponse(
            error="issue_description is required", code="INVALID_PARAM"
        ).model_dump()

    text = issue_description.lower()

    # Keyword-based matching (deterministic fallback; LLM does primary classification)
    matches: list[tuple[str, float, str]] = []

    keyword_map = {
        "eSIM activation": (["esim", "e-sim", "activation code", "qr code", "cellular plan"], 0.9),
        "Order status": (
            ["order", "delivery", "shipped", "tracking", "fedex", "ups", "when will"],
            0.85,
        ),
        "Trade-in status": (["trade", "trade-in", "trade in", "credit", "return device"], 0.85),
        "App not working": (
            ["app", "application", "crashing", "won't open", "not loading", "error 403"],
            0.85,
        ),
        "Bill explanation": (
            ["bill", "charge", "charged", "invoice", "statement", "fee", "cost"],
            0.8,
        ),
        "Billing dispute": (
            [
                "overcharged",
                "wrong amount",
                "dispute",
                "unauthorised charge",
                "double charged",
                "fraud",
            ],
            0.9,
        ),
        "Network signal (individual)": (
            ["signal", "coverage", "no service", "drop", "bar", "lte", "5g", "slow data"],
            0.8,
        ),
        "Network outage (area-wide)": (
            [
                "outage",
                "down for everyone",
                "area",
                "neighbourhood",
                "city",
                "region",
                "widespread",
            ],
            0.9,
        ),
        "Device troubleshooting": (
            ["phone", "device", "restart", "frozen", "battery", "update", "crash"],
            0.75,
        ),
        "Port/number transfer": (
            ["port", "transfer number", "number transfer", "porting", "keep my number"],
            0.9,
        ),
        "Roaming issues": (
            ["roaming", "international", "abroad", "travelling", "travel", "overseas", "day pass"],
            0.9,
        ),
        "Contract/plan change": (
            ["plan", "upgrade", "downgrade", "contract", "switch plan", "change plan"],
            0.8,
        ),
        "Account access / lock": (
            ["locked", "locked out", "password", "login", "can't log in", "account access", "2fa"],
            0.9,
        ),
        "General complaint / NPS risk": (
            [
                "cancel",
                "switching",
                "leaving",
                "terrible",
                "awful",
                "worst",
                "disappointed",
                "done with",
            ],
            0.8,
        ),
    }

    for category, (keywords, base_score) in keyword_map.items():
        matched = [kw for kw in keywords if kw in text]
        if matched:
            score = min(base_score + 0.05 * (len(matched) - 1), 0.99)
            matches.append((category, score, ", ".join(matched)))

    if not matches:
        # Default fallback
        return TaxonomyMatch(
            category="General complaint / NPS risk",
            tier=2,
            confidence=0.3,
            matched_on="fallback",
        ).model_dump()

    best_cat, best_score, matched_on = max(matches, key=lambda x: x[1])
    tier = _taxonomy.get(best_cat, {}).get("tier", 2)

    logger.info("lookup_taxonomy", category=best_cat, tier=tier, confidence=best_score)
    return TaxonomyMatch(
        category=best_cat, tier=tier, confidence=best_score, matched_on=matched_on
    ).model_dump()


@mcp.tool()
@tool_trace("classify", "get_tier")
async def get_tier(category: str) -> dict[str, Any]:
    """Return the resolution tier for a given taxonomy category."""
    if not category:
        return ErrorResponse(error="category is required", code="INVALID_PARAM").model_dump()
    info = _taxonomy.get(category)
    if not info:
        return ErrorResponse(error=f"Unknown category: {category}", code="NOT_FOUND").model_dump()
    return {"category": category, "tier": info["tier"]}


@mcp.tool()
@tool_trace("classify", "get_kb_context")
async def get_kb_context(category: str, carrier: str) -> dict[str, Any]:
    """Pull relevant KB snippet for triage context."""
    if not category or not carrier:
        return ErrorResponse(
            error="category and carrier are required", code="INVALID_PARAM"
        ).model_dump()

    for entry in _kb_data:
        if entry["category"] == category and entry["carrier"] == carrier.lower():
            steps_preview = entry["steps"][:3]
            return {
                "category": category,
                "carrier": carrier,
                "tier": entry["tier"],
                "title": entry["title"],
                "steps_preview": steps_preview,
                "escalation_triggers": entry.get("escalation_triggers", []),
            }

    return ErrorResponse(
        error=f"No KB entry for {category}/{carrier}", code="NOT_FOUND"
    ).model_dump()


if __name__ == "__main__":
    mcp.run()
