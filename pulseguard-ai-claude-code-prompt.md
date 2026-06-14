# PulseGuard AI — Claude Code Build Prompt
### Autonomous Social Feed Triage System for Telecom CX
**Paste this entire file into Claude Code as your opening prompt.**

---

## ROLE AND CONTEXT

You are Claude Code acting as lead architect and builder for **PulseGuard AI** — a production-grade autonomous multi-agent system that monitors public social media and review platforms for telecom customer issues, triages them by severity and resolvability, attempts autonomous resolution for deterministic issues, and routes complex cases to human experts.

The project owner is a Senior Manager in AI Strategy with deep telecom CX background (Verizon). This is a portfolio piece demonstrating production agentic AI competence. Build accordingly: every architectural decision must be defensible in a senior engineering or product interview. No shortcuts, no stubs left uncommitted.

Read the entire prompt before writing a single line of code. Confirm your understanding before building.

---

## WHAT PULSEGUARD AI IS

A **carrier-agnostic social media triage platform, configured for telecom**. It:

1. Continuously ingests public social signals from multiple platforms where telecom customers and brands actively engage
2. Validates each signal as a genuine telecom support issue (not spam, not off-topic)
3. Deduplicates signals across sources (same complaint appearing on X and Reddit is one issue)
4. Classifies the issue by type and resolution tier using LLM reasoning
5. Attempts autonomous resolution for deterministic, self-serviceable issues (Tier 0/1)
6. Routes unresolvable and complex issues to a human expert queue (Tier 2)
7. Produces a structured audit trail of every decision, with full LangSmith traces

**What PulseGuard AI is NOT:**
- Not a call transcript analyser
- Not a call anatomy framework
- Not related to voice or IVR systems
- Not a chatbot

---

## FEED SOURCES AND API ARCHITECTURE

This is the most important design decision in the system. Get this right.

### Primary Source: X (Twitter) via Recent Search — NOT Streaming

**Architectural honesty required:** X filtered stream requires Pro tier ($5,000/month). Basic tier ($200/month) supports `GET /2/tweets/search/recent` (polling, 15,000 reads/month cap). Design the X adapter accordingly:

- Use `GET /2/tweets/search/recent` with carrier-specific filter rules
- Poll on a configurable interval (default: every 5 minutes)
- Track `newest_id` as a cursor to avoid re-ingesting the same tweets
- Respect the 15,000 reads/month cap — implement a monthly counter in Redis, alert at 80% usage
- Build the adapter interface so it is **stream-ready**: when a Pro key is provided, the same adapter switches to `GET /2/tweets/search/stream` without changing any downstream code
- Filter rules to build (carrier-agnostic, configurable per deployment):
  - Mentions of official carrier handles (@Verizon, @TMobile, @ATTHelp, @ATT)
  - Brand name + complaint keywords: `(verizon OR "t-mobile" OR att) (problem OR issue OR outage OR billing OR "not working" OR "can't" OR slow OR dropped)`
  - Exclude: retweets (`-is:retweet`), verified brand accounts posting proactively (`-from:Verizon`), replies to brand accounts that are promotional

Authentication: OAuth 2.0 Bearer Token (app-only, sufficient for read). Store as `X_BEARER_TOKEN` in `.env`.

### Secondary Source: Reddit via PRAW

- Subreddits to monitor (configurable): `r/verizon`, `r/tmobile`, `r/ATT`, `r/NoContract`, `r/mobilecarriers`, `r/techsupport`
- Use PRAW streaming (`subreddit.stream.submissions()` and `subreddit.stream.comments()`)
- Filter posts by keyword match before passing to SENTINEL
- Rate limits: PRAW handles this transparently. Use read-only OAuth (no user account needed).

### Tertiary Sources (pluggable adapters, ship as stubs with clear interface):

**Google Play Reviews** via `google-play-scraper` Python library (unofficial but stable, no API key required):
- Monitor Verizon, T-Mobile, AT&T app pages daily
- Pull reviews sorted by `newest`, last 24 hours only
- Rich signal: users describe exact error messages, app version, device — highly structured complaints

