from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_PROFILE = ".codex/harness/project_profile.json"
WORKSPACE_CONFIG = ".codex/harness/workspace-routing.json"
EXECUTION_MODELS = {"main_agent_serial", "host_subagent_or_manual"}


def apply_runtime_policy(
    workspace_root: Path,
    route_plan: dict[str, Any],
    task: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = select_runtime_policy(workspace_root, route_plan, task, config=config)
    if not policy:
        return route_plan
    plan = dict(route_plan)
    plan["subagent_runtime_policy"] = policy
    return plan


def select_runtime_policy(
    workspace_root: Path,
    route_plan: dict[str, Any],
    task: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace_config = config if isinstance(config, dict) else read_json_object(workspace_root / WORKSPACE_CONFIG)
    for policy in workspace_project_policies(workspace_config, route_plan):
        normalized = matching_policy(policy, route_plan, task)
        if normalized:
            return normalized

    for policy in project_profile_policies(workspace_root, route_plan) + workspace_level_policies(workspace_config):
        normalized = matching_policy(policy, route_plan, task)
        if normalized:
            return normalized
    return {}


def workspace_project_policies(config: dict[str, Any], route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    projects = config.get("projects") if isinstance(config.get("projects"), list) else []
    affected = affected_project_ids(route_plan)
    policies: list[dict[str, Any]] = []
    for project_id in affected:
        for item in projects:
            if not isinstance(item, dict) or str(item.get("id") or "") != project_id:
                continue
            policy = item.get("subagent_runtime_policy")
            if isinstance(policy, dict):
                policies.append(policy)
    return policies


def workspace_level_policies(config: dict[str, Any]) -> list[dict[str, Any]]:
    policy = config.get("subagent_runtime_policy")
    return [policy] if isinstance(policy, dict) else []


def project_profile_policies(workspace_root: Path, route_plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    policies = []
    seen_paths: set[str] = set()
    for root in project_profile_roots(workspace_root, route_plan or {}):
        path = project_profile_path(root)
        key = path.resolve(strict=False).as_posix().lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        profile = read_json_object(path)
        for value in (
            profile.get("subagent_runtime_policy"),
            dict_value(profile.get("harness")).get("subagent_runtime_policy"),
        ):
            if isinstance(value, dict):
                policies.append(value)
    return policies


def project_profile_path(workspace_root: Path) -> Path:
    return resolve_project_root(workspace_root) / PROJECT_PROFILE


def project_profile_roots(workspace_root: Path, route_plan: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    base = workspace_root.resolve(strict=False)
    for route in route_plan.get("routes") if isinstance(route_plan.get("routes"), list) else []:
        if not isinstance(route, dict):
            continue
        route_cwd = string(route.get("cwd") or route.get("path"))
        if not route_cwd or route_cwd == ".":
            continue
        path = Path(route_cwd)
        candidate = path if path.is_absolute() else base / path
        if is_within(candidate, base):
            candidates.append(candidate)
    candidates.append(workspace_root)
    return sorted_project_profile_roots(candidates)


def sorted_project_profile_roots(candidates: list[Path]) -> list[Path]:
    roots: list[tuple[int, int, Path]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        root = resolve_project_root(candidate)
        key = root.resolve(strict=False).as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append((len(root.resolve(strict=False).parts), index, root))
    roots.sort(key=lambda item: (-item[0], item[1]))
    return [root for _, _, root in roots]


def resolve_project_root(start: Path) -> Path:
    current = start.resolve(strict=False)
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (candidate / PROJECT_PROFILE).exists():
            return candidate
    return current


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def matching_policy(policy: dict[str, Any], route_plan: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    if not selectors_match(policy, route_plan, task):
        return {}
    if policy.get("enabled") is False:
        return {
            "execution_model": "main_agent_serial",
            "autostart": False,
            "reason": string(policy.get("reason")) or "SubAgent runtime policy is disabled for this route.",
        }
    execution_model = string(policy.get("execution_model"))
    if execution_model not in EXECUTION_MODELS:
        return {}
    reason = string(policy.get("reason")) or "Project policy requests host SubAgent dispatch for this route."
    return {
        "execution_model": execution_model,
        "autostart": bool(policy.get("autostart")),
        "reason": reason,
    }


def selectors_match(policy: dict[str, Any], route_plan: dict[str, Any], task: dict[str, Any]) -> bool:
    return (
        value_allowed(string(route_plan.get("task_type") or "implementation"), string_list(policy.get("task_types")))
        and value_allowed(string(route_plan.get("risk_level") or "medium"), string_list(policy.get("risk_levels")))
        and value_allowed(string(route_plan.get("mode") or ""), string_list(policy.get("modes")))
        and projects_allowed(route_plan, string_list(policy.get("project_ids")))
        and task_not_disabled(task)
    )


def projects_allowed(route_plan: dict[str, Any], project_ids: list[str]) -> bool:
    if not project_ids:
        return True
    affected = set(affected_project_ids(route_plan))
    return "*" in project_ids or bool(affected.intersection(project_ids))


def affected_project_ids(route_plan: dict[str, Any]) -> list[str]:
    values = string_list(route_plan.get("affected_projects"))
    primary = string(route_plan.get("primary_project"))
    if primary:
        values.insert(0, primary)
    for route in route_plan.get("routes") if isinstance(route_plan.get("routes"), list) else []:
        if isinstance(route, dict):
            values.extend(string_list(route.get("project_id")))
    return list(dict.fromkeys(values))


def value_allowed(value: str, allowed: list[str]) -> bool:
    return not allowed or "*" in allowed or value in allowed


def task_not_disabled(task: dict[str, Any]) -> bool:
    metadata = dict_value(task.get("metadata"))
    value = task.get("use_subagents", metadata.get("use_subagents"))
    return value is not False


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def string(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
