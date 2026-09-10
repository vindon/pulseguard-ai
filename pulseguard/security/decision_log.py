"""Structured decision traceability, distinct from write_audit_entry
(security/audit.py). write_audit_entry logs that an action happened — a
signal was resolved, an escalation was created. DecisionLogger logs the
*reasoning behind* a decision — why this category, why this routing, why
resolved instead of escalated — so "why did the AI decide this" is
answerable from one greppable log per signal, not by re-reading scattered
LLM output. Mirrors the DecisionLogger discipline already proven in a
sibling project (spec §10)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DECISION_LOG_PATH = Path(os.getenv("DECISION_LOG_PATH", "logs/decisions.jsonl"))


class DecisionLogger:
    def __init__(self, agent: str, signal_id: str, trace_id: str) -> None:
        self.agent = agent
        self.signal_id = signal_id
        self.trace_id = trace_id
        self._entries: list[dict[str, Any]] = []

    def log(
        self,
        decision_type: str,
        decision: str,
        reason: str,
        evidence: dict[str, Any] | None = None,
        confidence: float | None = None,
        alternatives: list[str] | None = None,
    ) -> None:
        self._entries.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "agent": self.agent,
                "signal_id": self.signal_id,
                "trace_id": self.trace_id,
                "decision_type": decision_type,
                "decision": decision,
                "reason": reason[:500],
                "evidence": evidence or {},
                "confidence": confidence,
                "alternatives": alternatives or [],
            }
        )

    def finalize(self) -> list[dict[str, Any]]:
        if not self._entries:
            return []
        _DECISION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_DECISION_LOG_PATH, "a", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(json.dumps(entry) + "\n")
        return self._entries
