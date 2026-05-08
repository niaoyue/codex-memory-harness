from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from install_debug import debug_log


HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse", "Stop")


def hook_command(launcher_family: str, event: str) -> str:
    if launcher_family == "posix":
        return "sh ./scripts/hook_launcher.sh --codex-event " + shlex.quote(event)
    return "cmd /d /c .\\scripts\\hook_launcher.cmd --codex-event " + event


def hooks_config(launcher_family: str = "powershell") -> dict[str, Any]:
    return {
        "hooks": {
            event: [
                {
                    "matcher": ".*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_command(launcher_family, event),
                        }
                    ],
                }
            ]
            for event in HOOK_EVENTS
        }
    }


def json_matches_payload(current: str, payload: dict[str, Any]) -> bool:
    if not current.strip():
        return False
    try:
        return json.loads(current) == payload
    except json.JSONDecodeError:
        return False


def ensure_hooks_config(
    plugin_root: Path,
    *,
    launcher_family: str = "powershell",
) -> dict[str, Any]:
    path = plugin_root / "hooks.json"
    payload = hooks_config(launcher_family)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    modified = not json_matches_payload(current, payload)
    if modified:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
    commands = [
        hook["command"]
        for event_hooks in payload["hooks"].values()
        for item in event_hooks
        for hook in item["hooks"]
    ]
    debug_log(
        "hooks_config_ensured",
        {
            "path": str(path),
            "launcher_family": launcher_family,
            "modified": modified,
            "events": list(payload["hooks"].keys()),
        },
    )
    return {
        "path": str(path),
        "modified": modified,
        "launcher_family": launcher_family,
        "events": list(payload["hooks"].keys()),
        "commands": commands,
    }
