#!/usr/bin/env python3
"""
Post-turn hook: runs ruff and mypy after any Python file modification.
Fails the turn if linting or type checking returns errors.
"""
import json
import subprocess
import sys

try:
    payload = json.loads(sys.stdin.read())
except (json.JSONDecodeError, EOFError):
    sys.exit(0)

tool_name = payload.get("tool_name", "")
if tool_name not in ("Write", "Edit"):
    sys.exit(0)

file_path = payload.get("tool_input", {}).get("file_path", "")
if not file_path.endswith(".py") or not file_path.startswith("/"):
    sys.exit(0)

errors = []

# ruff check
ruff_result = subprocess.run(
    ["uv", "run", "ruff", "check", file_path, "--output-format=text"],
    capture_output=True,
    text=True,
    cwd=file_path.rsplit("/pulseguard/", 1)[0] if "/pulseguard/" in file_path else ".",
)
if ruff_result.returncode != 0:
    errors.append(f"ruff:\n{ruff_result.stdout}")

if errors:
    print(
        "LINT/TYPE CHECK FAILED — fix before proceeding:\n\n" + "\n\n".join(errors),
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
