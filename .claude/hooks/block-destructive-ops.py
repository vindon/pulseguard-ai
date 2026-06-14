#!/usr/bin/env python3
"""
Pre-tool-call hook: blocks destructive operations in bash commands.
Reads JSON from stdin, checks for dangerous patterns, exits 2 to block.
"""
import json
import re
import sys

BLOCKED_PATTERNS = [
    r"\bFLUSHALL\b",
    r"\bFLUSHDB\b",
    r"\bDROP\s+TABLE\b",
    r"\bDELETE\s+FROM\b",
    r"rm\s+-rf\s+(?!\/tmp)",
    r"redis-cli\s+.*FLUSHALL",
    r"redis-cli\s+.*FLUSHDB",
]

try:
    payload = json.loads(sys.stdin.read())
except (json.JSONDecodeError, EOFError):
    sys.exit(0)

tool_name = payload.get("tool_name", "")
if tool_name != "Bash":
    sys.exit(0)

command = payload.get("tool_input", {}).get("command", "")

for pattern in BLOCKED_PATTERNS:
    if re.search(pattern, command, re.IGNORECASE):
        print(
            f"BLOCKED: Destructive operation detected — pattern '{pattern}' matched.\n"
            f"Command: {command[:200]}\n"
            "If this is intentional, confirm explicitly before proceeding.",
            file=sys.stderr,
        )
        sys.exit(2)

sys.exit(0)
