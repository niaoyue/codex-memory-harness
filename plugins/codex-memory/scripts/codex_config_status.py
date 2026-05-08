from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from official_memory_status import codex_home

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None


RECOMMENDED_HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse", "Stop")
REQUIRED_HOOKS_LINE = "hooks = true"


def inspect_codex_config(
    home: Path | None = None,
    *,
    plugin_root: Path | None = None,
) -> dict[str, Any]:
    root = codex_home(home)
    config_path = root / "config.toml"
    config = _read_toml(config_path)
    values = config.get("values") if isinstance(config.get("values"), dict) else {}
    plugin_hooks = _inspect_plugin_hooks(plugin_root)
    sandbox_mode = _string(values.get("sandbox_mode"))
    approval_policy = _string(values.get("approval_policy"))
    hooks = _nested(values, "features.hooks")
    legacy_codex_hooks = _nested(values, "features.codex_hooks")

    return {
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "config_parse_ok": config["ok"],
        "config_error": config["error"],
        "features_hooks": hooks if isinstance(hooks, bool) else None,
        "features_codex_hooks": legacy_codex_hooks if isinstance(legacy_codex_hooks, bool) else None,
        "hooks_enabled": hooks is True,
        "deprecated_codex_hooks_present": isinstance(legacy_codex_hooks, bool),
        "mcp_servers": sorted(_mcp_server_names(values)),
        "codex_memory_mcp_configured": "codex-memory" in _mcp_server_names(values),
        "sandbox_mode": sandbox_mode,
        "approval_policy": approval_policy,
        "sandbox_profile": _sandbox_profile(sandbox_mode, approval_policy),
        "agents_override": _agents_override_status(root),
        "plugin_hooks": plugin_hooks,
        "native_alignment": _native_alignment(hooks, plugin_hooks, sandbox_mode, approval_policy),
    }


def ensure_codex_config(
    home: Path | None = None,
    *,
    plugin_root: Path | None = None,
) -> dict[str, Any]:
    root = codex_home(home)
    config_path = root / "config.toml"
    before = inspect_codex_config(home, plugin_root=plugin_root)
    if not before["config_parse_ok"]:
        return {
            "config_path": str(config_path),
            "modified": False,
            "actions": [],
            "error": before["config_error"],
            "after": before,
            "recommendations": [
                "Fix Codex config.toml syntax, then rerun codex memory install."
            ],
        }
    if before["hooks_enabled"] and not before["deprecated_codex_hooks_present"]:
        return {
            "config_path": str(config_path),
            "modified": False,
            "actions": [],
            "error": "",
            "after": before,
            "recommendations": [],
        }

    current = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated, actions = _ensure_hooks_feature(current)
    validation = _parse_toml(updated)
    if not validation["ok"]:
        return {
            "config_path": str(config_path),
            "modified": False,
            "actions": [],
            "error": validation["error"],
            "after": before,
            "recommendations": [
                "Add [features] hooks = true to Codex config.toml manually."
            ],
        }

    root.mkdir(parents=True, exist_ok=True)
    config_path.write_text(updated, encoding="utf-8")
    after = inspect_codex_config(home, plugin_root=plugin_root)
    return {
        "config_path": str(config_path),
        "modified": updated != current,
        "actions": actions,
        "error": "",
        "after": after,
        "recommendations": [],
    }


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": True, "values": {}, "error": ""}
    return _parse_toml(path.read_text(encoding="utf-8"))


def _parse_toml(value: str) -> dict[str, Any]:
    if tomllib is None:
        return {"ok": False, "values": {}, "error": "tomllib is unavailable"}
    try:
        return {"ok": True, "values": tomllib.loads(value), "error": ""}
    except Exception as exc:
        return {"ok": False, "values": {}, "error": str(exc)}


