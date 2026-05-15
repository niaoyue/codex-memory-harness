from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codex_config_status import inspect_codex_config
from install_support import (
    AGENTS_END,
    AGENTS_START,
    dependency_status,
    home_agents_path,
    home_root,
    posix_profile_statuses,
    profile_statuses,
    read_text,
    stale_uncommitted_review_gate_lines,
)
from skill_bundle import bundled_skills_status


REQUIRED_SUBAGENT_DISPATCH_MARKERS = (
    "subagent_dispatch_plan.host_spawn_requests",
    "subagent_runtime.recommended=true",
    "host_dispatch_allowed=true",
    "spawn_agent",
    "不得只生成 dispatch plan",
    "长期明确授权",
    "当前 prompt 未再次写 SubAgent",
    "指定 role",
    "Implementation Specialist",
    "Workspace Coordinator",
    "Route Review Specialist",
    "XHigh Review Runner",
    "host_subagent_required",
    "OpenSpec",
    "openspec/changes/",
    "openspec/specs/",
    "autostart=true",
    "dispatch_required",
    "host_spawn_request_count",
    "actual_subagents=0",
    "downgrade_reason",
    "dispatch_id",
    "recommended_not_started",
)

REQUIRED_OPENSPEC_UPSTREAM_COMMAND_MARKERS = (
    "codex openspec upstream sync --version 1.3.1",
    "codex openspec upstream verify",
)

REQUIRED_OPENSPEC_UPSTREAM_DEFAULT_RULE_MARKERS = (
    "每个 Codex 窗口启动或进入项目后，默认先执行由 Codex Memory Harness 提供的启动自检",
    "OpenSpec upstream snapshot",
    "Codex Memory Harness 提供的项目初始化/自检步骤",
    "不代表目标项目自身已经实现",
    "启动自检",
    "默认流程",
    *REQUIRED_OPENSPEC_UPSTREAM_COMMAND_MARKERS,
    "显式禁用 OpenSpec",
    "只读/不写文件",
    "网络或 upstream 不可用",
    "降级必须",
)


def missing_required_subagent_dispatch_markers(agents_text: str) -> list[str]:
    return [
        marker
        for marker in REQUIRED_SUBAGENT_DISPATCH_MARKERS
        if marker not in agents_text
    ]


def missing_default_openspec_upstream_markers(agents_text: str) -> list[str]:
    return [
        marker
        for marker in REQUIRED_OPENSPEC_UPSTREAM_COMMAND_MARKERS
        if marker not in agents_text
    ]


def missing_default_openspec_upstream_rule_markers(agents_text: str) -> list[str]:
    return [
        marker
        for marker in REQUIRED_OPENSPEC_UPSTREAM_DEFAULT_RULE_MARKERS
        if marker not in agents_text
    ]


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
    agents_text = read_text(home_agents_path())
    missing_dispatch_markers = missing_required_subagent_dispatch_markers(agents_text)
    missing_openspec_upstream_markers = missing_default_openspec_upstream_markers(
        agents_text
    )
    missing_openspec_upstream_rule_markers = (
        missing_default_openspec_upstream_rule_markers(agents_text)
    )
    stale_review_gate_lines = stale_uncommitted_review_gate_lines(agents_text)
    mentions_candidate_review_gate = "candidate commit" in agents_text or "候选提交" in agents_text

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
            "mentions_memory": "Codex Memory" in agents_text,
            "has_marked_block": AGENTS_START in agents_text and AGENTS_END in agents_text,
            "has_legacy_unmarked_block": AGENTS_START not in agents_text
            and "## Codex Memory 全局无感使用" in agents_text,
            "mentions_current_openspec_layout": "openspec/changes/" in agents_text,
            "mentions_default_openspec_upstream": not missing_openspec_upstream_markers,
            "missing_default_openspec_upstream_markers": missing_openspec_upstream_markers,
            "mentions_default_openspec_upstream_rule": not missing_openspec_upstream_rule_markers,
            "missing_default_openspec_upstream_rule_markers": (
                missing_openspec_upstream_rule_markers
            ),
            "mentions_candidate_review_gate": mentions_candidate_review_gate,
            "has_stale_uncommitted_review_gate": bool(stale_review_gate_lines),
            "stale_uncommitted_review_gate_lines": stale_review_gate_lines,
            "review_gate_guidance_ok": mentions_candidate_review_gate
            and not stale_review_gate_lines,
            "mentions_required_subagent_dispatch": not missing_dispatch_markers,
            "missing_required_subagent_dispatch_markers": missing_dispatch_markers,
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