**Apple App Store Reviews** via `app-store-scraper` Python library (unofficial, no API key required):
- Same apps as Google Play
- Pull via RSS feed endpoint (`https://itunes.apple.com/us/rss/customerreviews/`)
- Less structured than Play but high volume

**Trustpilot** via HTTP scraping of their internal JSON API (no auth required, public data):
- Target: Verizon, T-Mobile, AT&T company pages on Trustpilot
- Poll daily for new reviews (reviews are slower cadence than social)
- Trustpilot reviews skew toward billing disputes and contract issues — high escalation signal
- Implement respectful rate limiting (1 request/second, rotating user agents)

**YouTube Comments** (stub only — implement as future adapter):
- Telecom brand channels and "how to" videos have high-signal complaint threads
- Requires YouTube Data API v3 (free tier sufficient)
- Document the interface but leave unimplemented

**Quora** (stub only):
- Public questions about carrier issues
- No official API; implement via SerpAPI or similar if needed

### Feed Adapter Interface

Every source implements this Python ABC:

```python
class FeedAdapter(ABC):
    name: str                    # e.g. "x", "reddit", "trustpilot"
    carrier_configs: list[CarrierConfig]

    @abstractmethod
    async def fetch(self) -> list[RawSignal]:
        """Fetch new signals since last run. Must be idempotent."""
        pass

    @abstractmethod
    async def health_check(self) -> AdapterHealth:
        """Return current health: HEALTHY | DEGRADED | DOWN + reason"""
        pass
```

`RawSignal` is the universal envelope:

```python
class RawSignal(BaseModel):
    signal_id: str           # UUID generated at ingestion
    source: Literal["x", "reddit", "google_play", "app_store", "trustpilot", "youtube", "quora"]
    source_id: str           # platform-native ID (tweet_id, reddit post_id, etc.)
    carrier_hint: str | None # detected from content or source URL
    author_handle: str       # hashed SHA-256 before storage
    content: str             # raw text, sanitised of PII before storage
    url: str                 # permalink to original post
    posted_at: datetime
    ingested_at: datetime
    adapter_metadata: dict   # source-specific fields (subreddit, app version, star rating, etc.)
```

---

## SYSTEM ARCHITECTURE

### Agent Roster — Four Agents on LangGraph

Each agent is a compiled `StateGraph`. They communicate via Redis Streams (event bus). No agent calls another agent directly.

---

**SENTINEL — Signal Validation Agent**

Role: The gatekeeper. Receives every raw signal from every adapter. Decides if it is a genuine telecom support issue worth triaging.

LangGraph nodes:
- `validate_format` — Pydantic schema check, reject malformed signals
- `deduplicate` — compute content hash + source_id, check Redis bloom filter, drop if seen
- `detect_carrier` — identify which carrier the signal is about (required for routing)
- `classify_validity` — LLM call: is this a genuine support issue? (not a meme, not a compliment, not off-topic)
- `emit_or_drop` — write valid signals to Redis, emit `signal.validated` event; drop invalids with reason logged

Model: `claude-haiku-4-5` — high volume, binary decision, cost matters here.

Tools via MCP: `pulseguard-feed-mcp` (read pending signals), `pulseguard-dedup-mcp` (bloom filter check/write), `pulseguard-state-mcp` (Redis write)

---

**TRIAGE — Classification and Routing Agent**

Role: Classifies the validated issue into a category and resolution tier. Determines whether RESOLVER or ESCALATION handles it.

LangGraph nodes:
- `classify_issue_type` — LLM call with structured output: issue category from the telecom taxonomy (see below)
- `assign_resolution_tier` — deterministic logic based on category + confidence score
- `score_severity` — urgency score 1–5 based on sentiment, language intensity, potential churn signal
- `enrich_context` — pull carrier-specific KB context for the issue category
- `emit_routed` — write TriageReport to Redis, emit `signal.triaged` with routing decision

