from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import workspace_subagents
import subagent_runtime_planner
from harness_controller import checkpoint_task


def build_dispatch_plan(
    route_plan: dict[str, Any],
    bindings: list[dict[str, Any]],
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coordinator = next((item for item in bindings if item.get("binding_mode") == "coordinator"), None)
    coordinator_prepare_id = f"dispatch-{coordinator.get('binding_id')}-prepare" if coordinator else None
    specialist_items = [
        dispatch_item(binding, coordinator_prepare_id)
        for binding in bindings
        if binding.get("binding_mode") == "specialist"
    ]
    items = list(specialist_items)
    if coordinator:
        items.insert(0, coordinator_item(route_plan, coordinator, "prepare", []))
        items.append(coordinator_item(route_plan, coordinator, "summarize", [item["dispatch_id"] for item in specialist_items]))
    if runtime and runtime.get("review_subagent_required") and specialist_items:
        items.append(reviewer_item(route_plan, specialist_items))
    return {
        "version": 1,
        "task_id": str(route_plan.get("task_id") or "workspace-route"),
        "route_plan_id": str(route_plan.get("route_plan_id") or ""),
        "status": "ready",
        "execution_model": "host_subagent_or_manual",
        "autostart": False,
        "host_spawn_requests": [host_spawn_request(item) for item in items],
        "items": items,
        "completion_gate": {
            "requires_checkpoint": True,
            "requires_scope_guard": True,
            "requires_verification": bool(route_plan.get("verification_plan")),
        },
    }


def dispatch_item(binding: dict[str, Any], coordinator_prepare_id: str | None) -> dict[str, Any]:
    return {
        "dispatch_id": f"dispatch-{binding.get('binding_id')}",
        "binding_id": binding.get("binding_id"),
        "subagent_id": binding.get("subagent_id"),
        "role": binding.get("role"),
        "binding_mode": binding.get("binding_mode"),
        "project_id": binding.get("project_id"),
        "domain": binding.get("domain"),
        "cwd": binding.get("cwd"),
        "assigned_scope": binding.get("assigned_scope") or [],
        "rules": binding.get("rules") or [],
        "verification_profile_ids": binding.get("verification_profile_ids") or [],
        "status": "queued",
        "dependencies": [coordinator_prepare_id] if coordinator_prepare_id else [],
        "prompt": specialist_prompt(binding),
    }


def coordinator_item(route_plan: dict[str, Any], binding: dict[str, Any], phase: str, dependencies: list[str]) -> dict[str, Any]:
    return {
        "dispatch_id": f"dispatch-{binding.get('binding_id')}-{phase}",
        "binding_id": binding.get("binding_id"),
        "subagent_id": binding.get("subagent_id"),
        "role": binding.get("role"),
        "binding_mode": "coordinator",
        "phase": phase,
        "coordinates_projects": binding.get("coordinates_projects") or [],
        "status": "queued",
        "dependencies": dependencies,
        "prompt": coordinator_prompt(route_plan, phase),
    }


def reviewer_item(route_plan: dict[str, Any], specialist_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "dispatch_id": "dispatch-route-reviewer",
        "binding_id": "binding-route-reviewer",
        "subagent_id": "agent-route-reviewer",
        "role": "Route Review Specialist",
        "binding_mode": "reviewer",
        "status": "queued",
        "dependencies": [item["dispatch_id"] for item in specialist_items],
        "prompt": reviewer_prompt(route_plan),
    }


def host_spawn_request(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "dispatch_id": item.get("dispatch_id"),
        "binding_id": item.get("binding_id"),
        "subagent_id": item.get("subagent_id"),
        "role": item.get("role"),
        "agent_type": agent_type_for(item),
        "fork_context": True,
        "dependencies": item.get("dependencies") or [],
        "message": item.get("prompt") or "",
        "checkpoint_required": True,
        "scope_guard_required": item.get("binding_mode") == "specialist",
        "wait_policy": "progress_output_observation",
        "idle_policy": "progress_signal_observation_only",
        "total_timeout_policy": "none",
        "observation_window_policy": "poll_only_never_interrupt",
        "no_fixed_total_timeout": True,
    }


def agent_type_for(item: dict[str, Any]) -> str:
    if item.get("binding_mode") == "specialist":
        return "worker"
    return "default"


def specialist_prompt(binding: dict[str, Any]) -> str:
    return (
        f"Role: {binding.get('role')}\n"
        f"Project: {binding.get('project_id')} ({binding.get('domain')})\n"
        f"CWD: {binding.get('cwd')}\n"
        f"Scope: {', '.join(workspace_subagents.string_list(binding.get('assigned_scope')))}\n"
        "You are not alone in the codebase; do not revert edits made by others, and adapt to concurrent changes.\n"
        "No fixed total timeout applies. Host wait windows are observation polls only; do not interrupt solely because a wait window expires.\n"
        "Do not edit outside assigned_scope. Record a checkpoint with binding_id, subagent_id, project_id, "
        "domain, assigned_scope, touched_paths, verification_profile_ids, findings, and next_step."
    )


def coordinator_prompt(route_plan: dict[str, Any], phase: str) -> str:
    mode = route_plan.get("mode")
    if phase == "prepare":
        return (
            f"Prepare {mode} coordination: confirm contracts, dispatch order, release gates, and rollback needs. "
            "No fixed total timeout applies; host wait windows are observation polls only."
        )
    return (
        "Summarize specialist checkpoints, conflicts, scope guard results, verification gaps, publish order, and rollback needs. "
        "No fixed total timeout applies; host wait windows are observation polls only."
    )


def reviewer_prompt(route_plan: dict[str, Any]) -> str:
    factors = route_plan.get("task_type") or "implementation"
    return (
        f"Review route-bound implementation for task type {factors}. Focus on regressions, "
        "scope guard violations, missing tests, requirements gaps, and integration risks. "
        "No fixed total timeout applies; host wait windows are observation polls only. "
        "Do not edit files; report findings with file paths and blocking severity."
    )


def checkpoint_dispatch(project_root: Path, task_id: str, dispatch_plan: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "tool_name": "subagent_scheduler",
        "phase": "subagent_dispatch",
        "summary": f"Generated SubAgent dispatch plan with {len(dispatch_plan['items'])} item(s).",
        "touched_paths": [],
        "exit_code": 0,
        "signals": {"subagent_dispatch_plan": dispatch_plan},
        "next_step": "按 dispatch plan 启动宿主 SubAgent 或手工执行对应角色任务。",
    }
    args = argparse.Namespace(
        project_root=str(project_root),
        task_id=task_id,
        result_file=None,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    return checkpoint_task(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SubAgent dispatch plans from workspace routes.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--route-file")
    parser.add_argument("--task-file")
    parser.add_argument("--task-id")
    parser.add_argument("--objective")
    parser.add_argument("--working-set", action="append", default=[])
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--checkpoint", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    route_plan = workspace_subagents.load_or_build_route_plan(project_root, args)
    bindings = workspace_subagents.create_bindings(route_plan)
    runtime = subagent_runtime_planner.runtime_decision(route_plan, bindings, scheduler_task_payload(route_plan, args))
    dispatch_plan = build_dispatch_plan(route_plan, bindings, runtime)
    checkpoint = None
    if args.checkpoint:
        checkpoint = checkpoint_dispatch(project_root, str(route_plan["task_id"]), dispatch_plan)
    result = {
        "ok": True,
        "mode": "schedule",
        "route_plan": route_plan,
        "bindings": bindings,
        "subagent_runtime": runtime,
        "dispatch_plan": dispatch_plan,
        "checkpoint": checkpoint,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def scheduler_task_payload(route_plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_id": str(route_plan.get("task_id") or args.task_id or ""),
        "objective": str(args.objective or ""),
        "working_set": list(args.working_set or []),
    }
    requirements = route_plan.get("requirements_gate") if isinstance(route_plan.get("requirements_gate"), dict) else {}
    for key in ("task_intent", "requirement_sources", "acceptance", "acceptance_criteria"):
        value = requirements.get(key)
        if value not in (None, "", []):
            payload[key] = value
    for key in ("task_type", "risk_level"):
        value = route_plan.get(key)
        if value not in (None, "", []):
            payload[key] = value
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
