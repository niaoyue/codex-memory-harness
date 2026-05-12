from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import workspace_binding_enforcement
import workspace_router
from workspace_artifact_security import sensitive_artifact_gaps
from workspace_artifact_filters import is_subagent_artifact
from workspace_path_utils import first_parent_match, normalize_many, normalize_path


def create_bindings(route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = [specialist_binding(route_plan, route) for route in routes(route_plan)]
    if route_plan.get("coordinator_required") or len(bindings) > 1:
        bindings.insert(0, coordinator_binding(route_plan, bindings))
    return workspace_binding_enforcement.apply_requirements_write_enforcement(route_plan, bindings)


def specialist_binding(route_plan: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    project_id = str(route.get("project_id") or "workspace")
    route_id = str(route.get("route_id") or project_id)
    return compact(
        {
            "version": 1,
            "task_id": str(route_plan.get("task_id") or "workspace-route"),
            "route_plan_id": str(route_plan.get("route_plan_id") or ""),
            "binding_id": f"binding-{route_id}",
            "subagent_id": f"agent-{route_id}",
            "role": role_for(route),
            "binding_mode": "specialist",
            "route_id": route_id,
            "project_id": project_id,
            "domain": str(route.get("domain") or "unknown"),
            "cwd": str(route.get("cwd") or "."),
            "assigned_scope": string_list(route.get("assigned_scope")) or [str(route.get("cwd") or ".")],
            "denied_scope": denied_scope(route_plan, project_id),
            "rules": string_list(route.get("rules")) or ["workspace/generic"],
            "verification_profile_ids": string_list(route.get("verification_profile_ids")) or ["primary"],
            "diagnostic_logging": diagnostic_logging(route.get("diagnostic_logging")),
            "memory_binding": route.get("memory_binding") or default_memory_binding(project_id),
            "artifact_policy": artifact_policy(),
            "permissions": {
                "may_write": True,
                "allowed_paths": string_list(route.get("assigned_scope")) or [str(route.get("cwd") or ".")],
                "forbidden_paths": denied_scope(route_plan, project_id),
            },
            "scope_guard": {
                "enabled": True,
                "on_violation": "report_cross_project_dependency",
            },
            "handoff_policy": {
                "cross_project_dependency_required": True,
                "coordinator_review_required": bool(route_plan.get("coordinator_required")),
            },
        }
    )


def coordinator_binding(route_plan: dict[str, Any], bindings: list[dict[str, Any]]) -> dict[str, Any]:
    project_ids = [str(item.get("project_id")) for item in bindings if item.get("project_id")]
    assigned = sorted({scope for item in bindings for scope in string_list(item.get("assigned_scope"))})
    profiles = sorted({profile for item in bindings for profile in string_list(item.get("verification_profile_ids"))})
    return compact(
        {
            "version": 1,
            "task_id": str(route_plan.get("task_id") or "workspace-route"),
            "route_plan_id": str(route_plan.get("route_plan_id") or ""),
            "binding_id": "binding-coordinator",
            "subagent_id": "agent-coordinator",
            "role": coordinator_role(route_plan),
            "binding_mode": "coordinator",
            "assigned_scope": assigned or ["."],
            "rules": ["workspace/base", "coordination/base"],
            "verification_profile_ids": profiles or ["primary"],
            "memory_binding": {
                "storage_scope": "project",
                "semantic_scope": "workspace",
                "write_summary": True,
                "shared_memory_allowed": route_plan.get("mode") in {"cross_project_contract", "release_train"},
            },
            "artifact_policy": artifact_policy(),
            "permissions": {
                "may_write": False,
                "allowed_paths": assigned or ["."],
                "forbidden_paths": [],
            },
            "coordinates_projects": project_ids,
            "scope_guard": {
                "enabled": True,
                "on_violation": "block",
            },
            "handoff_policy": {
                "cross_project_dependency_required": False,
                "coordinator_review_required": False,
            },
        }
    )


def check_scope(
    binding: dict[str, Any],
    touched_paths: list[str],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    assigned = normalize_many(string_list(binding.get("assigned_scope")) or ["."])
    denied = normalize_many(string_list(binding.get("denied_scope")))
    touched = normalize_many(touched_paths, project_root=project_root)
    violations: list[dict[str, str]] = []
    allowed: list[str] = []
    for path in touched:
        denied_hit = first_parent_match(path, denied)
        assigned_hit = first_parent_match(path, assigned)
        if denied_hit and (not assigned_hit or len(denied_hit.split("/")) >= len(assigned_hit.split("/"))):
            violations.append({"path": path, "reason": f"matches denied scope {denied_hit}"})
        elif assigned_hit:
            allowed.append(path)
        else:
            violations.append({"path": path, "reason": "outside assigned scope"})
    return {
        "ok": not violations,
        "binding_id": binding.get("binding_id"),
        "subagent_id": binding.get("subagent_id"),
        "project_id": binding.get("project_id"),
        "allowed_paths": allowed,
        "violations": violations,
        "cross_project_dependencies": [
            {
                "from_binding": binding.get("binding_id"),
                "path": item["path"],
                "reason": item["reason"],
            }
            for item in violations
        ],
    }


def coordinator_summary(
    bindings: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    verification_aggregation: dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    artifact_items = [item for item in artifacts if isinstance(item, dict)]
    subagent_artifacts = [item for item in artifact_items if is_subagent_artifact(item)]
    specialist_bindings = [item for item in bindings if item.get("binding_mode") == "specialist"]
    scope_results = [
        check_scope(binding, artifact_touched_paths(binding, subagent_artifacts), project_root=project_root)
        for binding in specialist_bindings
    ]
    conflicts = conflict_report(subagent_artifacts, project_root=project_root)
    artifact_gaps = unmatched_artifact_gaps(specialist_bindings, subagent_artifacts, project_root=project_root)
    artifact_gaps.extend(sensitive_artifact_gaps(specialist_bindings, subagent_artifacts))
    artifact_gaps.extend(missing_checkpoint_gaps(specialist_bindings, subagent_artifacts))
    verification_gaps = []
    verification_warnings = []
    if verification_aggregation:
        for item in verification_aggregation.get("gaps") or []:
            if isinstance(item, dict) and item.get("blocking"):
                verification_gaps.append(item)
            elif isinstance(item, dict):
                verification_warnings.append(item)
        verification_gaps.extend(verification_blockers(verification_aggregation))
    scope_violations = any(item["violations"] for item in scope_results)
    return {
        "ok": not conflicts and not scope_violations and not artifact_gaps and not verification_gaps,
        "projects": sorted({str(item.get("project_id")) for item in bindings if item.get("project_id")}),
        "scope_guard": scope_results,
        "conflicts": conflicts,
        "artifact_gaps": artifact_gaps,
        "verification_gaps": verification_gaps,
        "verification_warnings": verification_warnings,
        "publish_order": publish_order(bindings),
        "rollback_required": bool(conflicts or artifact_gaps or verification_gaps or scope_violations),
    }


def verification_blockers(aggregation: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    status = str(aggregation.get("overall_status") or aggregation.get("status") or "")
    if status and status not in {"passed", "not_run"}:
        blockers.append({"reason": f"verification aggregation status is {status}", "blocking": True})
    for result in aggregation.get("results") if isinstance(aggregation.get("results"), list) else []:
        if isinstance(result, dict) and result.get("status") == "failed" and result.get("blocking"):
            blockers.append(
                {
                    "project_id": result.get("project_id"),
                    "profile_id": result.get("profile_id"),
                    "reason": f"blocking command failed: {result.get('command_id') or result.get('command')}",
                    "blocking": True,
                }
            )
    gates = aggregation.get("release_gates") if isinstance(aggregation.get("release_gates"), dict) else {}
    for gate_id, gate in gates.items():
        if isinstance(gate, dict) and gate.get("blocking") and gate.get("status") != "passed":
            blockers.append({"reason": f"release gate blocked: {gate_id}", "blocking": True})
    return blockers


def conflict_report(artifacts: list[dict[str, Any]], *, project_root: Path | None = None) -> list[dict[str, Any]]:
    owners: dict[str, list[str]] = {}
    for artifact in artifacts:
        owner = str(artifact.get("binding_id") or artifact.get("subagent_id") or artifact.get("project_id") or "unknown")
        for path in normalize_many(string_list(artifact.get("touched_paths")), project_root=project_root):
            owners.setdefault(path, []).append(owner)
    return [
        {"path": path, "owners": sorted(set(items)), "reason": "multiple bindings touched same path"}
        for path, items in sorted(owners.items())
        if len(set(items)) > 1
    ]


def artifact_touched_paths(binding: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for artifact in artifacts:
        if artifact_matches_binding(binding, artifact):
            paths.extend(string_list(artifact.get("touched_paths")))
    return paths


def unmatched_artifact_gaps(
    bindings: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    *,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for artifact in artifacts:
        touched = normalize_many(string_list(artifact.get("touched_paths")), project_root=project_root)
        if not touched:
            continue
        if any(artifact_matches_binding(binding, artifact) for binding in bindings):
            continue
        gaps.append(
            {
                "type": "artifact_attribution",
                "blocking": True,
                "reason": "artifact with touched_paths did not match any specialist binding",
                "touched_paths": touched,
            }
        )
    return gaps


def missing_checkpoint_gaps(bindings: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for binding in bindings:
        policy = binding.get("artifact_policy") if isinstance(binding.get("artifact_policy"), dict) else {}
        if not policy.get("checkpoint_required"):
            continue
        required = string_list(policy.get("required_fields"))
        if any(
            artifact_matches_binding(binding, artifact) and has_required_artifact_fields(artifact, required)
            for artifact in artifacts
        ):
            continue
        gaps.append({"type": "missing_checkpoint", "binding_id": binding.get("binding_id"),
                     "subagent_id": binding.get("subagent_id"), "project_id": binding.get("project_id"),
                     "blocking": True, "reason": "specialist binding requires a complete checkpoint artifact"})
    return gaps


def has_required_artifact_fields(artifact: dict[str, Any], required: list[str]) -> bool:
    return all(string_list(artifact.get(field)) if field in {"assigned_scope", "touched_paths"}
               else str(artifact.get(field) or "").strip() for field in required)


def artifact_matches_binding(binding: dict[str, Any], artifact: dict[str, Any]) -> bool:
    binding_ids = {str(binding.get("binding_id") or ""), str(binding.get("subagent_id") or "")} - {""}
    artifact_ids = {str(artifact.get("binding_id") or ""), str(artifact.get("subagent_id") or "")} - {""}
    if artifact_ids:
        return bool(binding_ids & artifact_ids)
    project_id = str(binding.get("project_id") or "")
    artifact_project_id = str(artifact.get("project_id") or "")
    return bool(project_id and artifact_project_id and project_id == artifact_project_id)


def denied_scope(route_plan: dict[str, Any], project_id: str) -> list[str]:
    denied: list[str] = []
    for route in routes(route_plan):
        if route.get("project_id") != project_id:
            scopes = string_list(route.get("assigned_scope")) or string_list(route.get("cwd"))
            denied.extend(scope for scope in scopes if normalize_path(scope) != ".")
    return sorted(set(denied))


def routes(route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    value = route_plan.get("routes") if isinstance(route_plan.get("routes"), list) else []
    return [item for item in value if isinstance(item, dict)]


def role_for(route: dict[str, Any]) -> str:
    domain = str(route.get("domain") or "unknown")
    task_type = str(route.get("task_type") or "implementation")
    return f"{domain.replace('_', ' ').title()} {task_type.title()} Specialist"


def coordinator_role(route_plan: dict[str, Any]) -> str:
    if route_plan.get("mode") == "release_train":
        return "Release Coordinator"
    if route_plan.get("mode") == "cross_project_contract":
        return "Contract Coordinator"
    return "Workspace Coordinator"


def diagnostic_logging(value: Any) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, dict) else {}
    return {
        "allowed": bool(payload.get("allowed", False)),
        "required_scopes": string_list(payload.get("required_scopes")),
        "release_must_be_disabled": bool(payload.get("release_must_be_disabled", True)),
    }


def artifact_policy() -> dict[str, Any]:
    return {
        "required_fields": ["binding_id", "subagent_id", "project_id", "domain", "assigned_scope", "touched_paths"],
        "forbid_raw_sensitive_output": True,
        "checkpoint_required": True,
    }


def default_memory_binding(project_id: str) -> dict[str, Any]:
    return {
        "storage_scope": "project",
        "semantic_scope": "project",
        "project_id": project_id,
        "write_summary": True,
        "shared_memory_allowed": True,
    }


def publish_order(bindings: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("project_id"))
        for item in bindings
        if item.get("binding_mode") == "specialist" and item.get("project_id")
    ]


def compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("bindings"), list):
        return value
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object.")
    return value


def read_json_list(paths: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            for line in text.splitlines():
                if not line.strip():
                    continue
                line_value = json.loads(line)
                if isinstance(line_value, dict):
                    items.append(line_value)
            continue
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            items.append(value)
    return items


def checkpoint_bindings(project_root: Path, task_id: str, bindings: list[dict[str, Any]]) -> dict[str, Any]:
    from harness_controller import checkpoint_task

    payload = {
        "tool_name": "workspace_subagents",
        "phase": "subagent_binding",
        "summary": f"Generated {len(bindings)} SubAgent route binding(s).",
        "touched_paths": [],
        "exit_code": 0,
        "signals": {"subagent_route_bindings": bindings},
        "next_step": "将 binding 注入对应 SubAgent 上下文，并在 checkpoint 中执行 scope guard。",
    }
    args = argparse.Namespace(
        project_root=str(project_root),
        task_id=task_id,
        result_file=None,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    return checkpoint_task(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="SubAgent route binding and scope guard utilities.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    bind = subparsers.add_parser("bind")
    bind.add_argument("--route-file")
    bind.add_argument("--task-file")
    bind.add_argument("--task-id")
    bind.add_argument("--objective")
    bind.add_argument("--working-set", action="append", default=[])
    bind.add_argument("--changed", action="store_true")
    bind.add_argument("--checkpoint", action="store_true")

    check = subparsers.add_parser("scope-check")
    check.add_argument("--binding-file", required=True)
    check.add_argument("--touched-path", action="append", default=[])
    check.add_argument("--artifact-file", action="append", default=[])

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--bindings-file", required=True)
    summarize.add_argument("--artifact-file", action="append", default=[])
    summarize.add_argument("--verification-file")

    args = parser.parse_args()
    result = dispatch(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    if args.command == "bind":
        route_plan = load_or_build_route_plan(project_root, args)
        bindings = create_bindings(route_plan)
        checkpoint = None
        if args.checkpoint:
            checkpoint = checkpoint_bindings(project_root, str(route_plan["task_id"]), bindings)
        return {"ok": True, "mode": "bind", "route_plan": route_plan, "bindings": bindings, "checkpoint": checkpoint}
    if args.command == "scope-check":
        binding = read_json(args.binding_file)
        validate_single_binding(binding)
        touched = string_list(args.touched_path)
        for artifact in read_json_list(args.artifact_file):
            touched.extend(string_list(artifact.get("touched_paths")))
        result = check_scope(binding, touched, project_root=project_root)
        return {"ok": result["ok"], "mode": "scope-check", "scope_guard": result}
    if args.command == "summarize":
        payload = read_json(args.bindings_file)
        bindings = payload.get("bindings") if isinstance(payload.get("bindings"), list) else []
        verification = read_json(args.verification_file) if args.verification_file else None
        if verification and isinstance(verification.get("verification_aggregation"), dict):
            verification = verification["verification_aggregation"]
        summary = coordinator_summary(bindings, read_json_list(args.artifact_file), verification, project_root=project_root)
        return {"ok": summary["ok"], "mode": "summarize", "coordinator_summary": summary}
    raise ValueError(f"Unsupported command: {args.command}")


def validate_single_binding(binding: dict[str, Any]) -> None:
    if isinstance(binding.get("bindings"), list):
        raise ValueError("scope-check requires a single binding JSON, not the full bind output.")
    if isinstance(binding.get("routes"), list):
        raise ValueError("scope-check requires a single binding JSON, not a route plan.")
    required = ["binding_id", "subagent_id", "assigned_scope"]
    missing = [field for field in required if not binding.get(field)]
    if missing:
        raise ValueError(f"scope-check binding is missing required field(s): {', '.join(missing)}")
    if not string_list(binding.get("assigned_scope")):
        raise ValueError("scope-check binding must include at least one assigned scope.")


def load_or_build_route_plan(project_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    route_plan = read_json(args.route_file)
    if route_plan:
        return workspace_binding_enforcement.current_route_plan(route_plan)
    task = workspace_router.load_task(args.task_file)
    if args.task_id:
        task["task_id"] = args.task_id
    if args.objective:
        task["objective"] = args.objective
    if args.working_set:
        task["working_set"] = workspace_router.string_list(task.get("working_set")) + args.working_set
    return workspace_router.build_route_plan(project_root, task, changed=args.changed)


if __name__ == "__main__":
    raise SystemExit(main())