Issue Taxonomy (carrier-agnostic, telecom-configured):

| Category | Tier | Resolution |
|---|---|---|
| Network outage (area-wide) | 2 | Human — requires ops team |
| Network signal (individual) | 1 | Resolver attempts, escalates if unresolved |
| Billing dispute | 2 | Human — account-specific data required |
| Bill explanation | 1 | Resolver attempts with KB lookup |
| Trade-in status | 0 | Resolver — deterministic lookup |
| Order status | 0 | Resolver — deterministic lookup |
| eSIM activation | 0 | Resolver — scripted steps |
| Device troubleshooting | 1 | Resolver attempts |
| Port/number transfer | 1 | Resolver attempts |
| Contract/plan change | 2 | Human — account action required |
| Roaming issues | 1 | Resolver attempts |
| App not working | 0 | Resolver — known fix steps |
| Account access / lock | 2 | Human — security-sensitive |
| General complaint / NPS risk | 2 | Human — retention at risk |

Model: `claude-sonnet-4-6` — nuanced classification, mid volume.

Tools via MCP: `pulseguard-classify-mcp` (taxonomy lookup, tier assignment), `pulseguard-kb-mcp` (KB context pull)

---

**RESOLVER — Autonomous Resolution Agent**

Role: Handles Tier 0 and Tier 1 issues. Attempts to provide a complete, accurate, actionable resolution. If it cannot resolve confidently, it escalates.

LangGraph nodes:
- `retrieve_resolution` — KB lookup for the issue category + carrier
- `draft_response` — LLM drafts a public-facing response (tweet-length for X, longer for Reddit/reviews)
- `validate_confidence` — LLM self-evaluates: is this response accurate and complete? Score 0–1
- `decide` — if confidence >= 0.85: emit resolved; else: route to escalation
- `format_for_channel` — format response appropriately for the source platform (280 chars for X, markdown for Reddit, prose for reviews)
- `emit_resolved` — write resolution to output store, emit `signal.resolved`

Model: `claude-sonnet-4-6` with extended thinking enabled on `draft_response` node.

Tools via MCP: `pulseguard-kb-mcp` (resolution scripts), `pulseguard-output-mcp` (write resolution record)

**Critical design rule:** RESOLVER never posts publicly. It produces a draft resolution that a human or brand system can post. PulseGuard is a triage and intelligence system, not a posting bot.

---

**ESCALATION — Human Handoff Agent**

Role: Handles Tier 2 issues and Tier 1 issues RESOLVER could not confidently resolve. Produces a structured brief for the human expert and parks it in the escalation queue. Waits for acknowledgement before marking closed.

LangGraph nodes:
- `compose_brief` — LLM produces EscalationBrief: issue summary, source platform, carrier, customer sentiment score, urgency level, RESOLVER's attempted response if any, recommended human action
- `assign_priority` — P1 (respond within 1 hour) / P2 (within 4 hours) / P3 (within 24 hours) based on severity score and issue category
- `notify` — send to configured notification channel (Slack, email, or both)
- `park_in_queue` — write to escalation queue in Redis, set TTL based on priority
- `await_ack` — interrupt node: loop waits for human acknowledgement via FastAPI endpoint before completing

Model: `claude-opus-4-6` — highest-stakes output, lower volume.

Tools via MCP: `pulseguard-notify-mcp` (Slack/email), `pulseguard-output-mcp` (queue write/read)

---

### Orchestrator

A LangGraph parent graph that:
- Spawns adapter polling loops on configurable schedules (X: every 5 min, Reddit: streaming, others: daily)
- Routes `signal.validated` events to TRIAGE
- Routes `signal.triaged` events to RESOLVER or ESCALATION based on tier
- Tracks system-wide state: signals in flight, queue depths, error counts, monthly X API cap usage
- Implements a **circuit breaker** per adapter: if an adapter returns errors 5 consecutive times, pause it and alert
- Implements a **global circuit breaker**: if ESCALATION queue depth > 100 unacknowledged, pause new intake and alert
- Exposes orchestrator health state to the FastAPI gateway

