# Skill: run-smoke-test

Posts one synthetic signal per source type through the live pipeline and reports pass/fail.

## What this skill does

1. Starts the FastAPI gateway if not running (`uv run uvicorn pulseguard.gateway.main:app`)
2. Posts each fixture signal to `POST /api/v1/signals/ingest`
3. Polls `GET /api/v1/signals/{signal_id}` until status = `resolved` or `escalated` (timeout: 120s)
4. For each signal: prints final status, LangSmith trace URL, and audit log entry
5. Reports overall pass/fail

## Usage

```
/run-smoke-test [--gateway-url http://localhost:8000]
```

## Expected outcomes per fixture

| Fixture | Expected routing | Expected stage |
|---------|-----------------|----------------|
| signal_tier0_esim | RESOLVER | resolved |
| signal_tier0_order_status | RESOLVER | resolved |
| signal_tier1_network | RESOLVER or ESCALATION | resolved or escalated |
| signal_tier2_billing | ESCALATION | escalated |
| signal_duplicate | dropped | (not ingested) |
| signal_invalid_spam | dropped | (not ingested) |

## Prerequisites

- Redis running: `redis-server` or `docker run -p 6379:6379 redis:7-alpine`
- `.env` configured with `ANTHROPIC_API_KEY`, `LANGCHAIN_API_KEY`, `PULSEGUARD_API_KEY`
- Gateway started: `uv run uvicorn pulseguard.gateway.main:app --reload`

## Pass criteria

- All 4 non-duplicate/non-spam signals reach terminal state within 120s
- LangSmith shows a trace for each signal with all agent nodes present
- `logs/audit.jsonl` contains entries for each signal_id
- No Python exceptions in gateway logs
