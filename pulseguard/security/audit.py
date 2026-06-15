import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_AUDIT_PATH = Path(os.getenv("AUDIT_LOG_PATH", "logs/audit.jsonl"))


def _ensure_log_dir() -> None:
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)


def write_audit_entry(
    agent: str,
    signal_id: str,
    action: str,
    trace_id: str,
    extra: dict[str, Any] | None = None,
) -> None:
    _ensure_log_dir()
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent": agent,
        "signal_id": signal_id,
        "action": action,
        "trace_id": trace_id,
    }
    if extra:
        entry.update(extra)
    with open(_AUDIT_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
