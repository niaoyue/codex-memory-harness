from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from codex_config_status import inspect_codex_config
from hook_config import hooks_config
from install_debug import debug_log
from install_status import check_state, points_to, safe_existing_target
from install_support import home_root, read_text, select_mcp_python_runtime
from install_dry_run_targets import (
    agents_plan,
    blocked as blocked_target,
    bundled_skills_plan,
    home_skipped_targets,
    launcher_profiles_plan,
    planned_writes,
    skipped,
    target_blocks,
)
from install_marketplace import PLUGIN_NAME, marketplace_plan
from mcp_config import MCP_PLUGIN_NAME, mcp_config


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_marketplace_path() -> Path:
    return _repo_root() / ".agents" / "plugins" / "marketplace.json"


def _home_root() -> Path:
    return home_root()


def _home_plugin_path() -> Path:
    return _home_root() / "plugins" / PLUGIN_NAME


def _home_marketplace_path() -> Path:
    return _home_root() / ".agents" / "plugins" / "marketplace.json"


def build_install_dry_run_plan(
    mode: str,
    scope: str,
    profile_shells: str,
    *,
    install_agents: bool,
    update_existing: bool,
    install_skills: bool,
    mcp_python_command: str | None = None,
    mcp_python_prefix_args: list[str] | None = None,
    launcher_family: str = "powershell",
) -> dict[str, Any]:
    launcher_family = _normalize_launcher_family(launcher_family)
    mcp_runtime = select_mcp_python_runtime(mcp_python_command, mcp_python_prefix_args)
    debug_log(
        "install_dry_run_start",
        {
            "scope": scope,
            "mode": mode,
            "launcher_family": launcher_family,
            "profile_shells": profile_shells,
            "install_agents": install_agents,
            "install_skills": install_skills,
            "update_existing": update_existing,
            "mcp_python_command": mcp_runtime["command"],
            "mcp_python_prefix_arg_count": len(mcp_runtime["prefix_args"]),
        },
    )

    targets: dict[str, Any] = {}
    blocked_items: list[dict[str, Any]] = []
    if scope in ("repo", "all"):
        targets["repo_hooks_config"] = _hooks_config_plan(_plugin_root(), launcher_family)
        targets["repo_mcp_config"] = _mcp_config_plan(_plugin_root(), mcp_runtime, launcher_family)
        targets["repo_marketplace"] = marketplace_plan(
            _repo_marketplace_path(),
            default_name="codex-memory-harness",
            default_display_name="Codex Memory Harness",
            source_path=f"./plugins/{PLUGIN_NAME}",
        )

    if scope in ("home", "all"):
        home_plugin = _home_plugin_plan(mode, update_existing=update_existing)
        targets["home_plugin"] = home_plugin
        if home_plugin.get("status") == "installed_elsewhere":
            blocked_items.append(blocked_target("home_plugin", home_plugin["path"], "installed_elsewhere"))
            targets.update(home_skipped_targets("installed_elsewhere"))
        else:
            home_plugin_path = _effective_home_plugin_path(home_plugin, mode)
            preview_plugin_path = _preview_home_plugin_files_path(home_plugin, mode)
            repo_preview_texts = (
                _repo_config_preview_texts(launcher_family)
                if scope == "all" and _home_plugin_sources_repo(home_plugin, mode)
                else {}
            )
            home_entry_path = _home_plugin_path()
            targets["codex_config"] = _codex_config_plan()
            targets["home_hooks_config"] = _hooks_config_plan(
                home_plugin_path,
                launcher_family,
                preview_plugin_path=preview_plugin_path,
                preview_text=repo_preview_texts.get("hooks.json"),
            )
            targets["home_mcp_config"] = _mcp_config_plan(
                home_plugin_path,
                mcp_runtime,
                launcher_family,
                preview_plugin_path=preview_plugin_path,
                preview_text=repo_preview_texts.get(".mcp.json"),
            )
            targets["home_marketplace"] = marketplace_plan(
                _home_marketplace_path(),
                default_name="local-user-plugins",
                default_display_name="Local User Plugins",
                source_path=f"./plugins/{PLUGIN_NAME}",
            )
            targets["home_agents"] = (
                agents_plan(home_entry_path) if install_agents else skipped("skip_agents")
            )
            targets["bundled_skills"] = (
                bundled_skills_plan(_plugin_root()) if install_skills else skipped("skip_skills")
            )
            targets.update(launcher_profiles_plan(home_entry_path, profile_shells, launcher_family))

    blocked_items.extend(target_blocks(targets))
    result = {
        "dry_run": True,
        "operation": "install",
        "scope": scope,
        "mode": mode,
        "launcher_family": launcher_family,
        "profile_shells": profile_shells,
        "mcp_runtime": mcp_runtime,
        "update_existing": update_existing,
        "install_agents": install_agents,
        "install_skills": install_skills,
        "targets": targets,
        "planned_writes": planned_writes(targets),
        "blocked": blocked_items,
        "check": _check_state(),
    }
    debug_log(
        "install_dry_run_complete",
        {
            "target_count": len(targets),
            "planned_write_count": len(result["planned_writes"]),
            "blocked_count": len(blocked_items),
        },
    )
    return result


