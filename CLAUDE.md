# PulseGuard AI — Project Rules

## Identity
PulseGuard AI is a social media customer issue triage system for telecom.
It monitors public social feeds, classifies issues, and routes them for resolution.
It is NOT a call transcript system. It is NOT related to call anatomy frameworks.

## Non-negotiables
- Author handles are ALWAYS hashed (SHA-256) before storage. No exceptions.
- Content is ALWAYS PII-sanitised before storage. No exceptions.
- RESOLVER never posts publicly. It produces drafts only. Publishing happens
  ONLY via explicit human approval through the `/drafts/{id}/approve`
  endpoint — never automatically, never by any agent acting on its own.
  ("RESOLVER never posts" describes the agent, not the system: the system
  does post, but only after that explicit human action. Treating the
  Approve & Send feature as a violation of this rule is a misreading of it.)
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

## KB / Vector store
Resolution KB is stored in ChromaDB (local, file-based).
Embeddings: sentence-transformers/all-MiniLM-L6-v2 (ARM64 compatible, no GPU required).

## Notifications
ESCALATION agent sends via Slack webhook AND email (SMTP or SendGrid).
Check SLACK_WEBHOOK_URL, SENDGRID_API_KEY, and SMTP_HOST in .env.

## Code standards
- Python 3.12, fully async, type hints on every function signature
- Pydantic v2 for all data models
- structlog for all logging. Never use print().
- Black + ruff for formatting and linting
- All agent state transitions logged at INFO with structured fields
- All MCP tool calls logged with inputs + outputs + latency
