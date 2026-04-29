from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import workspace_scanner
from workspace_routing_signals import (
    diagnostic_logging_policy,
    dict_value,
    fallback_profiles,
    git_changed_paths,
    has_release_signal,
    is_escaping_path,
    normalize_signal_path,
    path_in_scope,
    project_path_hits,
    project_diagnostic_policies,
    text_has_keyword,
)


DOMAIN_RULES = {
    "game_client": ["workspace/base", "game_client/base"],
    "game_server": ["workspace/base", "game_server/base"],
    "backoffice_web": ["workspace/base", "backoffice/base", "web/base"],
    "backoffice_service": ["workspace/base", "backoffice/base"],
    "design_docs": ["workspace/base", "docs/design"],
    "art_pipeline": ["workspace/base", "art_pipeline/base"],
    "build_release": ["workspace/base", "release/train"],
    "workspace_meta": ["workspace/base"],
    "unknown": ["workspace/generic"],
}
GAME_CLIENT_TASK_RULES = {
    "ui": "game_client/ui",
    "asset": "game_client/assets",
    "release": "release/high_risk",
    "contract": "game_client/network",
}
CONTRACT_WORDS = ("api", "proto", "protocol", "contract", "interface", "接口", "协议", "契约")
UI_WORDS = ("ui", "panel", "button", "view", "界面", "面板", "按钮")
PROFILE_PRIORITY = {
    "release": ("release", "release_gate", "publish", "build", "quick", "primary"),
    "contract": ("contract", "integration", "quick", "primary"),
    "ui": ("ui", "quick", "primary"),
    "asset": ("asset", "quick", "primary"),
    "docs": ("docs", "quick", "primary"),
    "implementation": ("quick", "primary"),
}


def build_route_plan(
    workspace_root: Path,
    task: dict[str, Any],
    *,
    changed: bool = False,
    max_depth: int = 2,
) -> dict[str, Any]:
    inventory = workspace_scanner.scan_workspace(workspace_root, max_depth=max_depth)
    config = workspace_scanner.load_workspace_config(workspace_root.resolve())
    projects = inventory_projects(inventory)
    signals = collect_signals(workspace_root, task, changed=changed)
    explicit_ids = explicit_project_ids(task)
    scored = score_projects(projects, signals, explicit_ids)

    if not scored:
        return unknown_plan(task, inventory, signals)

    affected = [project for project, score in scored if score > 0]
    if not affected:
        return unknown_plan(task, inventory, signals)

    mode = route_mode(affected, signals)
    task_type = infer_task_type(signals)
    risk = risk_level(mode, signals)
    confidence = min(0.96, max(score for _, score in scored) / 10)
    workspace_diagnostic = dict_value(config.get("diagnostic_logging"))
    project_diagnostics = project_diagnostic_policies(config)
    route_entries = [
        route_entry(
            project,
            projects,
            signals,
            task_type,
            workspace_diagnostic,
            project_diagnostics.get(str(project.get("id") or ""), {}),
        )
        for project in affected
    ]

    return {
        "version": 1,
        "task_id": str(task.get("task_id") or "workspace-route"),
        "route_plan_id": str(task.get("route_plan_id") or f"route-{task.get('task_id') or 'workspace-route'}"),
        "mode": mode,
        "primary_project": affected[0]["id"] if mode != "workspace_meta" else None,
        "affected_projects": [project["id"] for project in affected],
        "routes": route_entries,
        "task_type": task_type,
        "risk_level": risk,
        "coordinator_required": mode in {"cross_project_contract", "multi_project_parallel", "release_train"},
        "verification_profile_ids": flatten_profiles(route_entries),
        "contracts": contracts(mode, affected, signals),
        "confidence": round(confidence, 2),
        "reasons": reasons(affected, signals, explicit_ids),
        "verification_plan": verification_plan(route_entries),
        "memory_plan": memory_plan(affected, mode),
        "coordination": coordination(mode, affected),
        "fallback_action": "none",
    }