---

## MCP TOOL SERVERS

Build five FastMCP servers. Each is a standalone process. Transport: `stdio` for local development, `SSE` for production Docker.

### 1. `pulseguard-feed-mcp`
Tools:
- `list_pending_signals(source: str | None, limit: int)` — list signals awaiting SENTINEL
- `mark_signal_processed(signal_id: str, outcome: str)` — mark as validated/dropped
- `get_adapter_status()` — health of all registered adapters

### 2. `pulseguard-dedup-mcp`
Tools:
- `check_duplicate(content_hash: str, source_id: str) -> bool` — Redis bloom filter check
- `register_signal(content_hash: str, source_id: str)` — add to bloom filter after validation
- `get_dedup_stats()` — total seen, total dropped as duplicates

### 3. `pulseguard-classify-mcp`
Tools:
- `lookup_taxonomy(issue_description: str) -> TaxonomyMatch` — match to telecom issue taxonomy
- `get_tier(category: str) -> int` — return resolution tier for a category
- `get_kb_context(category: str, carrier: str) -> str` — pull relevant KB snippet for triage

### 4. `pulseguard-kb-mcp`
Tools:
- `search_kb(query: str, carrier: str, category: str) -> list[KBArticle]` — semantic search over resolution KB
- `get_resolution_script(category: str, carrier: str) -> ResolutionScript` — structured resolution steps
- `log_kb_miss(signal_id: str, category: str, carrier: str)` — track gaps in KB coverage

### 5. `pulseguard-notify-mcp`
Tools:
- `send_slack_alert(brief: EscalationBrief, channel: str)` — post to Slack webhook
- `send_email_brief(brief: EscalationBrief, recipient: str)` — send via SMTP or SendGrid
- `acknowledge_escalation(signal_id: str, ack_by: str)` — mark human ack received
- `get_queue_depth() -> int` — current unacknowledged escalations

### 6. `pulseguard-output-mcp`
Tools:
- `write_resolution(signal_id: str, resolution: ResolutionRecord)`
- `write_escalation(signal_id: str, brief: EscalationBrief)`
- `get_signal_status(signal_id: str) -> SignalStatus`
- `list_resolved(carrier: str | None, hours: int) -> list[ResolutionRecord]`
- `list_escalations(priority: str | None, acknowledged: bool | None) -> list[EscalationBrief]`

**All MCP tools must:**
- Validate inputs with Pydantic v2 before executing
- Log every call to LangSmith with tool name, inputs, outputs, latency
- Return structured error objects on failure (never raise unhandled exceptions)
- Be idempotent where applicable

---

## DATA MODELS

All models in `pulseguard/models/` using Pydantic v2.