def _normalize_launcher_family(value: str) -> str:
    return "posix" if value == "posix" else "powershell"


def _home_plugin_plan(mode: str, *, update_existing: bool) -> dict[str, Any]:
    src = _plugin_root()
    dst = _home_plugin_path()
    exists = dst.exists() or dst.is_symlink()
    resolved = safe_existing_target(dst)
    if not exists:
        return {
            "path": str(dst),
            "source": str(src),
            "status": "would_install",
            "mode": _resolved_home_plugin_mode(mode),
            "would_write": True,
            "reason": "missing",
        }
    if points_to(dst, src):
        return {
            "path": str(dst),
            "source": str(src),
            "status": "already_installed",
            "resolved_path": resolved,
            "would_write": False,
        }
    if not update_existing:
        return {
            "path": str(dst),
            "source": str(src),
            "status": "installed_elsewhere",
            "resolved_path": resolved,
            "would_write": False,
            "recommended_action": "Run install.bat --update-existing to update this installation to the current package.",
        }
    return {
        "path": str(dst),
        "source": str(src),
        "status": "would_replace_existing",
        "resolved_path": resolved,
        "mode": _resolved_home_plugin_mode(mode),
        "replacement": _replacement_plan(dst),
        "would_write": True,
    }


def _effective_home_plugin_path(home_plugin: dict[str, Any], mode: str) -> Path:
    if home_plugin.get("status") in {"would_install", "would_replace_existing"}:
        resolved_mode = str(home_plugin.get("mode") or _resolved_home_plugin_mode(mode))
        if resolved_mode in {"junction", "symlink"}:
            return _plugin_root()
    return _home_plugin_path()


def _preview_home_plugin_files_path(home_plugin: dict[str, Any], mode: str) -> Path | None:
    if home_plugin.get("status") not in {"would_install", "would_replace_existing"}:
        return None
    resolved_mode = str(home_plugin.get("mode") or _resolved_home_plugin_mode(mode))
    if resolved_mode == "copy":
        return _plugin_root()
    return None


def _home_plugin_sources_repo(home_plugin: dict[str, Any], mode: str) -> bool:
    status = home_plugin.get("status")
    if status == "already_installed":
        return True
    if status not in {"would_install", "would_replace_existing"}:
        return False
    resolved_mode = str(home_plugin.get("mode") or _resolved_home_plugin_mode(mode))
    return resolved_mode in {"junction", "symlink", "copy"}


def _resolved_home_plugin_mode(mode: str) -> str:
    if mode != "auto":
        return mode
    return "junction" if os.name == "nt" else "symlink"


def _replacement_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {"mode": "symlink", "action": "unlink"}
    if bool(getattr(path, "is_junction", lambda: False)()):
        return {"mode": "junction", "action": "rmdir"}
    return {"mode": "backup", "action": "rename_to_timestamped_backup"}


