#!/usr/bin/env python3
"""
Post-tool-call hook: scans written adapter/agent files for raw PII patterns.
Fails the turn if unguarded PII-handling code is detected.
"""
import json
import re
import sys

PII_PATTERNS = [
    (r"author_handle\s*=\s*(?!hash_handle)", "author_handle assigned without hash_handle()"),
    (r'\.author_handle\s*=\s*["\']', "author_handle set to raw string literal"),
    (r'email\s*=\s*["\'][^"\']*@[^"\']*["\']', "hardcoded email address in output code"),
    (r"content\s*=\s*(?!sanitise_pii)", "content assigned without sanitise_pii() in adapter code"),
]

WATCHED_PATHS = ["pulseguard/adapters/", "pulseguard/agents/"]

try:
    payload = json.loads(sys.stdin.read())
except (json.JSONDecodeError, EOFError):
    sys.exit(0)

tool_name = payload.get("tool_name", "")
if tool_name not in ("Write", "Edit"):
    sys.exit(0)

file_path = payload.get("tool_input", {}).get("file_path", "")
if not any(watched in file_path for watched in WATCHED_PATHS):
    sys.exit(0)

content = payload.get("tool_input", {}).get("content", "") or payload.get("tool_input", {}).get(
    "new_string", ""
)

violations = []
for pattern, description in PII_PATTERNS:
    if re.search(pattern, content):
        violations.append(description)

if violations:
    print(
        f"PII SANITISATION CHECK FAILED in {file_path}:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\nAll author_handle values must use hash_handle(); all content must use sanitise_pii().",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