```python
# Core signal lifecycle

class RawSignal(BaseModel):
    signal_id: str
    source: Literal["x", "reddit", "google_play", "app_store", "trustpilot", "youtube", "quora"]
    source_id: str
    carrier_hint: str | None
    author_handle: str        # SHA-256 hashed before storage
    content: str              # PII-sanitised before storage
    url: str
    posted_at: datetime
    ingested_at: datetime
    adapter_metadata: dict

class ValidatedSignal(BaseModel):
    signal_id: str
    raw: RawSignal
    detected_carrier: str
    is_valid: bool
    validity_reason: str
    content_hash: str         # for deduplication
    sentinel_trace_id: str
    validated_at: datetime

class TriageReport(BaseModel):
    signal_id: str
    category: str             # from telecom taxonomy
    resolution_tier: Literal[0, 1, 2]
    severity_score: int       # 1-5
    sentiment_score: float    # -1.0 to 1.0
    churn_risk: bool
    routing_decision: Literal["RESOLVER", "ESCALATION"]
    routing_rationale: str
    kb_context: str | None
    triage_trace_id: str
    triaged_at: datetime

class ResolutionRecord(BaseModel):
    signal_id: str
    category: str
    carrier: str
    draft_response: str       # platform-formatted, ready for human review
    source_platform: str      # determines format
    confidence_score: float   # 0.0-1.0
    resolved: bool
    escalation_reason: str | None  # if not resolved
    resolver_trace_id: str
    resolved_at: datetime

class EscalationBrief(BaseModel):
    signal_id: str
    summary: str
    source_platform: str
    carrier: str
    category: str
    severity: Literal["P1", "P2", "P3"]
    sentiment_score: float
    churn_risk: bool
    original_post_url: str
    attempted_resolution: str | None
    recommended_action: str
    escalation_trace_id: str
    escalated_at: datetime
    acknowledged: bool
    acknowledged_by: str | None
    acknowledged_at: datetime | None

class AdapterHealth(BaseModel):
    adapter_name: str
    status: Literal["HEALTHY", "DEGRADED", "DOWN"]
    last_successful_fetch: datetime | None
    consecutive_errors: int
    monthly_cap_used: int | None   # X only
    monthly_cap_limit: int | None  # X only
    error_message: str | None
```

---

## OBSERVABILITY — LANGSMITH

Every agent node emits a named LangSmith span. This is non-negotiable for a production portfolio piece.

**Instrumentation pattern for every LangGraph node:**

```python
from langsmith import traceable

@traceable(name="sentinel.validate_format", tags=["agent:sentinel"])
async def validate_format(state: SentinelState) -> dict:
    ...
```

**Required tags on every trace:**
- `signal_id`
- `source` (x, reddit, trustpilot, etc.)
- `carrier`
- `agent` (sentinel, triage, resolver, escalation)
- `node` (the specific LangGraph node name)
- `routing_decision` (populated by TRIAGE and later)

**What to capture per trace:**
- Input tokens, output tokens, model used, latency
- Tool calls: name, inputs, outputs, latency
- Confidence scores where applicable
- Routing decisions with rationale

**LangSmith datasets:** Create one dataset per agent for regression evaluation. Add at least 5 examples per dataset from the test fixtures.

---

## FASTAPI GATEWAY

Expose the following endpoints. All require API key auth except `/health`.

```
POST   /api/v1/signals/ingest          # Manual signal ingestion (for testing)
GET    /api/v1/signals/{signal_id}     # Signal status and full lifecycle
GET    /api/v1/signals                 # List signals with filters (carrier, status, source, hours)
GET    /api/v1/escalations             # List escalations with filters
POST   /api/v1/escalations/{id}/ack   # Human acknowledgement endpoint
GET    /api/v1/adapters/status         # All adapter health statuses
GET    /api/v1/orchestrator/status     # Queue depths, circuit breakers, monthly cap
GET    /metrics                        # Prometheus metrics (no auth)
GET    /health                         # Liveness check (no auth)
```

Prometheus metrics to expose:
- `pulseguard_signals_ingested_total{source, carrier}`
- `pulseguard_signals_by_routing{tier, carrier}`
- `pulseguard_resolutions_total{outcome, carrier}`
- `pulseguard_escalations_total{priority, carrier}`
- `pulseguard_adapter_errors_total{adapter}`
- `pulseguard_x_api_reads_monthly` (gauge, updated on every X poll)
- `pulseguard_agent_latency_seconds{agent, node}` (histogram)

---

## SECURITY

**No exceptions on any of these:**

- All secrets in `.env` (gitignored). Provide `.env.example` with documented descriptions.
- `author_handle` must be SHA-256 hashed before any storage or logging. Raw usernames never appear in Redis, logs, LangSmith, or output records.
- `content` must be passed through `sanitise_pii(text: str) -> str` before storage. Strip: email patterns, phone number patterns, credit card patterns.
- API key authentication on all gateway endpoints except `/health` and `/metrics`. Keys validated via FastAPI dependency, stored in env.
- Rate limiting: 60 requests/minute per API key via `slowapi`.
- RESOLVER never posts publicly. All generated responses are drafts only.
- Audit log at `logs/audit.jsonl` is append-only. Every agent output (ValidatedSignal, TriageReport, ResolutionRecord, EscalationBrief) writes one audit entry: `{timestamp, agent, signal_id, action, trace_id}`.
- MCP tool inputs validated by Pydantic before execution. No raw strings passed to tool logic.