def inventory_projects(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    projects = inventory.get("projects") if isinstance(inventory.get("projects"), list) else []
    return [project for project in projects if isinstance(project, dict)]


def collect_signals(workspace_root: Path, task: dict[str, Any], *, changed: bool) -> dict[str, Any]:
    root = workspace_root.resolve()
    text_parts = [
        str(task.get("objective") or ""),
        str(task.get("user_request") or ""),
        str(task.get("summary") or ""),
    ]
    paths = string_list(task.get("working_set"))
    paths.extend(string_list(task.get("touched_paths")))
    paths.extend(string_list(task.get("paths")))
    if changed:
        paths.extend(git_changed_paths(workspace_root))
    normalized_paths = sorted(
        path for path in {normalize_signal_path(path, root) for path in paths if path}
        if path and not is_escaping_path(path)
    )
    cwd = normalize_signal_path(task.get("cwd") or "", root)
    if is_escaping_path(cwd):
        cwd = ""
    return {
        "text": " ".join(part for part in text_parts if part).lower(),
        "paths": [path for path in normalized_paths if path],
        "cwd": cwd,
    }


def explicit_project_ids(task: dict[str, Any]) -> list[str]:
    values = []
    for key in ("project_id", "primary_project", "primary_project_id"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    values.extend(string_list(task.get("project_ids")))
    values.extend(string_list(task.get("affected_projects")))
    return sorted(set(values))


def score_projects(
    projects: list[dict[str, Any]],
    signals: dict[str, Any],
    explicit_ids: list[str],
) -> list[tuple[dict[str, Any], int]]:
    scored: list[tuple[dict[str, Any], int]] = []
    for project in projects:
        score = 0
        project_id = str(project.get("id") or "")
        domain = str(project.get("domain") or "")
        cwd = str(project.get("cwd") or "").replace("\\", "/").strip("/")
        engine = str(project.get("engine") or "")
        if project_id in explicit_ids:
            score += 10
        if cwd == "." and signals["cwd"] == "." and not signals["paths"]:
            score += 5
        elif cwd and cwd != "." and signals["cwd"] and path_in_scope(signals["cwd"], cwd):
            score += 5
        path_hits = project_path_hits(project, projects, signals["paths"])
        score += min(len(path_hits) * 3, 9)
        text = signals["text"]
        if domain == "game_client" and any(word in text for word in ("client", "unity", "laya", "cocos", "客户端")):
            score += 2
        if engine and engine in text:
            score += 2
        if domain == "game_server" and any(word in text for word in ("server", "服务端", "服务器")):
            score += 2
        if domain.startswith("backoffice") and any(word in text for word in ("admin", "gm", "后台", "运营")):
            score += 2
        if domain == "design_docs" and any(word in text for word in ("docs", "design", "文档", "策划")):
            score += 2
        if domain == "art_pipeline" and any(word in text for word in ("asset", "art", "美术", "资源")):
            score += 2
        if score > 0:
            scored.append((project, score))
    return sorted(scored, key=lambda item: item[1], reverse=True)


def unknown_plan(task: dict[str, Any], inventory: dict[str, Any], signals: dict[str, Any]) -> dict[str, Any]:
    profiles = fallback_profiles(inventory)
    return {
        "version": 1,
        "task_id": str(task.get("task_id") or "workspace-route"),
        "mode": "unknown_low_confidence",
        "primary_project": None,
        "affected_projects": [],
        "routes": [],
        "task_type": infer_task_type(signals),
        "risk_level": risk_level("unknown_low_confidence", signals),
        "coordinator_required": False,
        "verification_profile_ids": profiles,
        "confidence": 0.2,
        "reasons": ["No explicit project, cwd, or changed path matched the project inventory."],
        "verification_plan": fallback_verification_plan(profiles),
        "fallback_action": "readonly_analysis",
    }


def route_mode(projects: list[dict[str, Any]], signals: dict[str, Any]) -> str:
    text = signals["text"]
    domains = {str(project.get("domain") or "") for project in projects}
    if has_release_signal(signals):
        return "release_train" if len(projects) > 1 else "single_project"
    if len(projects) == 1:
        return "single_project"
    if any(word in text for word in CONTRACT_WORDS) or {"game_client", "game_server"} <= domains:
        return "cross_project_contract"
    return "multi_project_parallel"


def infer_task_type(signals: dict[str, Any]) -> str:
    text = signals["text"]
    if has_release_signal(signals):
        return "release"
    if text_has_keyword(text, CONTRACT_WORDS):
        return "contract"
    if text_has_keyword(text, UI_WORDS):
        return "ui"
    if text_has_keyword(text, ("asset", "美术", "资源")):
        return "asset"
    if text_has_keyword(text, ("doc", "docs", "文档", "策划")):
        return "docs"
    return "implementation"


def risk_level(mode: str, signals: dict[str, Any]) -> str:
    if mode == "release_train" or has_release_signal(signals):
        return "release_blocking"
    if mode in {"cross_project_contract", "multi_project_parallel"}:
        return "high" if mode == "cross_project_contract" else "medium"
    return "medium"


def route_entry(
    project: dict[str, Any],
    all_projects: list[dict[str, Any]],
    signals: dict[str, Any],
    task_type: str,
    workspace_diagnostic: dict[str, Any] | None = None,
    project_diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_id = str(project.get("id"))
    cwd = str(project.get("cwd") or ".").replace("\\", "/").strip("/")
    domain = str(project.get("domain") or "unknown")
    matched_paths = project_path_hits(project, all_projects, signals["paths"])
    scope = matched_paths or ([cwd] if cwd else ["."])
    payload = {
        "route_id": f"{project_id}-{task_type}",
        "project_id": project_id,
        "domain": domain,
        "cwd": cwd,
        "engine": project.get("engine"),
        "task_type": task_type,
        "assigned_scope": scope,
        "rules": route_rules(project, task_type),
        "verification_profile_ids": profile_ids(project, task_type),
        "diagnostic_logging": diagnostic_logging_policy(workspace_diagnostic, project_diagnostic, task_type),
        "memory_binding": memory_binding(project),
        "confidence": 0.8,
        "reasons": route_reasons(project, matched_paths),
    }
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def route_rules(project: dict[str, Any], task_type: str) -> list[str]:
    domain = str(project.get("domain") or "unknown")
    result = string_list(project.get("rules")) or list(DOMAIN_RULES.get(domain, DOMAIN_RULES["unknown"]))
    engine = str(project.get("engine") or "").strip().lower()
    if domain == "game_client" and engine:
        result.append(f"game_client/{engine}")
        if task_type in GAME_CLIENT_TASK_RULES:
            result.append(GAME_CLIENT_TASK_RULES[task_type])
    return list(dict.fromkeys(result))


def profile_ids(project: dict[str, Any], task_type: str) -> list[str]:
    profiles = project.get("verification_profiles")
    if isinstance(profiles, dict):
        normalized = {
            str(key).lower(): str(value)
            for key, value in profiles.items()
            if str(key).strip() and str(value).strip()
        }
        for key in PROFILE_PRIORITY.get(task_type, PROFILE_PRIORITY["implementation"]):
            if key in normalized:
                return [normalized[key]]
        if normalized:
            return [normalized[sorted(normalized)[0]]]
    return ["primary"]


def memory_binding(project: dict[str, Any]) -> dict[str, Any]:
    binding = project.get("memory_binding")
    if isinstance(binding, dict) and binding:
        allowed = {"storage_scope", "semantic_scope", "project_id", "shared_memory_allowed"}
        runtime_binding = {key: binding[key] for key in allowed if key in binding}
        runtime_binding.setdefault("storage_scope", "project")
        runtime_binding.setdefault("semantic_scope", "project")
        runtime_binding.setdefault("project_id", str(project.get("id") or ""))
        return runtime_binding
    return {
        "storage_scope": "project",
        "semantic_scope": "project",
        "project_id": str(project.get("id") or ""),
        "shared_memory_allowed": True,
    }


def route_reasons(project: dict[str, Any], matched_paths: list[str]) -> list[str]:
    if matched_paths:
        return [f"matched path {path}" for path in matched_paths[:3]]
    return [f"matched project {project.get('id')} by text, cwd, or explicit project id"]


def flatten_profiles(routes: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for route in routes:
        values.extend(string_list(route.get("verification_profile_ids")))
    return sorted(set(values)) or ["primary"]


def verification_plan(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "project_id": str(route["project_id"]),
            "domain": str(route["domain"]),
            "cwd": str(route["cwd"]),
            "verification_profile_ids": string_list(route.get("verification_profile_ids")),
            "blocking": True,
        }
        for route in routes
    ]


def fallback_verification_plan(profile_ids: list[str]) -> list[dict[str, Any]]:
    if not profile_ids:
        return []
    return [{
        "project_id": "workspace", "domain": "workspace", "cwd": ".",
        "verification_profile_ids": profile_ids, "blocking": True,
    }]


def contracts(mode: str, projects: list[dict[str, Any]], signals: dict[str, Any]) -> list[dict[str, Any]]:
    if mode != "cross_project_contract":
        return []
    return [
        {
            "contract_id": "cross-project-contract",
            "owner": "coordinator",
            "affected_projects": [str(project.get("id")) for project in projects],
            "source_paths": signals["paths"],
            "summary": "Coordinator must lock the shared API/protocol/config contract before specialist edits.",
        }
    ]


def memory_plan(projects: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    return {
        "workspace_summary": {
            "storage_scope": "project",
            "semantic_scope": "workspace",
            "shared_memory_allowed": mode in {"cross_project_contract", "release_train"},
        },
        "project_summaries": [memory_binding(project) for project in projects],
    }


def coordination(mode: str, projects: list[dict[str, Any]]) -> dict[str, Any]:
    if mode not in {"cross_project_contract", "multi_project_parallel", "release_train"}:
        return {}
    payload = {
        "coordinator_role": coordinator_role(mode),
        "publish_order": [str(project.get("id")) for project in projects],
    }
    if mode == "cross_project_contract":
        payload["contract_owner"] = "coordinator"
    if mode == "release_train":
        payload["rollback_plan_required"] = True
    return payload


def coordinator_role(mode: str) -> str:
    if mode == "release_train":
        return "release coordinator"
    if mode == "cross_project_contract":
        return "contract coordinator"
    return "workspace coordinator"


def reasons(projects: list[dict[str, Any]], signals: dict[str, Any], explicit_ids: list[str]) -> list[str]:
    result: list[str] = []
    if explicit_ids:
        result.append(f"explicit project ids: {', '.join(explicit_ids)}")
    if signals["cwd"]:
        result.append(f"cwd signal: {signals['cwd']}")
    result.extend(f"path signal: {path}" for path in signals["paths"][:5])
    result.extend(f"selected project: {project.get('id')}" for project in projects)
    return result or ["selected by workspace inventory"]


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def load_task(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Task file root must be a JSON object.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only workspace route planner.")
    parser.add_argument("--workspace-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--task-file")
    parser.add_argument("--task-id")
    parser.add_argument("--objective")
    parser.add_argument("--working-set", action="append", default=[])
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--checkpoint", action="store_true")
    args = parser.parse_args()

    task = load_task(args.task_file)
    if args.task_id:
        task["task_id"] = args.task_id
    if args.objective:
        task["objective"] = args.objective
    if args.working_set:
        task["working_set"] = string_list(task.get("working_set")) + args.working_set

    route_plan = build_route_plan(
        Path(args.workspace_root),
        task,
        changed=args.changed,
        max_depth=max(args.max_depth, 0),
    )
    checkpoint_result = None
    if args.checkpoint and route_plan.get("task_id"):
        checkpoint_result = checkpoint_route_plan(Path(args.workspace_root), str(route_plan["task_id"]), route_plan)
    result = {"ok": True, "mode": "route", "route_plan": route_plan, "checkpoint": checkpoint_result}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def checkpoint_route_plan(project_root: Path, task_id: str, route_plan: dict[str, Any]) -> dict[str, Any]:
    from harness_controller import checkpoint_task

    payload = {
        "tool_name": "workspace_router",
        "phase": "routing",
        "summary": f"Workspace route plan generated: {route_plan['mode']}.",
        "touched_paths": [],
        "exit_code": 0,
        "signals": {
            "route_plan": route_plan,
        },
        "next_step": "按 route plan 加载规则、执行修改并运行验证。",
    }
    args = argparse.Namespace(
        project_root=str(project_root),
        task_id=task_id,
        result_file=None,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    return checkpoint_task(args)


if __name__ == "__main__":
    raise SystemExit(main())
