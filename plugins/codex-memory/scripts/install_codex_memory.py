from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_config_status import ensure_codex_config
from hook_config import ensure_hooks_config as _ensure_hooks_config
from install_dry_run import build_install_dry_run_plan
from install_debug import debug_log
from install_marketplace import (
    PLUGIN_CATEGORY,
    PLUGIN_NAME,
    PLUGIN_POLICY,
    remove_marketplace_entry as _remove_marketplace_entry,
    upsert_marketplace_entry as _upsert_marketplace_entry,
)
from install_status import check_state, points_to, safe_existing_target
from install_support import (
    AGENTS_END,
    AGENTS_START,
    ensure_agents,
    home_agents_path,
    home_root,
    remove_marked_block,
    select_mcp_python_runtime,
)
from mcp_config import ensure_mcp_config as _ensure_mcp_config
from mcp_config import mcp_config as _mcp_config
from profile_install import ensure_launcher_profiles, remove_launcher_profiles
from skill_bundle import ensure_bundled_skills


PROFILE_SHELL_CHOICES = ["auto", "pwsh", "windows", "all", "none", "profile", "bash", "zsh"]


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


def _safe_existing_target(path: Path) -> str:
    return safe_existing_target(path)


def _points_to(path: Path, target: Path) -> bool:
    return points_to(path, target)


def _remove_existing_home_plugin(
    dst: Path,
    *,
    remove_current: bool = False,
) -> dict[str, Any]:
    if not dst.exists() and not dst.is_symlink():
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
    if dst.exists() or dst.is_symlink():
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


def _ensure_symlink(src: Path, dst: Path) -> dict[str, Any]:
    if dst.exists() or dst.is_symlink():
        if _points_to(dst, src):
            return {"path": str(dst), "mode": "symlink", "created": False, "status": "ok"}
        raise RuntimeError(
            f"Destination already exists and does not point at source: {dst} -> {_safe_existing_target(dst)}"
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src, target_is_directory=True)
    return {"path": str(dst), "mode": "symlink", "created": True, "status": "ok"}


def _ensure_copy(src: Path, dst: Path) -> dict[str, Any]:
    if dst.exists() or dst.is_symlink():
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
    if dst.exists() or dst.is_symlink():
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
                "recommended_action": "Run the current package installer with --update-existing to update this installation.",
            }
        replacement = _remove_existing_home_plugin(dst)
    if mode == "copy":
        result = _ensure_copy(src, dst)
        result["replacement"] = replacement
        return result
    if mode == "symlink":
        result = _ensure_symlink(src, dst)
        result["replacement"] = replacement
        return result
    if mode == "junction":
        result = _ensure_windows_junction(src, dst)
        result["replacement"] = replacement
        return result
    try:
        if os.name == "nt":
            result = _ensure_windows_junction(src, dst)
        else:
            result = _ensure_symlink(src, dst)
    except Exception as exc:
        result = _ensure_copy(src, dst)
        result["fallback_reason"] = f"{type(exc).__name__}: {exc}"
    result["replacement"] = replacement
    return result


def _check_state() -> dict[str, Any]:
    return check_state(
        plugin_name=PLUGIN_NAME,
        repo_marketplace=_repo_marketplace_path(),
        home_marketplace=_home_marketplace_path(),
        plugin_root=_plugin_root(),
        home_plugin=_home_plugin_path(),
    )


def _normalize_launcher_family(value: str) -> str:
    if value == "posix":
        return "posix"
    return "powershell"


