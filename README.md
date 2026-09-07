# PulseGuard AI

**Autonomous social feed triage system for telecom CX.**

PulseGuard AI continuously monitors public social signals from X (Twitter) and Reddit for telecom customer issues. It validates signals, deduplicates them across sources, classifies issues by type and resolution tier, autonomously resolves deterministic issues (Tier 0/1), and routes complex cases to a human expert queue with structured escalation briefs.

Source scope is deliberately narrow: an earlier build also scraped Google Play, the App Store, Trustpilot, and Quora, but those were cut — Trustpilot in particular scraped an undocumented internal API, and Quora added a paid per-query dependency for the weakest data quality of the six. X and Reddit are the two official, low-maintenance APIs that carry the real complaint volume for this use case.

---

## Architecture

```
Social Feeds (X, Reddit)
        │
        ▼
   [SENTINEL]  ← claude-haiku-4-5
   Validate • Deduplicate • Detect carrier • Classify validity
        │
        ▼
   [TRIAGE]    ← claude-sonnet-4-6
   Classify issue • Assign tier • Score severity • Enrich KB context
        │
    ┌───┴───┐
    │       │
    ▼       ▼
[RESOLVER] [ESCALATION]  ← claude-opus-4-6
sonnet-4-6  Compose brief • Assign priority • Notify • Park in queue
+ thinking
    │
    ▼
Draft response (never auto-posted)
```

All agents communicate via **Redis Streams** event bus. Six **FastMCP** tool servers handle Redis, deduplication, KB lookup (ChromaDB), notifications, and output. Full observability via **LangSmith** on every node.

---

## Setup

### Prerequisites

- Python 3.12
- Redis 7+ (`brew install redis` or Docker)
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Install

```bash
git clone <repo>
cd pulseguard-ai
uv sync --extra dev
cp .env.example .env
# Fill in .env with your API keys
```

### Configure `.env`

Minimum required keys:

```bash
ANTHROPIC_API_KEY=           # Required for all agents
LANGCHAIN_API_KEY=           # Required for LangSmith tracing
PULSEGUARD_API_KEY=          # Gateway API auth key (you choose this)
X_BEARER_TOKEN=              # X API Basic tier bearer token
REDDIT_CLIENT_ID=            # Reddit read-only OAuth
REDDIT_CLIENT_SECRET=
SLACK_WEBHOOK_URL=           # For escalation alerts
REDIS_URL=redis://localhost:6379
```

### Run locally

```bash
# Start Redis
redis-server

# Start gateway (includes orchestrator)
uv run uvicorn pulseguard.gateway.main:app --reload

# Gateway is now at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Run with Docker

```bash
# Core services (gateway + Redis)
docker-compose up

# With monitoring (Prometheus + Grafana)
docker-compose --profile monitoring up

# Grafana at http://localhost:3000 (admin/pulseguard)
```

---

## API Reference

All endpoints require `X-API-Key: <PULSEGUARD_API_KEY>` header except `/health` and `/metrics`.

```
POST   /api/v1/signals/ingest                # Manually ingest a test signal
GET    /api/v1/signals/{signal_id}           # Signal lifecycle status
GET    /api/v1/signals?carrier=&hours=       # List resolved signals
GET    /api/v1/escalations?priority=&acknowledged=   # List escalations
POST   /api/v1/escalations/{id}/ack          # Human acknowledgement
GET    /api/v1/escalations/{id}/export       # Download escalation as JSON
GET    /api/v1/adapters/status               # All adapter health
GET    /api/v1/orchestrator/status           # Queue depths, circuit breakers, X cap
GET    /metrics                              # Prometheus metrics
GET    /health                               # Liveness check
```

### Manual signal test

```bash
curl -X POST http://localhost:8000/api/v1/signals/ingest \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "x",
    "source_id": "tweet-test-001",
    "author_handle": "@testuser",
    "content": "my verizon esim activation keeps failing with error EE002",
    "url": "https://x.com/i/web/status/tweet-test-001",
    "posted_at": "2026-06-08T10:00:00Z",
    "carrier_hint": "verizon"
  }'
