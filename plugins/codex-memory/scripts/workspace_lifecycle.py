from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import workspace_router
import workspace_subagents
from workspace_path_utils import normalize_many


def safe_workspace_routing(task_id: str, task_payload: dict[str, Any]) -> dict[str, Any]:
    if routing_disabled():
        return {}
    try:
        task = {
            "task_id": task_id,
            "objective": string(task_payload.get("objective")),
            "working_set": string_list(task_payload.get("working_set")),
            "touched_paths": string_list(task_payload.get("touched_paths")),
            "cwd": string(task_payload.get("cwd")),
        }
        route_plan = workspace_router.build_route_plan(workspace_root(), task)
        return {
            "route_plan": route_plan,
            "bindings": create_bindings(route_plan),
        }
    except Exception as exc:
        return {
            "degraded": True,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def create_bindings(route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return workspace_subagents.create_bindings(route_plan)


def safe_scope_guard(
    bindings: Any,
    touched_paths: list[str],
    *,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    normalized_paths = normalize_many(touched_paths, project_root=project_root or workspace_root())
    if not normalized_paths or not isinstance(bindings, list):
        return []
    specialists = [
        item for item in bindings if isinstance(item, dict) and item.get("binding_mode") == "specialist"
    ]
    if len(specialists) == 1:
        return [workspace_subagents.check_scope(specialists[0], normalized_paths)]

    paths_by_binding: dict[int, list[str]] = {index: [] for index in range(len(specialists))}
    assigned_paths: set[str] = set()
    for path in normalized_paths:
        matches = [
            (index, scope_specificity(path, string_list(binding.get("assigned_scope"))))
            for index, binding in enumerate(specialists)
        ]
        matches = [(index, score) for index, score in matches if score >= 0]
        if not matches:
            continue
        best_score = max(score for _, score in matches)
        for index, score in matches:
            if score == best_score:
                paths_by_binding[index].append(path)
        assigned_paths.add(path)

    results: list[dict[str, Any]] = []
    for index, binding in enumerate(specialists):
        scoped_paths = paths_by_binding.get(index, [])
        if not scoped_paths:
            continue
        results.append(workspace_subagents.check_scope(binding, scoped_paths))

    unassigned = [path for path in normalized_paths if path not in assigned_paths]
    if unassigned:
        results.append(unassigned_scope_result(unassigned))
    return results


def merge_scope_guard_history(previous: Any, current: Any) -> list[dict[str, Any]]:
    results = [dict(item) for item in previous if isinstance(item, dict)] if isinstance(previous, list) else []
    for item in current if isinstance(current, list) else []:
        if not isinstance(item, dict):
            continue
        key = scope_guard_key(item)
        existing = next((result for result in results if scope_guard_key(result) == key), None)
        if existing is None:
            results.append(dict(item))
            continue
        for field in ("allowed_paths", "violations", "cross_project_dependencies"):
            existing[field] = merge_unique(existing.get(field), item.get(field))
        existing["ok"] = not existing.get("violations")
    return results


def scope_guard_key(result: dict[str, Any]) -> tuple[str, str, str]:
    return (
        string(result.get("binding_id")),
        string(result.get("subagent_id")),
        string(result.get("project_id")),
    )


def merge_unique(previous: Any, current: Any) -> list[Any]:
    merged: list[Any] = []
    for item in (previous if isinstance(previous, list) else []) + (current if isinstance(current, list) else []):
        if item not in merged:
            merged.append(item)
    return merged


def routing_review(task_state: dict[str, Any] | None) -> dict[str, Any]:
    metadata = task_state.get("metadata") if isinstance(task_state, dict) else {}
    routing = metadata.get("workspace_routing") if isinstance(metadata, dict) else {}
    if not isinstance(routing, dict) or not routing:
        return {"ok": True, "gaps": []}
    route_plan = routing.get("route_plan") if isinstance(routing.get("route_plan"), dict) else {}
    gaps: list[dict[str, Any]] = []
    if routing.get("degraded"):
        gaps.append(
            {
                "type": "workspace_routing",
                "blocking": False,
                "reason": string(routing.get("reason")) or "workspace routing degraded",
            }
        )
    adaptive_degraded = (
        routing.get("adaptive_degraded") if isinstance(routing.get("adaptive_degraded"), dict) else {}
    )
    if adaptive_degraded.get("degraded"):
        gaps.append(
            {
                "type": "workspace_routing",
                "blocking": False,
                "reason": string(adaptive_degraded.get("reason")) or "adaptive workspace routing degraded",
            }
        )
    if route_plan.get("mode") == "unknown_low_confidence":
        gaps.append({"type": "route_confidence", "blocking": False, "reason": "route plan confidence is low"})
    verification = routing.get("verification_aggregation") if isinstance(routing.get("verification_aggregation"), dict) else {}
    if route_plan.get("verification_plan") and not verification:
        gaps.append({"type": "verification", "blocking": False, "reason": "verification aggregation not recorded"})
    elif verification:
        status = string(verification.get("overall_status") or verification.get("status"))
        if status and status not in {"passed", "not_run"}:
            gaps.append(
                {
                    "type": "verification",
                    "blocking": True,
                    "reason": f"verification aggregation status is {status}",
                }
            )
    for result in routing.get("scope_guard") if isinstance(routing.get("scope_guard"), list) else []:
        if isinstance(result, dict) and result.get("violations"):
            gaps.append({"type": "scope_guard", "blocking": True, "reason": "touched paths exceed binding scope"})
    return {"ok": not any(item.get("blocking") for item in gaps), "gaps": gaps}


def unassigned_scope_result(paths: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "binding_id": "workspace-scope-guard",
        "subagent_id": "workspace",
        "project_id": None,
        "allowed_paths": [],
        "violations": [
            {"path": path, "reason": "not covered by any specialist assigned scope"}
            for path in paths
        ],
        "cross_project_dependencies": [
            {
                "from_binding": "workspace-scope-guard",
                "path": path,
                "reason": "not covered by any specialist assigned scope",
            }
            for path in paths
        ],
    }


def workspace_root() -> Path:
    return Path(os.environ.get("CODEX_MEMORY_CWD") or Path.cwd()).resolve()


def routing_disabled() -> bool:
    return os.environ.get("CODEX_WORKSPACE_ROUTING_DISABLE") == "1"


def path_in_any_scope(path: str, scopes: list[str]) -> bool:
    return scope_specificity(path, scopes) >= 0


def scope_specificity(path: str, scopes: list[str]) -> int:
    normalized_path = path.replace("\\", "/").strip("/")
    best_score = -1
    for scope in scopes:
        normalized_scope = scope.replace("\\", "/").strip("/")
        if normalized_scope in {"", "."}:
            best_score = max(best_score, 0)
            continue
        if normalized_path == normalized_scope or normalized_path.startswith(f"{normalized_scope}/"):
            best_score = max(best_score, normalized_scope.count("/") + 1)
    return best_score


def string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    return [str(value).strip()]
