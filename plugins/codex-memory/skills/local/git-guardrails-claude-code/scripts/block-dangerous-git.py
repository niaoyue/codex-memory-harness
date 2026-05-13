#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys


DANGEROUS_PATTERNS = [
    r"\bgit\s+push\b",
    r"\bpush\s+--force\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\breset\s+--hard\b",
    r"\bgit\s+clean\s+-f(d)?\b",
    r"\bgit\s+branch\s+-D\b",
    r"\bgit\s+checkout\s+\.\b",
    r"\bgit\s+restore\s+\.\b",
]


def extract_command() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()

    raw = sys.stdin.read().strip()
    if not raw:
        return ""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            return command.strip()

    command = payload.get("command")
    if isinstance(command, str):
        return command.strip()

    return raw


def main() -> int:
    command = extract_command()
    if not command:
        print("Usage: block-dangerous-git.py <command> or pipe JSON/raw command on stdin", file=sys.stderr)
        return 1

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            print(
                f"BLOCKED: {command!r} matches dangerous pattern {pattern!r}.",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