```

---

## Resolution Tiers

| Tier | Description | Handler |
|------|-------------|---------|
| 0 | Deterministic, self-serviceable (eSIM, order status, trade-in, app fix) | RESOLVER — auto |
| 1 | Attempts autonomous resolution; escalates if confidence < 0.85 | RESOLVER → ESCALATION |
| 2 | Requires account access, security check, or human judgment | ESCALATION — direct |

**RESOLVER never posts publicly.** All draft responses require human review before posting.

---

## Issue Taxonomy

| Category | Tier |
|----------|------|
| Network outage (area-wide) | 2 |
| Network signal (individual) | 1 |
| Billing dispute | 2 |
| Bill explanation | 1 |
| Trade-in status | 0 |
| Order status | 0 |
| eSIM activation | 0 |
| Device troubleshooting | 1 |
| Port/number transfer | 1 |
| Contract/plan change | 2 |
| Roaming issues | 1 |
| App not working | 0 |
| Account access / lock | 2 |
| General complaint / NPS risk | 2 |

---

## How to add a new feed adapter

1. Run `/add-feed-adapter` skill (see `.claude/skills/add-feed-adapter/SKILL.md`)
2. Or manually:
   - Create `pulseguard/adapters/{name}_adapter.py` extending `FeedAdapter`
   - Add source literal to `RawSignal.source` in `pulseguard/models/signals.py`
   - Register in `pulseguard/orchestrator/graph.py` `_adapters` dict
   - Add circuit breaker in `pulseguard/orchestrator/circuit_breaker.py`
   - Write unit tests with mocked API responses

**Important:** Always use `self._make_signal()` — never assign `author_handle` or `content` directly.

---

## How to add a KB entry

1. Run `/add-kb-entry` skill (see `.claude/skills/add-kb-entry/SKILL.md`)
2. Or manually add to `pulseguard/kb/telecom_resolutions.json`:
   ```json
   {
     "category": "...",
     "carrier": "verizon|tmobile|att",
     "tier": 0|1|2,
     "steps": ["..."],
     "escalation_triggers": ["..."],
     "platform_responses": {"x": "...", "reddit": "...", "review": "..."}
   }
   ```
3. Reseed ChromaDB: `uv run python -c "from pulseguard.mcp_servers.kb_mcp import _seed_collection, _get_collection; _seed_collection(_get_collection())"`

---

## X API Constraint

PulseGuard uses **X Basic tier** (`GET /2/tweets/search/recent`, polling every 5 minutes, 15,000 reads/month cap). The adapter is **stream-ready** — setting `X_API_TIER=pro` in `.env` automatically switches to the filtered stream endpoint without any code changes.

Monitor cap usage:
```bash
redis-cli GET pulseguard:x:monthly_reads
# Or use the /check-x-cap Claude skill
```

---

## Security

- `author_handle` is SHA-256 hashed before any storage, logging, or LangSmith traces
- `content` is PII-sanitised (email, phone, CC, SSN patterns stripped) before storage
- All secrets in `.env` (gitignored); never hardcoded
- API key auth required on all gateway endpoints
- Rate limited: 60 requests/minute per API key
- Append-only audit log at `logs/audit.jsonl`
- RESOLVER produces draft responses only — never posts automatically

---

## Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# Specific agent
uv run pytest tests/unit/test_agents.py -v
```

---

## Observability

All agent nodes and MCP tool calls emit LangSmith spans. Every trace is tagged with:
- `signal_id`, `source`, `carrier`, `agent`, `node`, `routing_decision`

To view traces: [smith.langchain.com](https://smith.langchain.com) → project `pulseguard-ai`

Prometheus metrics available at `/metrics`. Run with `--profile monitoring` for Grafana dashboard.

---

*PulseGuard AI — social feed triage for telecom. Production quality.*