---

## CLAUDE CODE PROJECT STRUCTURE

### CLAUDE.md (root — write this first, never alter during builds)

```
# PulseGuard AI — Project Rules

## Identity
PulseGuard AI is a social media customer issue triage system for telecom.
It monitors public social feeds, classifies issues, and routes them for resolution.
It is NOT a call transcript system. It is NOT related to call anatomy frameworks.

## Non-negotiables
- Author handles are ALWAYS hashed (SHA-256) before storage. No exceptions.
- Content is ALWAYS PII-sanitised before storage. No exceptions.
- RESOLVER never posts publicly. It produces drafts only.
- All secrets via environment variables. Never hardcode credentials.
- Never commit .env. Never log API keys.
- Run tests before marking any task done.
- ARM64 compatible code only (MacBook M-series + Linux ARM).
- uv for dependency management. Not pip.

## Agent model assignments (do not change)
- SENTINEL: claude-haiku-4-5 (high volume, binary decision)
- TRIAGE: claude-sonnet-4-6 (nuanced classification)
- RESOLVER: claude-sonnet-4-6 with extended thinking on draft_response node
- ESCALATION: claude-opus-4-6 (highest-stakes output)

## X API constraint (important)
Basic tier = recent search polling only. NOT filtered stream.
Poll interval: 5 minutes. Monthly cap: 15,000 reads.
Track usage in Redis. Alert at 80% of monthly cap.
Stream-ready interface: Pro key in env switches to streaming automatically.

## Code standards
- Python 3.12, fully async, type hints on every function signature
- Pydantic v2 for all data models
- structlog for all logging. Never use print().
- Black + ruff for formatting and linting
- All agent state transitions logged at INFO with structured fields
- All MCP tool calls logged with inputs + outputs + latency
```

### Skills (`.claude/skills/`)

**`add-feed-adapter/SKILL.md`**
Scaffolds a new feed adapter: creates the class extending `FeedAdapter`, implements `fetch()` and `health_check()`, adds Pydantic models for `adapter_metadata`, writes unit tests with mock responses, registers the adapter in orchestrator config.

**`add-kb-entry/SKILL.md`**
Adds a new resolution script to the KB: validates the category exists in the taxonomy, creates the structured `ResolutionScript` entry, writes a unit test asserting the resolver uses it for the matching category.

**`run-smoke-test/SKILL.md`**
Posts one synthetic signal per source type to the ingest endpoint, waits for it to complete the pipeline, prints the final status, LangSmith trace URL, and audit log entry for each. Reports pass/fail.

**`check-x-cap/SKILL.md`**
Reads the current X API monthly read count from Redis, computes percentage of cap used, days remaining in billing cycle, and projected end-of-month usage. Prints a warning if over 80%.

### Hooks (`.claude/hooks/`)

**`pre-tool-call: block-destructive-ops`**
Blocks bash commands containing: `FLUSHALL`, `FLUSHDB`, `DROP TABLE`, `DELETE FROM`, `rm -rf` (outside `/tmp`). Logs blocked command, requires explicit confirmation.

**`post-tool-call: enforce-pii-sanitisation`**
After any file write to `pulseguard/adapters/` or `pulseguard/agents/`, scans the written content for common PII patterns (email regex, phone regex). Fails the turn if raw PII patterns are found in adapter output code paths.

**`post-turn: lint-and-type-check`**
Runs `ruff check .` and `mypy pulseguard/` after any Python file modification. Fails the turn if either returns errors.

### Subagents (use these during build — do not pollute main context)

