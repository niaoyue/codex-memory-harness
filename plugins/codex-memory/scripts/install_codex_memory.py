from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from install_support import (
    AGENTS_END,
    AGENTS_START,
    PROFILE_END,
    PROFILE_START,
    ensure_agents,
    ensure_profile,
    home_agents_path,
    profile_paths,
    profile_statuses,
    read_text,
    remove_marked_block,
)


PLUGIN_NAME = "codex-memory"
PLUGIN_CATEGORY = "Productivity"
PLUGIN_POLICY = {
    "installation": "INSTALLED_BY_DEFAULT",
    "authentication": "ON_INSTALL",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_marketplace_path() -> Path:
    return _repo_root() / ".agents" / "plugins" / "marketplace.json"


def _home_root() -> Path:
    return Path.home()


def _home_plugin_path() -> Path:
    return _home_root() / "plugins" / PLUGIN_NAME


def _home_marketplace_path() -> Path:
    return _home_root() / ".agents" / "plugins" / "marketplace.json"


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default, ensure_ascii=False))
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _entry_for(source_path: str) -> dict[str, Any]:
    return {
        "name": PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": source_path,
        },
        "policy": dict(PLUGIN_POLICY),
        "category": PLUGIN_CATEGORY,
    }


def _upsert_marketplace_entry(
    path: Path,
    default_name: str,
    default_display_name: str,
    source_path: str,
) -> dict[str, Any]:
    marketplace = _read_json(
        path,
        {
            "name": default_name,
            "interface": {"displayName": default_display_name},
            "plugins": [],
        },
    )
    plugins = marketplace.setdefault("plugins", [])
    interface = marketplace.setdefault("interface", {})
    interface.setdefault("displayName", default_display_name)
    marketplace.setdefault("name", default_name)

    entry = _entry_for(source_path)
    for index, existing in enumerate(plugins):
        if existing.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            _write_json(path, marketplace)
            return {"path": str(path), "updated": True, "created": False}

    plugins.append(entry)
    _write_json(path, marketplace)
    return {"path": str(path), "updated": False, "created": True}


def _remove_marketplace_entry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "removed": False}
    marketplace = _read_json(path, {"plugins": []})
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        return {"path": str(path), "exists": True, "removed": False}
    original_count = len(plugins)
    marketplace["plugins"] = [
        item for item in plugins if not (isinstance(item, dict) and item.get("name") == PLUGIN_NAME)
    ]
    removed = len(marketplace["plugins"]) != original_count
    if removed:
        _write_json(path, marketplace)
    return {"path": str(path), "exists": True, "removed": removed}


