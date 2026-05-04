from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MCP_PLUGIN_NAME = "codex-memory"
MCP_LAUNCHER_ARGS = [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "./scripts/mcp_launcher.ps1",
    "--stdio",
    "--memory-scope",
    "project",
]


def mcp_config() -> dict[str, Any]:
    return {
        "mcpServers": {
            MCP_PLUGIN_NAME: {
                "command": "powershell",
                "args": list(MCP_LAUNCHER_ARGS),
            }
        }
    }


def json_matches_payload(current: str, payload: dict[str, Any]) -> bool:
    if not current.strip():
        return False
    try:
        return json.loads(current) == payload
    except json.JSONDecodeError:
        return False


def ensure_mcp_config(
    plugin_root: Path,
    *,
    python_command: str,
    python_prefix_args: list[str],
) -> dict[str, Any]:
    path = plugin_root / ".mcp.json"
    payload = mcp_config()
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    modified = not json_matches_payload(current, payload)
    if modified:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
    server = payload["mcpServers"][MCP_PLUGIN_NAME]
    return {
        "path": str(path),
        "modified": modified,
        "command": server["command"],
        "args": list(server["args"]),
        "python_command": python_command,
        "python_prefix_args": list(python_prefix_args),
    }