- Reading and summarising X API v2 documentation for the recent search endpoint parameters
- Drafting all six Pydantic model files in isolation, then import the result
- Comparing `google-play-scraper` vs `app-store-scraper` library maturity and last commit date
- Running parallel validation of all five MCP server tool schemas against the data models

---

## DIRECTORY STRUCTURE

```
pulseguard-ai/
├── CLAUDE.md
├── .env.example
├── .env                          (gitignored)
├── pyproject.toml
├── docker-compose.yml
├── README.md
│
├── .claude/
│   ├── skills/
│   │   ├── add-feed-adapter/SKILL.md
│   │   ├── add-kb-entry/SKILL.md
│   │   ├── run-smoke-test/SKILL.md
│   │   └── check-x-cap/SKILL.md
│   └── hooks/
│       ├── block-destructive-ops.py
│       ├── enforce-pii-sanitisation.py
│       └── lint-and-type-check.py
│
├── pulseguard/
│   ├── __init__.py
│   ├── models/
│   │   ├── signals.py            (RawSignal, ValidatedSignal)
│   │   ├── triage.py             (TriageReport)
│   │   ├── resolution.py         (ResolutionRecord)
│   │   ├── escalation.py         (EscalationBrief)
│   │   └── adapters.py           (AdapterHealth, CarrierConfig)
│   ├── adapters/
│   │   ├── base.py               (FeedAdapter ABC, RawSignal)
│   │   ├── x_adapter.py          (X recent search + stream-ready interface)
│   │   ├── reddit_adapter.py     (PRAW streaming)
│   │   ├── google_play_adapter.py
│   │   ├── app_store_adapter.py
│   │   ├── trustpilot_adapter.py
│   │   └── stubs/
│   │       ├── youtube_adapter.py   (documented stub)
│   │       └── quora_adapter.py     (documented stub)
│   ├── agents/
│   │   ├── sentinel.py
│   │   ├── triage.py
│   │   ├── resolver.py
│   │   └── escalation.py
│   ├── orchestrator/
│   │   ├── graph.py              (parent LangGraph orchestrator)
│   │   ├── event_bus.py          (Redis Streams)
│   │   └── circuit_breaker.py
│   ├── mcp_servers/
│   │   ├── feed_mcp.py
│   │   ├── dedup_mcp.py
│   │   ├── classify_mcp.py
│   │   ├── kb_mcp.py
│   │   ├── notify_mcp.py
│   │   └── output_mcp.py
│   ├── kb/
│   │   └── telecom_resolutions.json   (structured resolution scripts per category/carrier)
│   ├── gateway/
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routes.py
│   │   └── metrics.py
│   └── security/
│       ├── sanitise.py           (PII sanitisation, handle hashing)
│       └── audit.py              (append-only audit log writer)
│
├── tests/
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_adapters.py
│   │   └── test_mcp_tools.py
│   ├── integration/
│   │   ├── test_pipeline_pass.py
│   │   ├── test_pipeline_escalate.py
│   │   └── test_circuit_breaker.py
│   └── fixtures/
│       ├── signal_tier0_esim.json
│       ├── signal_tier0_order_status.json
│       ├── signal_tier1_network.json
│       ├── signal_tier2_billing.json
│       ├── signal_duplicate.json
│       └── signal_invalid_spam.json
│
└── logs/
    └── audit.jsonl               (append-only, gitignored from git history)
```

---

## ENVIRONMENT VARIABLES

```bash
# Anthropic
ANTHROPIC_API_KEY=

# LangSmith
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=pulseguard-ai
LANGCHAIN_TRACING_V2=true

# X (Twitter) API — Basic tier
X_BEARER_TOKEN=
# Set to "pro" to enable filtered stream if you upgrade
X_API_TIER=basic
X_MONTHLY_CAP=15000
X_POLL_INTERVAL_SECONDS=300

# Reddit (read-only OAuth)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=PulseGuard/1.0

# Trustpilot (no auth required — rate limit settings)
TRUSTPILOT_POLL_INTERVAL_SECONDS=86400
TRUSTPILOT_REQUEST_DELAY_SECONDS=1

# Notifications
SLACK_WEBHOOK_URL=
NOTIFICATION_EMAIL=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

# Redis
REDIS_URL=redis://localhost:6379

# FastAPI Gateway
PULSEGUARD_API_KEY=

# Carrier configuration (comma-separated for multi-carrier monitoring)
MONITORED_CARRIERS=verizon,tmobile,att
```

