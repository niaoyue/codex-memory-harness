from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from install_debug import debug_log


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
MCP_POSIX_LAUNCHER_ARGS = [
    "./scripts/mcp_launcher.sh",
    "--stdio",
    "--memory-scope",
    "project",
]


def mcp_config(launcher_family: str = "powershell") -> dict[str, Any]:
    if launcher_family == "posix":
        server = {
            "command": "sh",
            "args": list(MCP_POSIX_LAUNCHER_ARGS),
        }
    else:
        server = {
            "command": "powershell",
            "args": list(MCP_LAUNCHER_ARGS),
        }
    return {
        "mcpServers": {
            MCP_PLUGIN_NAME: server,
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
    launcher_family: str = "powershell",
) -> dict[str, Any]:
    path = plugin_root / ".mcp.json"
    payload = mcp_config(launcher_family)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    modified = not json_matches_payload(current, payload)
    if modified:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
    server = payload["mcpServers"][MCP_PLUGIN_NAME]
    debug_log(
        "mcp_config_ensured",
        {
            "path": str(path),
            "launcher_family": launcher_family,
            "modified": modified,
            "command": server["command"],
            "python_command": python_command,
            "python_prefix_arg_count": len(python_prefix_args),
        },
    )
    return {
        "path": str(path),
        "modified": modified,
        "launcher_family": launcher_family,
        "command": server["command"],
        "args": list(server["args"]),
        "python_command": python_command,
        "python_prefix_args": list(python_prefix_args),
    }