def _safe_existing_target(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        resolved = path.resolve()
        return str(resolved)
    except OSError:
        return "unresolved"


def _points_to(path: Path, target: Path) -> bool:
    if not path.exists() or not target.exists():
        return False
    try:
        return path.resolve() == target.resolve()
    except OSError:
        return False


def _remove_existing_home_plugin(
    dst: Path,
    *,
    remove_current: bool = False,
) -> dict[str, Any]:
    if not dst.exists():
        return {"path": str(dst), "removed": False, "reason": "missing"}
    if _points_to(dst, _plugin_root()) and not remove_current:
        return {"path": str(dst), "removed": False, "reason": "already_current"}

    is_link = dst.is_symlink()
    is_junction = bool(getattr(dst, "is_junction", lambda: False)())
    if is_link:
        dst.unlink()
        return {"path": str(dst), "removed": True, "mode": "symlink"}
    if is_junction:
        dst.rmdir()
        return {"path": str(dst), "removed": True, "mode": "junction"}

    backup = dst.with_name(
        f"{dst.name}.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    os.replace(dst, backup)
    return {"path": str(dst), "removed": True, "mode": "backup", "backup_path": str(backup)}


def _ensure_windows_junction(src: Path, dst: Path) -> dict[str, Any]:
    if dst.exists():
        if dst.resolve() == src.resolve():
            return {"path": str(dst), "mode": "junction", "created": False, "status": "ok"}
        raise RuntimeError(
            f"Destination already exists and does not point at source: {dst} -> {_safe_existing_target(dst)}"
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    command = ["cmd", "/c", "mklink", "/J", str(dst), str(src)]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return {
        "path": str(dst),
        "mode": "junction",
        "created": True,
        "status": completed.stdout.strip() or "ok",
    }


def _ensure_copy(src: Path, dst: Path) -> dict[str, Any]:
    if dst.exists():
        if dst.resolve() == src.resolve():
            return {"path": str(dst), "mode": "copy", "created": False, "status": "ok"}
        raise RuntimeError(
            f"Destination already exists and will not be overwritten automatically: {dst}"
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return {"path": str(dst), "mode": "copy", "created": True, "status": "ok"}


def _ensure_home_plugin_install(mode: str, *, update_existing: bool) -> dict[str, Any]:
    src = _plugin_root()
    dst = _home_plugin_path()
    replacement = None
    if dst.exists():
        if _points_to(dst, src):
            return {
                "path": str(dst),
                "mode": "current",
                "created": False,
                "status": "already_installed",
                "resolved_path": _safe_existing_target(dst),
                "replacement": None,
            }
        if not update_existing:
            return {
                "path": str(dst),
                "created": False,
                "status": "installed_elsewhere",
                "resolved_path": _safe_existing_target(dst),
                "recommended_action": "Run install.ps1 -UpdateExisting to update this installation to the current package.",
            }
        replacement = _remove_existing_home_plugin(dst)
    if mode == "copy":
        result = _ensure_copy(src, dst)
        result["replacement"] = replacement
        return result
    try:
        result = _ensure_windows_junction(src, dst)
    except Exception as exc:
        if mode == "junction":
            raise
        result = _ensure_copy(src, dst)
        result["fallback_reason"] = f"{type(exc).__name__}: {exc}"
    result["replacement"] = replacement
    return result


def _check_state() -> dict[str, Any]:
    repo_marketplace = _repo_marketplace_path()
    home_marketplace = _home_marketplace_path()
    plugin_root = _plugin_root()
    home_plugin = _home_plugin_path()
    def _has_entry(path: Path) -> bool:
        if not path.exists():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        return any(item.get("name") == PLUGIN_NAME for item in payload.get("plugins", []))

    return {
        "plugin_root": str(plugin_root),
        "plugin_files": {
            "manifest": (plugin_root / ".codex-plugin" / "plugin.json").exists(),
            "mcp": (plugin_root / ".mcp.json").exists(),
            "hooks": (plugin_root / "hooks.json").exists(),
            "hook_bridge": (plugin_root / "scripts" / "hook_bridge.py").exists(),
        },
        "repo_marketplace": {
            "path": str(repo_marketplace),
            "exists": repo_marketplace.exists(),
            "has_entry": _has_entry(repo_marketplace),
        },
        "home_plugin": {
            "path": str(home_plugin),
            "exists": home_plugin.exists(),
            "resolved_path": _safe_existing_target(home_plugin),
            "points_to_current": _points_to(home_plugin, plugin_root),
        },
        "home_marketplace": {
            "path": str(home_marketplace),
            "exists": home_marketplace.exists(),
            "has_entry": _has_entry(home_marketplace),
        },
        "home_agents": {
            "path": str(home_agents_path()),
            "exists": home_agents_path().exists(),
            "mentions_memory": "Codex Memory" in read_text(home_agents_path()),
        },
        "powershell_profiles": profile_statuses("all"),
    }


def install(
    mode: str,
    scope: str,
    profile_shells: str,
    *,
    install_agents: bool,
    update_existing: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {"scope": scope, "mode": mode}
    if scope in ("repo", "all"):
        result["repo_marketplace"] = _upsert_marketplace_entry(
            _repo_marketplace_path(),
            default_name="codex-memory-harness",
            default_display_name="Codex Memory Harness",
            source_path=f"./plugins/{PLUGIN_NAME}",
        )
    if scope in ("home", "all"):
        result["home_plugin"] = _ensure_home_plugin_install(
            mode,
            update_existing=update_existing,
        )
        if result["home_plugin"].get("status") == "installed_elsewhere":
            result["home_marketplace"] = {"skipped": True, "reason": "installed_elsewhere"}
            result["home_agents"] = {"skipped": True, "reason": "installed_elsewhere"}
            result["powershell_profiles"] = []
        else:
            result["home_marketplace"] = _upsert_marketplace_entry(
                _home_marketplace_path(),
                default_name="local-user-plugins",
                default_display_name="Local User Plugins",
                source_path=f"./plugins/{PLUGIN_NAME}",
            )
            if install_agents:
                result["home_agents"] = ensure_agents(_home_plugin_path())
            result["powershell_profiles"] = ensure_profile(_home_plugin_path(), profile_shells)
    result["check"] = _check_state()
    return result


def uninstall(profile_shells: str, *, remove_home_plugin: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "repo_marketplace": _remove_marketplace_entry(_repo_marketplace_path()),
        "home_marketplace": _remove_marketplace_entry(_home_marketplace_path()),
        "home_agents": remove_marked_block(home_agents_path(), AGENTS_START, AGENTS_END),
        "powershell_profiles": [
            remove_marked_block(path, PROFILE_START, PROFILE_END)
            for path in profile_paths(profile_shells)
        ],
    }
    if remove_home_plugin:
        result["home_plugin"] = _remove_existing_home_plugin(
            _home_plugin_path(),
            remove_current=True,
        )
    result["check"] = _check_state()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Codex Memory for no-touch local use.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only inspect current installation state.",
    )
    parser.add_argument(
        "--scope",
        choices=["repo", "home", "all"],
        default="all",
        help="Install repo marketplace, home plugin, or both.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "junction", "copy"],
        default="auto",
        help="Home install mode. Auto prefers a Windows junction and falls back to copy.",
    )
    parser.add_argument(
        "--profile-shells",
        choices=["pwsh", "windows", "all", "none"],
        default="pwsh",
        help="PowerShell profile(s) to update with codex/codexm functions.",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="Do not update ~/.codex/AGENTS.md.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Alias for --update-existing.",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update an existing ~/plugins/codex-memory that points at another source.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove marketplace entries and marked launcher/global-rules blocks.",
    )
    parser.add_argument(
        "--remove-home-plugin",
        action="store_true",
        help="With --uninstall, also remove ~/plugins/codex-memory.",
    )
    args = parser.parse_args()

    if args.check:
        result = {"check": _check_state()}
    elif args.uninstall:
        result = uninstall(args.profile_shells, remove_home_plugin=args.remove_home_plugin)
    else:
        result = install(
            args.mode,
            args.scope,
            args.profile_shells,
            install_agents=not args.skip_agents,
            update_existing=args.update_existing or args.replace_existing,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