def install(
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
    result: dict[str, Any] = {"scope": scope, "mode": mode, "launcher_family": launcher_family}
    mcp_runtime = select_mcp_python_runtime(mcp_python_command, mcp_python_prefix_args)
    debug_log(
        "install_start",
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
    if scope in ("repo", "all"):
        result["hooks_config"] = _ensure_hooks_config(
            _plugin_root(),
            launcher_family=launcher_family,
        )
        result["mcp_config"] = _ensure_mcp_config(
            _plugin_root(),
            python_command=mcp_runtime["command"],
            python_prefix_args=mcp_runtime["prefix_args"],
            launcher_family=launcher_family,
        )
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
        result["codex_config"] = ensure_codex_config(home=_home_root(), plugin_root=_plugin_root())
        if result["home_plugin"].get("status") == "installed_elsewhere":
            result["home_marketplace"] = {"skipped": True, "reason": "installed_elsewhere"}
            result["home_agents"] = {"skipped": True, "reason": "installed_elsewhere"}
            result["bundled_skills"] = {"skipped": True, "reason": "installed_elsewhere"}
            result["powershell_profiles"] = []
        else:
            result["hooks_config"] = _ensure_hooks_config(
                _home_plugin_path(),
                launcher_family=launcher_family,
            )
            result["mcp_config"] = _ensure_mcp_config(
                _home_plugin_path(),
                python_command=mcp_runtime["command"],
                python_prefix_args=mcp_runtime["prefix_args"],
                launcher_family=launcher_family,
            )
            result["home_marketplace"] = _upsert_marketplace_entry(
                _home_marketplace_path(),
                default_name="local-user-plugins",
                default_display_name="Local User Plugins",
                source_path=f"./plugins/{PLUGIN_NAME}",
            )
            if install_agents:
                result["home_agents"] = ensure_agents(_home_plugin_path())
            if install_skills:
                result["bundled_skills"] = ensure_bundled_skills(_plugin_root())
            else:
                result["bundled_skills"] = {"skipped": True, "reason": "skip_skills"}
            result.update(
                ensure_launcher_profiles(
                    _home_plugin_path(),
                    profile_shells,
                    launcher_family,
                )
            )
    result["check"] = _check_state()
    debug_log(
        "install_complete",
        {
            "scope": scope,
            "mode": mode,
            "launcher_family": launcher_family,
            "home_plugin_status": result.get("home_plugin", {}).get("status"),
            "home_plugin_mode": result.get("home_plugin", {}).get("mode"),
            "home_plugin_fallback": "fallback_reason" in result.get("home_plugin", {}),
            "mcp_command": result.get("mcp_config", {}).get("command"),
            "hooks_modified": result.get("hooks_config", {}).get("modified"),
            "posix_profile_count": len(result.get("posix_profiles", []))
            if isinstance(result.get("posix_profiles"), list)
            else 0,
        },
    )
    return result


def uninstall(profile_shells: str, launcher_family: str, *, remove_home_plugin: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "repo_marketplace": _remove_marketplace_entry(_repo_marketplace_path()),
        "home_marketplace": _remove_marketplace_entry(_home_marketplace_path()),
        "home_agents": remove_marked_block(home_agents_path(), AGENTS_START, AGENTS_END),
        **remove_launcher_profiles(profile_shells, _normalize_launcher_family(launcher_family)),
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
        choices=["auto", "junction", "symlink", "copy"],
        default="auto",
        help="Home install mode.",
    )
    parser.add_argument(
        "--profile-shells",
        choices=PROFILE_SHELL_CHOICES,
        default="all",
        help="PowerShell or POSIX profile(s) to update with codex/codexm functions.",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="Do not update ~/.codex/AGENTS.md.",
    )
    parser.add_argument(
        "--skip-skills",
        action="store_true",
        help="Do not install bundled Codex skills into ~/.agents/skills.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview install targets and planned writes without changing files.",
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
        "--no-update-existing",
        action="store_true",
        help="Do not replace an existing ~/plugins/codex-memory that points at another source.",
    )
    parser.add_argument(
        "--mcp-python-command",
        default=None,
        help="Python command to write into .mcp.json.",
    )
    parser.add_argument(
        "--mcp-python-prefix-arg",
        action="append",
        default=None,
        help="Prefix argument for the MCP Python command. Repeat for multiple args.",
    )
    parser.add_argument(
        "--launcher-family",
        choices=["powershell", "posix"],
        default="powershell",
        help="Launcher family to write into hooks.json and .mcp.json.",
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
    update_existing = args.update_existing or args.replace_existing or not args.no_update_existing

    if args.check:
        result = {"check": _check_state()}
    elif args.dry_run:
        result = build_install_dry_run_plan(
            args.mode,
            args.scope,
            args.profile_shells,
            install_agents=not args.skip_agents,
            update_existing=update_existing,
            install_skills=not args.skip_skills,
            mcp_python_command=args.mcp_python_command,
            mcp_python_prefix_args=args.mcp_python_prefix_arg,
            launcher_family=args.launcher_family,
        )
    elif args.uninstall:
        result = uninstall(args.profile_shells, args.launcher_family, remove_home_plugin=args.remove_home_plugin)
    else:
        result = install(
            args.mode,
            args.scope,
            args.profile_shells,
            install_agents=not args.skip_agents,
            update_existing=update_existing,
            install_skills=not args.skip_skills,
            mcp_python_command=args.mcp_python_command,
            mcp_python_prefix_args=args.mcp_python_prefix_arg,
            launcher_family=args.launcher_family,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