def _hooks_config_plan(
    plugin_root: Path,
    launcher_family: str,
    *,
    preview_plugin_path: Path | None = None,
    preview_text: str | None = None,
) -> dict[str, Any]:
    path = plugin_root / "hooks.json"
    preview_path = preview_plugin_path / "hooks.json" if preview_plugin_path else None
    payload = hooks_config(launcher_family)
    return _json_file_plan(
        path,
        payload,
        "hooks_config",
        {
            "launcher_family": launcher_family,
            "events": list(payload["hooks"].keys()),
            "commands": [
                hook["command"]
                for event_hooks in payload["hooks"].values()
                for item in event_hooks
                for hook in item["hooks"]
            ],
        },
        preview_path=preview_path,
        preview_text=preview_text,
    )


def _mcp_config_plan(
    plugin_root: Path,
    mcp_runtime: dict[str, Any],
    launcher_family: str,
    *,
    preview_plugin_path: Path | None = None,
    preview_text: str | None = None,
) -> dict[str, Any]:
    path = plugin_root / ".mcp.json"
    preview_path = preview_plugin_path / ".mcp.json" if preview_plugin_path else None
    payload = mcp_config(launcher_family)
    server = payload["mcpServers"][MCP_PLUGIN_NAME]
    return _json_file_plan(
        path,
        payload,
        "mcp_config",
        {
            "launcher_family": launcher_family,
            "command": server["command"],
            "args": list(server["args"]),
            "python_command": mcp_runtime["command"],
            "python_prefix_args": list(mcp_runtime["prefix_args"]),
        },
        preview_path=preview_path,
        preview_text=preview_text,
    )


def _json_file_plan(
    path: Path,
    payload: dict[str, Any],
    category: str,
    extra: dict[str, Any],
    *,
    preview_path: Path | None = None,
    preview_text: str | None = None,
) -> dict[str, Any]:
    current_path = preview_path or path
    if preview_text is None:
        current = current_path.read_text(encoding="utf-8") if current_path.exists() else ""
        planned_exists = current_path.exists()
    else:
        current = preview_text
        planned_exists = True
    matches = False
    parse_error = ""
    if current.strip():
        try:
            matches = json.loads(current) == payload
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    action = "no_change" if matches else ("update_file" if planned_exists else "create_file")
    return {
        "path": str(path),
        "category": category,
        "exists": path.exists(),
        "preview_source_path": str(current_path),
        "preview_source_exists": planned_exists,
        "action": action,
        "would_write": action != "no_change",
        "parse_error": parse_error,
        **extra,
    }


def _repo_config_preview_texts(launcher_family: str) -> dict[str, str]:
    return {
        "hooks.json": _json_payload_text(hooks_config(launcher_family)),
        ".mcp.json": _json_payload_text(mcp_config(launcher_family)),
    }


def _json_payload_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _codex_config_plan() -> dict[str, Any]:
    state = inspect_codex_config(home=_home_root(), plugin_root=_plugin_root())
    path = state["config_path"]
    if not state["config_parse_ok"]:
        return {
            "path": path,
            "category": "codex_config",
            "status": "parse_error",
            "action": "blocked",
            "would_write": False,
            "blocked": True,
            "reason": state["config_error"],
        }
    if state["hooks_enabled"] and not state.get("deprecated_codex_hooks_present"):
        action = "no_change"
        would_write = False
    elif state["hooks_enabled"]:
        action = "remove_deprecated_features.codex_hooks"
        would_write = True
    else:
        action = "set_features.hooks"
        would_write = True
    return {
        "path": path,
        "category": "codex_config",
        "status": "hooks_enabled" if state["hooks_enabled"] else "hooks_disabled",
        "action": action,
        "would_write": would_write,
        "key": "features.hooks",
        "value": True,
    }

def _check_state() -> dict[str, Any]:
    return check_state(
        plugin_name=PLUGIN_NAME,
        repo_marketplace=_repo_marketplace_path(),
        home_marketplace=_home_marketplace_path(),
        plugin_root=_plugin_root(),
        home_plugin=_home_plugin_path(),
    )