def _ensure_hooks_feature(text: str) -> tuple[str, list[dict[str, Any]]]:
    lines = text.splitlines()
    features_index = _section_index(lines, "features")
    hooks_pattern = re.compile(r"^(\s*)hooks\s*=.*?(\s*(#.*))?$")
    legacy_pattern = re.compile(r"^\s*codex_hooks\s*=.*?(\s*(#.*))?$")
    action = "set_feature"
    if features_index is not None:
        insert_at = len(lines)
        hooks_index = None
        legacy_indexes = []
        for index in range(features_index + 1, len(lines)):
            section_name = _section_name(lines[index])
            if section_name:
                insert_at = index
                break
            if hooks_pattern.match(lines[index]):
                hooks_index = index
            elif legacy_pattern.match(lines[index]):
                legacy_indexes.append(index)
        if hooks_index is not None:
            lines[hooks_index] = hooks_pattern.sub(r"\1" + REQUIRED_HOOKS_LINE + r"\2", lines[hooks_index])
            for index in reversed(legacy_indexes):
                del lines[index]
            return _join_toml_lines(lines), [{"action": action, "key": "features.hooks", "value": True}]
        if legacy_indexes:
            first = legacy_indexes[0]
            lines[first] = REQUIRED_HOOKS_LINE
            for index in reversed(legacy_indexes[1:]):
                del lines[index]
            return _join_toml_lines(lines), [{"action": "replace_deprecated_feature", "from": "features.codex_hooks", "key": "features.hooks", "value": True}]
        lines.insert(features_index + 1, REQUIRED_HOOKS_LINE)
        return _join_toml_lines(lines), [{"action": action, "key": "features.hooks", "value": True}]

    dotted_hooks_pattern = re.compile(r"^(\s*)features\.hooks\s*=.*?(\s*(#.*))?$")
    for index, line in enumerate(lines):
        if dotted_hooks_pattern.match(line):
            lines[index] = dotted_hooks_pattern.sub(r"\1features." + REQUIRED_HOOKS_LINE + r"\2", line)
            lines = [item for item in lines if not re.match(r"^\s*features\.codex_hooks\s*=", item)]
            return _join_toml_lines(lines), [{"action": action, "key": "features.hooks", "value": True}]

    dotted_pattern = re.compile(r"^(\s*)features\.codex_hooks\s*=.*?(\s*(#.*))?$")
    for index, line in enumerate(lines):
        if dotted_pattern.match(line):
            lines[index] = dotted_pattern.sub(r"\1features." + REQUIRED_HOOKS_LINE + r"\2", line)
            return _join_toml_lines(lines), [{"action": "replace_deprecated_feature", "from": "features.codex_hooks", "key": "features.hooks", "value": True}]

    dotted_feature_pattern = re.compile(r"^\s*features\.[A-Za-z0-9_.-]+\s*=.*$")
    for index, line in enumerate(lines):
        if dotted_feature_pattern.match(line):
            lines.insert(index + 1, f"features.{REQUIRED_HOOKS_LINE}")
            return _join_toml_lines(lines), [{"action": action, "key": "features.hooks", "value": True}]

    base = text.rstrip()
    prefix = f"{base}\n\n" if base else ""
    updated = f"{prefix}[features]\n{REQUIRED_HOOKS_LINE}\n"
    return updated, [{"action": "add_section", "section": "features"}, {"action": action, "key": "features.hooks", "value": True}]


def _section_index(lines: list[str], name: str) -> int | None:
    for index, line in enumerate(lines):
        if _section_name(line) == name:
            return index
    return None


def _section_name(line: str) -> str:
    match = re.match(r"^\s*\[([A-Za-z0-9_.-]+)\]\s*(#.*)?$", line)
    return match.group(1) if match else ""


def _join_toml_lines(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def _inspect_plugin_hooks(plugin_root: Path | None) -> dict[str, Any]:
    if plugin_root is None:
        return {
            "path": "",
            "exists": False,
            "events": [],
            "covers_recommended_events": False,
            "missing_recommended_events": list(RECOMMENDED_HOOK_EVENTS),
        }
    path = plugin_root / "hooks.json"
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "events": [],
            "covers_recommended_events": False,
            "missing_recommended_events": list(RECOMMENDED_HOOK_EVENTS),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "path": str(path),
            "exists": True,
            "parse_ok": False,
            "error": str(exc),
            "events": [],
            "covers_recommended_events": False,
            "missing_recommended_events": list(RECOMMENDED_HOOK_EVENTS),
        }
    hooks = payload.get("hooks") if isinstance(payload, dict) else {}
    events = sorted(hooks.keys()) if isinstance(hooks, dict) else []
    missing = [
        event for event in RECOMMENDED_HOOK_EVENTS
        if event not in events or not _has_command_hook(hooks.get(event))
    ]
    return {
        "path": str(path),
        "exists": True,
        "parse_ok": True,
        "events": events,
        "covers_recommended_events": not missing,
        "missing_recommended_events": missing,
    }


def _has_command_hook(value: Any) -> bool:
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        nested = item.get("hooks")
        if isinstance(nested, list) and _has_command_hook(nested):
            return True
        if item.get("type") == "command" and _string(item.get("command")):
            return True
    return False


def _native_alignment(
    hooks: Any,
    plugin_hooks: dict[str, Any],
    sandbox_mode: str,
    approval_policy: str,
) -> dict[str, Any]:
    missing_hooks = plugin_hooks.get("missing_recommended_events") or []
    return {
        "ok": hooks is True and not missing_hooks,
        "recommended_primary_path": "official_config_hooks_mcp",
        "wrapper_role": "compatibility_and_diagnostics",
        "needs_hooks_feature": hooks is not True,
        "needs_hook_event_update": bool(missing_hooks),
        "high_risk_unattended_permissions": _is_high_risk_permission_profile(
            sandbox_mode,
            approval_policy,
        ),
    }


def _agents_override_status(root: Path) -> dict[str, Any]:
    path = root / "AGENTS.override.md"
    return {
        "path": str(path),
        "exists": path.exists(),
        "may_override_global_agents": path.exists(),
    }


def _mcp_server_names(values: dict[str, Any]) -> set[str]:
    servers = values.get("mcp_servers")
    if not isinstance(servers, dict):
        return set()
    return {str(name) for name in servers.keys()}


def _sandbox_profile(sandbox_mode: str, approval_policy: str) -> str:
    if _is_high_risk_permission_profile(sandbox_mode, approval_policy):
        return "high_risk_unattended_full_access"
    if sandbox_mode == "danger-full-access":
        return "full_access"
    if approval_policy == "never":
        return "unattended"
    if sandbox_mode or approval_policy:
        return "custom"
    return "default"


def _is_high_risk_permission_profile(sandbox_mode: str, approval_policy: str) -> bool:
    return sandbox_mode == "danger-full-access" and approval_policy == "never"


def _nested(payload: dict[str, Any], dotted: str) -> Any:
    value: Any = payload
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
