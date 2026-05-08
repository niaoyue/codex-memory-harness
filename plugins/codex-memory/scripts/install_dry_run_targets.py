from __future__ import annotations

from pathlib import Path
from typing import Any

from install_support import (
    AGENTS_END,
    AGENTS_START,
    POSIX_PROFILE_END,
    POSIX_PROFILE_START,
    PROFILE_END,
    PROFILE_START,
    agents_block,
    home_agents_path,
    posix_profile_paths,
    profile_paths,
    read_text,
    replace_marked_block,
)
from profile_blocks import posix_profile_block, profile_block
from profile_install import _install_profile_shells
from skill_bundle import bundled_skills_status


def agents_plan(home_plugin: Path) -> dict[str, Any]:
    path = home_agents_path()
    current = read_text(path)
    if AGENTS_START not in current and "## Codex Memory 全局无感使用" in current:
        return {
            "path": str(path),
            "category": "agents",
            "status": "existing_unmarked_kept",
            "action": "no_change",
            "would_write": False,
        }
    updated, status = replace_marked_block(current, AGENTS_START, AGENTS_END, agents_block(home_plugin))
    return {
        "path": str(path),
        "category": "agents",
        "status": status if updated != current else "no_change",
        "action": status if updated != current else "no_change",
        "would_write": updated != current,
        "markers": [AGENTS_START, AGENTS_END],
    }


def launcher_profiles_plan(
    home_plugin: Path,
    profile_shells: str,
    launcher_family: str,
) -> dict[str, Any]:
    if launcher_family == "posix":
        shells = _install_profile_shells(profile_shells, "posix")
        return {
            "powershell_profiles": skipped("launcher_family_posix"),
            "posix_profiles": profile_group_plan(
                posix_profile_paths(shells),
                posix_profile_block(home_plugin),
                POSIX_PROFILE_START,
                POSIX_PROFILE_END,
                "posix_profile",
            ),
        }
    shells = _install_profile_shells(profile_shells, "powershell")
    return {
        "powershell_profiles": profile_group_plan(
            profile_paths(shells),
            profile_block(home_plugin),
            PROFILE_START,
            PROFILE_END,
            "powershell_profile",
        ),
        "posix_profiles": skipped("launcher_family_not_posix"),
    }


def profile_group_plan(
    paths: list[Path],
    block: str,
    start_marker: str,
    end_marker: str,
    category: str,
) -> list[dict[str, Any]]:
    plans = []
    for path in paths:
        current = read_text(path)
        updated, status = replace_marked_block(current, start_marker, end_marker, block)
        plans.append(
            {
                "path": str(path),
                "category": category,
                "exists": path.exists(),
                "status": status if updated != current else "no_change",
                "action": status if updated != current else "no_change",
                "would_write": updated != current,
                "markers": [start_marker, end_marker],
            }
        )
    return plans


def bundled_skills_plan(plugin_root: Path) -> dict[str, Any]:
    status = bundled_skills_status(plugin_root)
    skills = []
    for item in status["skills"]:
        if not item["source_exists"]:
            action = "blocked_missing_source"
        elif item["target_has_skill_md"]:
            action = "no_change"
        elif item["target_exists"]:
            action = "skip_existing_incomplete"
        else:
            action = "install"
        skills.append(
            {
                **item,
                "action": action,
                "would_write": action == "install",
                "blocked": action == "blocked_missing_source",
                "reason": "missing bundled skill source" if action == "blocked_missing_source" else "",
            }
        )
    return {
        **status,
        "category": "bundled_skills",
        "action": "install_missing_skills",
        "would_write": any(item["would_write"] for item in skills),
        "blocked": any(item["action"] == "blocked_missing_source" for item in skills),
        "skills": skills,
        "planned_install_count": sum(1 for item in skills if item["action"] == "install"),
    }


def home_skipped_targets(reason: str) -> dict[str, Any]:
    return {
        "codex_config": skipped(reason),
        "home_hooks_config": skipped(reason),
        "home_mcp_config": skipped(reason),
        "home_marketplace": skipped(reason),
        "home_agents": skipped(reason),
        "bundled_skills": skipped(reason),
        "powershell_profiles": [],
        "posix_profiles": [],
    }


def skipped(reason: str) -> dict[str, Any]:
    return {"skipped": True, "reason": reason, "would_write": False}


def blocked(category: str, path: str, reason: str) -> dict[str, Any]:
    return {"category": category, "path": path, "reason": reason}


def target_blocks(targets: dict[str, Any]) -> list[dict[str, Any]]:
    blocked_items: list[dict[str, Any]] = []
    for name, target in targets.items():
        for item in flatten_targets(target, include_aggregate=True):
            if item.get("blocked"):
                blocked_items.append(blocked(name, item.get("path", ""), item.get("reason", "blocked")))
    return blocked_items


def planned_writes(targets: dict[str, Any]) -> list[dict[str, str]]:
    writes: list[dict[str, str]] = []
    for name, target in targets.items():
        for item in flatten_targets(target):
            if item.get("would_write"):
                writes.append(
                    {
                        "target": name,
                        "path": str(item.get("path", "")),
                        "action": str(item.get("action", item.get("status", "write"))),
                    }
                )
    return writes


def flatten_targets(value: Any, *, include_aggregate: bool = False) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "skills" in value and isinstance(value["skills"], list):
            items = [item for item in value["skills"] if isinstance(item, dict)]
            return [value, *items] if include_aggregate and value.get("blocked") else items
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []
