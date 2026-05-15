from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import required_dispatch_review
import subagent_runtime_planner
import subagent_task_classifier
import workspace_binding_enforcement
import workspace_router
import workspace_subagents
from workspace_path_utils import normalize_many


def safe_workspace_routing(task_id: str, task_payload: dict[str, Any]) -> dict[str, Any]:
    if routing_disabled():
        return {}
    try:
        metadata = task_payload.get("metadata") if isinstance(task_payload.get("metadata"), dict) else {}
        task = {
            "task_id": task_id,
            "objective": string(task_payload.get("objective")),
            "working_set": string_list(task_payload.get("working_set")),
            "touched_paths": string_list(task_payload.get("touched_paths")),
            "cwd": string(task_payload.get("cwd")),
            "metadata": metadata,
        }
        for field in requirement_task_fields():
            if field in task_payload:
                task[field] = task_payload[field]
            elif field in metadata:
                task[field] = metadata[field]
        route_plan = workspace_router.build_route_plan(workspace_root(), task)
        bindings = create_bindings(route_plan)
        runtime = subagent_runtime_decision(route_plan, bindings, task_payload)
        routing = {
            "route_plan": route_plan,
            "bindings": bindings,
            "subagent_runtime": runtime,
        }
        write_enforcement = requirements_write_enforcement(route_plan)
        if write_enforcement:
            routing["write_enforcement"] = write_enforcement
        attach_dispatch_plan_if_needed(routing, route_plan, bindings, task_payload)
        return routing
    except Exception as exc:
        return {
            "degraded": True,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def create_bindings(route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return workspace_subagents.create_bindings(route_plan)


def subagent_runtime_decision(
    route_plan: dict[str, Any],
    bindings: list[dict[str, Any]],
    task_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return subagent_runtime_planner.runtime_decision(route_plan, bindings, task_payload)


def requirements_gate_blocking(route_plan: dict[str, Any]) -> bool:
    return subagent_runtime_planner.requirements_gate_blocking(route_plan)


def requirements_write_enforcement(route_plan: dict[str, Any]) -> dict[str, Any]:
    return workspace_binding_enforcement.requirements_write_enforcement(route_plan)


def binding_with_write_block(binding: dict[str, Any], enforcement: dict[str, Any]) -> dict[str, Any]:
    return workspace_binding_enforcement.binding_with_write_block(binding, enforcement)


def main_agent_action(dispatch_allowed: bool, recommended: bool, requirements_blocked: bool = False) -> str:
    return subagent_runtime_planner.main_agent_action(dispatch_allowed, recommended, requirements_blocked)


def attach_dispatch_plan_if_needed(
    routing: dict[str, Any],
    route_plan: dict[str, Any],
    bindings: list[dict[str, Any]],
    task_payload: dict[str, Any] | None = None,
) -> None:
    runtime = routing.get("subagent_runtime") if isinstance(routing.get("subagent_runtime"), dict) else {}
    if not runtime.get("dispatch_plan_required"):
        return
    if runtime.get("trigger") == "xhigh_review_gate":
        if subagent_task_classifier.xhigh_review_dispatch_disabled(task_payload or {}):
            runtime["dispatch_plan_required"] = False
            runtime["dispatch_plan_available"] = False
            runtime["host_spawn_request_count"] = 0
            runtime["main_agent_action"] = "execute_on_main_agent"
            runtime["fallback_action"] = "main_agent_serial"
            runtime["reason"] = "XHigh review dispatch is disabled inside an active review gate."
            routing["subagent_runtime"] = runtime
            return
        import xhigh_review_dispatch

        dispatch_plan = xhigh_review_dispatch.build_dispatch_plan(route_plan)
        routing["subagent_dispatch_plan"] = dispatch_plan
        runtime["dispatch_plan_available"] = True
        runtime["host_spawn_request_count"] = len(dispatch_plan.get("host_spawn_requests") or [])
        routing["subagent_runtime"] = runtime
        return
    import subagent_scheduler

    dispatch_plan = subagent_scheduler.build_dispatch_plan(route_plan, bindings, runtime)
    if not dispatch_plan.get("host_spawn_requests"):
        bindings = fallback_dispatch_bindings(route_plan)
        routing["bindings"] = bindings
        dispatch_plan = subagent_scheduler.build_dispatch_plan(route_plan, bindings, runtime)
        runtime["planned_bindings"] = len(bindings)
        runtime["planned_specialists"] = len([item for item in bindings if item.get("binding_mode") == "specialist"])
    routing["subagent_dispatch_plan"] = dispatch_plan
    runtime["dispatch_plan_available"] = True
    runtime["host_spawn_request_count"] = len(dispatch_plan.get("host_spawn_requests") or [])
    routing["subagent_runtime"] = runtime


def fallback_dispatch_bindings(route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    synthetic = dict(route_plan)
    synthetic["routes"] = [
        {
            "route_id": "workspace-fallback",
            "project_id": "workspace",
            "domain": "workspace_meta",
            "cwd": ".",
            "task_type": string(route_plan.get("task_type") or "implementation"),
            "assigned_scope": ["."],
            "rules": ["workspace/generic"],
            "verification_profile_ids": string_list(route_plan.get("verification_profile_ids")) or ["primary"],
            "confidence": route_plan.get("confidence") or 0.2,
        }
    ]
    return workspace_subagents.create_bindings(synthetic)


def note_subagent_artifact(routing: dict[str, Any], artifact: dict[str, Any]) -> None:
    marker = string(artifact.get("subagent_id")) or string(artifact.get("binding_id"))
    if not marker:
        return
    runtime = routing.get("subagent_runtime") if isinstance(routing.get("subagent_runtime"), dict) else {}
    runtime = dict(runtime)
    artifact_ids = string_list(runtime.get("artifact_actor_ids"))
    if marker not in artifact_ids:
        artifact_ids.append(marker)
    runtime["status"] = "artifact_recorded"
    runtime["actual_subagents"] = len(artifact_ids)
    runtime["artifact_actor_ids"] = artifact_ids
    runtime["reason"] = "At least one SubAgent-style checkpoint or route-bound artifact was recorded."
    routing["subagent_runtime"] = runtime


def merge_adaptive_routing(
    workspace_routing: dict[str, Any],
    adaptive_routing: dict[str, Any],
) -> None:
    adaptive_runtime = (
        adaptive_routing.get("subagent_runtime")
        if isinstance(adaptive_routing.get("subagent_runtime"), dict)
        else {}
    )
    adaptive_has_route_plan = isinstance(adaptive_routing.get("route_plan"), dict)
    if adaptive_has_route_plan:
        workspace_routing["adaptive_route_plan"] = adaptive_routing["route_plan"]
    if isinstance(adaptive_routing.get("bindings"), list):
        workspace_routing["adaptive_bindings"] = adaptive_routing["bindings"]
    if isinstance(adaptive_routing.get("write_enforcement"), dict):
        enforcement = adaptive_routing["write_enforcement"]
        workspace_routing["write_enforcement"] = enforcement
        if isinstance(adaptive_routing.get("bindings"), list):
            workspace_routing["bindings"] = adaptive_routing["bindings"]
        elif isinstance(workspace_routing.get("bindings"), list):
            workspace_routing["bindings"] = [
                binding_with_write_block(binding, enforcement) for binding in workspace_routing["bindings"]
            ]
    elif adaptive_has_route_plan:
        workspace_routing.pop("write_enforcement", None)
        if isinstance(adaptive_routing.get("bindings"), list):
            workspace_routing["bindings"] = adaptive_routing["bindings"]
    if isinstance(adaptive_routing.get("subagent_dispatch_plan"), dict):
        workspace_routing["adaptive_subagent_dispatch_plan"] = adaptive_routing["subagent_dispatch_plan"]
        if adaptive_runtime.get("dispatch_plan_required") or "subagent_dispatch_plan" not in workspace_routing:
            workspace_routing["subagent_dispatch_plan"] = adaptive_routing["subagent_dispatch_plan"]
    if adaptive_runtime.get("trigger") == "review_gate_dispatch_disabled":
        workspace_routing.pop("subagent_dispatch_plan", None)
        workspace_routing.pop("adaptive_subagent_dispatch_plan", None)
    if isinstance(adaptive_routing.get("subagent_runtime"), dict):
        merge_subagent_runtime(workspace_routing, adaptive_routing["subagent_runtime"])
    if adaptive_routing.get("degraded"):
        workspace_routing["adaptive_degraded"] = adaptive_routing


def apply_signal_route_plan(
    workspace_routing: dict[str, Any],
    route_plan: dict[str, Any],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    bindings = create_bindings(route_plan)
    clear_adaptive_route_plan(workspace_routing)
    workspace_routing["route_plan"] = route_plan
    workspace_routing["bindings"] = bindings
    write_enforcement = requirements_write_enforcement(route_plan)
    if write_enforcement:
        workspace_routing["write_enforcement"] = write_enforcement
    else:
        workspace_routing.pop("write_enforcement", None)
    merge_subagent_runtime(workspace_routing, subagent_runtime_decision(route_plan, bindings, payload))
    attach_dispatch_plan_if_needed(workspace_routing, route_plan, bindings, payload)
    return bindings


def clear_adaptive_route_plan(workspace_routing: dict[str, Any]) -> None:
    for key in (
        "adaptive_route_plan",
        "adaptive_bindings",
        "adaptive_subagent_dispatch_plan",
        "adaptive_degraded",
    ):
        workspace_routing.pop(key, None)


def merge_subagent_runtime(workspace_routing: dict[str, Any], incoming_runtime: dict[str, Any]) -> None:
    current = workspace_routing.get("subagent_runtime") if isinstance(workspace_routing.get("subagent_runtime"), dict) else {}
    if current.get("status") == "artifact_recorded" or current.get("artifact_actor_ids"):
        merged = dict(incoming_runtime)
        merged.update(current)
        workspace_routing["subagent_runtime"] = merged
        return
    workspace_routing["subagent_runtime"] = incoming_runtime


def requirement_task_fields() -> tuple[str, ...]:
    return (
        "user_request",
        "summary",
        "task_intent",
        "intent",
        "requirements_gate_status",
        "requirements_status",
        "requirement_sources",
        "design_docs",
        "source_docs",
        "requirements",
        "acceptance",
        "acceptance_criteria",
        "architecture",
        "architecture_notes",
        "rollback_plan",
        "rollback",
        "assumptions",
        "logical_conflicts",
        "acceptance_gaps",
        "scope_gaps",
        "non_goals",
        "implementation_spec_mismatches",
        "safety_security_migration_rollback_gaps",
        "product_requirement_questions",
        "planning_questions",
        "technical_decision_basis",
        "technology_selection_basis",
        "test_plan_gaps",
        "missing_tests",
        "platform_constraint_gaps",
        "webgl_mini_game_gaps",
        "performance_package_constraints",
        "package_size_constraints",
        "asset_bundle_constraints",
        "ab_constraints",
    )


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
    requirements = route_plan.get("requirements_gate") if isinstance(route_plan.get("requirements_gate"), dict) else {}
    append_requirements_gap(gaps, requirements, "requirements_gate")
    adaptive_plan = routing.get("adaptive_route_plan") if isinstance(routing.get("adaptive_route_plan"), dict) else {}
    adaptive_requirements = (
        adaptive_plan.get("requirements_gate") if isinstance(adaptive_plan.get("requirements_gate"), dict) else {}
    )
    append_requirements_gap(gaps, adaptive_requirements, "adaptive_requirements_gate")
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
    runtime = routing.get("subagent_runtime") if isinstance(routing.get("subagent_runtime"), dict) else {}
    required_dispatch_review.append_gap(gaps, runtime)
    review = {"ok": not any(item.get("blocking") for item in gaps), "gaps": gaps}
    if runtime:
        review["subagent_runtime"] = runtime
    return review


def requirement_gap_reason(requirements: dict[str, Any]) -> str:
    questions = string_list(requirements.get("open_questions"))
    if questions:
        return questions[0]
    missing = requirements.get("missing") if isinstance(requirements.get("missing"), list) else []
    fields = [string(item.get("field")) for item in missing if isinstance(item, dict) and item.get("field")]
    if fields:
        return f"requirements gate missing: {', '.join(fields)}"
    return "requirements gate requires clarification"


def append_requirements_gap(gaps: list[dict[str, Any]], requirements: dict[str, Any], gap_type: str) -> None:
    if requirements.get("blocking"):
        gaps.append({"type": gap_type, "blocking": True, "reason": requirement_gap_reason(requirements)})


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