---

## BUILD SEQUENCE

Build in this exact order. Do not proceed past a gate until tests pass.

**Phase 1 — Foundation**
1. `uv init pulseguard-ai`
2. Write all Pydantic models
3. Write `sanitise.py` (PII sanitisation + handle hashing) and its unit tests
4. Write `audit.py` (append-only audit log) and its unit tests
5. Set up Redis connection helpers
6. Set up structlog (JSON in production, pretty in dev)
7. Set up LangSmith instrumentation wrapper (`@traceable` + tag helpers)
8. Write `CLAUDE.md`
9. Write `.env.example`
10. **Gate: `uv run pytest tests/unit/test_models.py` — all pass**

**Phase 2 — Feed Adapters**
1. Write `FeedAdapter` ABC and `RawSignal` model
2. Write X adapter (recent search, cursor tracking, cap monitoring)
3. Write Reddit adapter (PRAW streaming)
4. Write Google Play adapter
5. Write App Store adapter
6. Write Trustpilot adapter
7. Write YouTube and Quora stubs (documented interface, clear TODOs)
8. Write carrier config (handles, keywords per carrier)
9. Write unit tests for each adapter with mocked API responses
10. **Gate: all adapter unit tests pass; X adapter correctly tracks `newest_id`**

**Phase 3 — MCP Tool Servers**
1. Build all 6 FastMCP servers
2. Pydantic validation on every tool input
3. LangSmith logging on every tool call
4. Unit tests for all tools with mocked Redis and dependencies
5. **Gate: all MCP tool tests pass**

**Phase 4 — Four Agents**
1. Build SENTINEL (validate, deduplicate, detect carrier, classify validity, emit)
2. Build TRIAGE (classify, tier, severity, enrich, route)
3. Build RESOLVER (retrieve, draft, validate confidence, decide, format, emit)
4. Build ESCALATION (compose brief, assign priority, notify, park, await ack)
5. Wire each agent to its MCP tools
6. **Gate: each agent processes one fixture signal in isolation, LangSmith trace visible**

**Phase 5 — Orchestrator and Gateway**
1. Build Redis Streams event bus
2. Build parent LangGraph orchestrator with adapter polling loops
3. Build circuit breakers (per adapter + global)
4. Build FastAPI gateway (all endpoints, auth, rate limiting, metrics)
5. Wire escalation acknowledgement endpoint to ESCALATION agent's await_ack node
6. **Gate: end-to-end integration tests pass for all 6 fixtures**

**Phase 6 — Claude Code Project Layer**
1. Write all 4 skills in `.claude/skills/`
2. Write all 3 hooks in `.claude/hooks/`
3. Write `docker-compose.yml` (agents, orchestrator, Redis, optional Prometheus + Grafana)
4. Write `README.md` (architecture, setup, how to run, how to add a new adapter, how to add a KB entry)
5. Run full test suite
6. Run smoke test skill
7. **Gate: smoke test passes, all 6 fixtures produce correct routing decisions, LangSmith shows complete traces for all**

---

## BEFORE YOU START — CONFIRM

Before writing any code, respond with:

1. One paragraph: what PulseGuard AI is (social triage system, NOT call analytics)
2. The X API constraint you will implement and why (no streaming on Basic)
3. Which adapters are fully implemented vs stubs
4. The build sequence you will follow
5. Any genuine blocking question (maximum 2)

Then begin Phase 1.

---

*PulseGuard AI. Social feed triage for telecom. Production quality. No shortcuts.*
