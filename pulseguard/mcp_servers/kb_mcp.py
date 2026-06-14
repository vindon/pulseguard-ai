import json
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from fastmcp import FastMCP
from pydantic import BaseModel

from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.redis_client import get_async_redis
from pulseguard.tracing import tool_trace

configure_logging()
logger = get_logger(__name__)

mcp = FastMCP("pulseguard-kb-mcp")

_KB_PATH = Path(__file__).parent.parent / "kb" / "telecom_resolutions.json"
_CHROMA_PATH = "chroma_db"
_COLLECTION_NAME = "telecom_kb"
_KB_MISS_KEY = "pulseguard:kb:misses"

# Lazy initialisation — avoids loading sentence-transformers at import time
_chroma_client: Any | None = None
_collection: Any | None = None


def _get_collection() -> chromadb.Collection:
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    _chroma_client = chromadb.PersistentClient(path=_CHROMA_PATH)
    _collection = _chroma_client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # Seed from JSON if collection is empty
    if _collection.count() == 0:
        _seed_collection(_collection)

    return _collection


def _seed_collection(col: chromadb.Collection) -> None:
    with open(_KB_PATH) as f:
        data = json.load(f)

    documents, metadatas, ids = [], [], []
    for entry in data["entries"]:
        doc_text = (
            f"Category: {entry['category']}. "
            f"Carrier: {entry['carrier']}. "
            f"Title: {entry['title']}. "
            f"Steps: {' '.join(entry['steps'][:4])}. "
            f"Escalation triggers: {', '.join(entry.get('escalation_triggers', []))}"
        )
        doc_id = f"{entry['carrier']}:{entry['category'].replace('/', '_').replace(' ', '_')}"
        documents.append(doc_text)
        metadatas.append(
            {
                "category": entry["category"],
                "carrier": entry["carrier"],
                "tier": entry["tier"],
                "title": entry["title"],
            }
        )
        ids.append(doc_id)

    col.add(documents=documents, metadatas=metadatas, ids=ids)
    logger.info("kb_seeded", count=len(documents))


class KBArticle(BaseModel):
    id: str
    category: str
    carrier: str
    tier: int
    title: str
    relevance_score: float


class ResolutionScript(BaseModel):
    category: str
    carrier: str
    tier: int
    title: str
    steps: list[str]
    escalation_triggers: list[str]
    expected_resolution_minutes: int | None
    platform_responses: dict[str, str]


class ErrorResponse(BaseModel):
    error: str
    code: str


@mcp.tool()
@tool_trace("kb", "search_kb")
async def search_kb(query: str, carrier: str, category: str = "") -> dict[str, Any]:
    """Semantic search over the resolution KB. Returns ranked KBArticle list."""
    if not query or not carrier:
        return ErrorResponse(
            error="query and carrier are required", code="INVALID_PARAM"
        ).model_dump()

    try:
        collection = _get_collection()
        where: dict[str, Any] = {"carrier": carrier.lower()}
        if category:
            where = {"$and": [{"carrier": carrier.lower()}, {"category": category}]}

        results = collection.query(
            query_texts=[query],
            n_results=min(5, collection.count()),
            where=where if collection.count() > 0 else None,
        )

        articles = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else 0.5
            articles.append(
                KBArticle(
                    id=doc_id,
                    category=meta["category"],
                    carrier=meta["carrier"],
                    tier=meta["tier"],
                    title=meta["title"],
                    relevance_score=round(1.0 - distance, 3),
                ).model_dump()
            )

        logger.info("search_kb", query=query[:50], carrier=carrier, results=len(articles))
        return {"articles": articles, "count": len(articles)}
    except Exception as exc:
        logger.error("search_kb_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="KB_ERROR").model_dump()


@mcp.tool()
@tool_trace("kb", "get_resolution_script")
async def get_resolution_script(category: str, carrier: str) -> dict[str, Any]:
    """Get the full structured resolution script for a category + carrier."""
    if not category or not carrier:
        return ErrorResponse(
            error="category and carrier are required", code="INVALID_PARAM"
        ).model_dump()

    try:
        with open(_KB_PATH) as f:
            data = json.load(f)

        for entry in data["entries"]:
            if entry["category"] == category and entry["carrier"] == carrier.lower():
                script = ResolutionScript(
                    category=entry["category"],
                    carrier=entry["carrier"],
                    tier=entry["tier"],
                    title=entry["title"],
                    steps=entry["steps"],
                    escalation_triggers=entry.get("escalation_triggers", []),
                    expected_resolution_minutes=entry.get("expected_resolution_minutes"),
                    platform_responses=entry.get("platform_responses", {}),
                )
                logger.info("get_resolution_script", category=category, carrier=carrier)
                return script.model_dump()

        await log_kb_miss(signal_id="lookup", category=category, carrier=carrier)
        return ErrorResponse(
            error=f"No script for {category}/{carrier}", code="NOT_FOUND"
        ).model_dump()
    except Exception as exc:
        logger.error("get_resolution_script_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="KB_ERROR").model_dump()


@mcp.tool()
@tool_trace("kb", "log_kb_miss")
async def log_kb_miss(signal_id: str, category: str, carrier: str) -> dict[str, Any]:
    """Track a KB gap — category or carrier not covered in the resolution KB."""
    if not signal_id or not category or not carrier:
        return ErrorResponse(
            error="signal_id, category, and carrier are required", code="INVALID_PARAM"
        ).model_dump()
    try:
        redis = get_async_redis()
        miss_key = f"{_KB_MISS_KEY}:{carrier}:{category.replace(' ', '_')}"
        await redis.incr(miss_key)
        logger.warning("kb_miss", signal_id=signal_id, category=category, carrier=carrier)
        return {"logged": True, "signal_id": signal_id, "category": category, "carrier": carrier}
    except Exception as exc:
        logger.error("log_kb_miss_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


if __name__ == "__main__":
    mcp.run()
