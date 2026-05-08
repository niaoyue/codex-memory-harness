from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codex_config_status import inspect_codex_config
from install_support import (
    dependency_status,
    home_agents_path,
    home_root,
    posix_profile_statuses,
    profile_statuses,
    read_text,
)
from skill_bundle import bundled_skills_status


def check_state(
    *,
    plugin_name: str,
    repo_marketplace: Path,
    home_marketplace: Path,
    plugin_root: Path,
    home_plugin: Path,
) -> dict[str, Any]:
    dependencies = dependency_status()
    codex_config = inspect_codex_config(home=home_root(), plugin_root=plugin_root)

    return {
        "plugin_root": str(plugin_root),
        "plugin_files": plugin_files(plugin_root),
        "repo_marketplace": marketplace_status(repo_marketplace, plugin_name),
        "home_plugin": {
            "path": str(home_plugin),
            "exists": home_plugin.exists() or home_plugin.is_symlink(),
            "resolved_path": safe_existing_target(home_plugin),
            "points_to_current": points_to(home_plugin, plugin_root),
        },
        "home_marketplace": marketplace_status(home_marketplace, plugin_name),
        "home_agents": {
            "path": str(home_agents_path()),
            "exists": home_agents_path().exists(),
            "mentions_memory": "Codex Memory" in read_text(home_agents_path()),
        },
        "powershell_profiles": profile_statuses("all"),
        "posix_profiles": posix_profile_statuses(),
        "codex_config": codex_config,
        "bundled_skills": bundled_skills_status(plugin_root),
        "dependencies": dependencies,
        "missing_dependencies": dependencies["missing"],
        "dependency_recommendations": dependencies["recommendations"],
    }


def plugin_files(plugin_root: Path) -> dict[str, bool]:
    return {
        "manifest": (plugin_root / ".codex-plugin" / "plugin.json").exists(),
        "mcp": (plugin_root / ".mcp.json").exists(),
        "mcp_launcher": (plugin_root / "scripts" / "mcp_launcher.ps1").exists()
        or (plugin_root / "scripts" / "mcp_launcher.sh").exists(),
        "hooks": (plugin_root / "hooks.json").exists(),
        "hook_launcher": (plugin_root / "scripts" / "hook_launcher.ps1").exists()
        or (plugin_root / "scripts" / "hook_launcher.sh").exists(),
        "codexm_launcher": (plugin_root / "scripts" / "codexm.ps1").exists()
        or (plugin_root / "scripts" / "codexm.sh").exists(),
        "hook_bridge": (plugin_root / "scripts" / "hook_bridge.py").exists(),
    }


def marketplace_status(path: Path, plugin_name: str) -> dict[str, Any]:
    status = {
        "path": str(path),
        "exists": path.exists(),
        "has_entry": False,
        "parse_ok": True,
        "error": "",
    }
    if not path.exists():
        return status
    try:
        status["has_entry"] = has_marketplace_entry(path, plugin_name)
    except (AttributeError, TypeError, json.JSONDecodeError) as exc:
        status["parse_ok"] = False
        status["error"] = str(exc)
    return status


def has_marketplace_entry(path: Path, plugin_name: str) -> bool:
    if not path.exists():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("marketplace JSON must be an object")
    interface = payload.get("interface", {})
    if not isinstance(interface, dict):
        raise TypeError("marketplace interface must be an object")
    plugins = payload.get("plugins", [])
    if not isinstance(plugins, list):
        raise TypeError("marketplace plugins must be a list")
    return any(item.get("name") == plugin_name for item in plugins)


def safe_existing_target(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "missing"
    try:
        resolved = path.resolve()
        return str(resolved)
    except OSError:
        return "unresolved"


def points_to(path: Path, target: Path) -> bool:
    if (not path.exists() and not path.is_symlink()) or not target.exists():
        return False
    try:
        return path.resolve() == target.resolve()
    except OSError:
        return False
