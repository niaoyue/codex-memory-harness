from __future__ import annotations

from typing import Any


BLOCKER_TYPES = ("dependency", "decision", "environment", "interface", "verification")


def build_blocker_plan(route_plan: dict[str, Any], bindings: list[dict[str, Any]]) -> dict[str, Any]:
    specialists = [item for item in bindings if item.get("binding_mode") == "specialist"]
    slices = [task_slice(item) for item in specialists]
    blockers = explicit_blockers(route_plan)
    scope_matrix = build_scope_matrix(slices)
    if scope_matrix["overlaps"]:
        blockers.append(
            {
                "id": "scope-overlap",
                "type": "interface",
                "severity": "blocks_slice",
                "summary": "Specialist write scopes overlap; coordinator or serial ownership is required.",
                "affected_slice_ids": sorted({item["left"] for item in scope_matrix["overlaps"]} | {item["right"] for item in scope_matrix["overlaps"]}),
                "unblock_condition": "Split scopes or assign the shared path to one contract-owner slice.",
                "owner": "coordinator",
            }
        )
    status = plan_status(blockers, slices)
    return {
        "version": 1,
        "status": status,
        "blockers": blockers,
        "task_slices": slices,
        "scope_matrix": scope_matrix,
        "dispatch_recommendation": dispatch_recommendation(status, blockers),
    }


def can_parallelize(plan: dict[str, Any]) -> bool:
    if plan.get("status") == "blocked":
        return False
    if any(item.get("id") == "scope-overlap" for item in plan.get("blockers", [])):
        return False
    return not any(item.get("severity") == "blocks_all" for item in plan.get("blockers", []))


def task_slice(binding: dict[str, Any]) -> dict[str, Any]:
    slice_id = str(binding.get("binding_id") or binding.get("route_id") or binding.get("project_id") or "slice")
    return {
        "slice_id": slice_id,
        "title": str(binding.get("role") or slice_id),
        "project_id": str(binding.get("project_id") or ""),
        "domain": str(binding.get("domain") or ""),
        "cwd": str(binding.get("cwd") or "."),
        "assigned_scope": string_list(binding.get("assigned_scope")),
        "forbidden_paths": string_list((binding.get("permissions") or {}).get("forbidden_paths") if isinstance(binding.get("permissions"), dict) else binding.get("denied_scope")),
        "depends_on": [],
        "blocked_by": [],
        "interface_contracts": [],
        "verification_profile_ids": string_list(binding.get("verification_profile_ids")),
        "checkpoint_required": True,
        "scope_guard_required": True,
        "parallel_group": "default",
    }


def explicit_blockers(route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = []
    gate = route_plan.get("requirements_gate") if isinstance(route_plan.get("requirements_gate"), dict) else {}
    if gate.get("blocking"):
        blockers.append(
            {
                "id": "requirements-gate",
                "type": "decision",
                "severity": "blocks_all",
                "summary": str(gate.get("recommended_next_step") or "Requirements gate blocks implementation."),
                "affected_slice_ids": [],
                "unblock_condition": "Resolve blocking requirements gate questions.",
                "owner": "user",
            }
        )
    for item in route_plan.get("task_blockers") if isinstance(route_plan.get("task_blockers"), list) else []:
        if isinstance(item, dict):
            blockers.append(normalize_blocker(item))
    return blockers


def normalize_blocker(item: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("type") or "dependency")
    severity = str(item.get("severity") or "blocks_slice")
    return {
        "id": str(item.get("id") or kind),
        "type": kind if kind in BLOCKER_TYPES else "dependency",
        "severity": severity if severity in {"non_blocking", "blocks_slice", "blocks_all"} else "blocks_slice",
        "summary": str(item.get("summary") or ""),
        "affected_slice_ids": string_list(item.get("affected_slice_ids")),
        "unblock_condition": str(item.get("unblock_condition") or ""),
        "owner": str(item.get("owner") or "main_agent"),
    }


def build_scope_matrix(slices: list[dict[str, Any]]) -> dict[str, Any]:
    overlaps = []
    for index, left in enumerate(slices):
        for right in slices[index + 1:]:
            shared = overlapping_paths(left["assigned_scope"], right["assigned_scope"])
            if shared:
                overlaps.append({"left": left["slice_id"], "right": right["slice_id"], "paths": shared})
    return {
        "disjoint": not overlaps,
        "overlaps": overlaps,
        "shared_contract_paths": sorted({path for item in overlaps for path in item["paths"]}),
        "shared_readonly_paths": [],
        "merge_owner_slice_id": slices[0]["slice_id"] if overlaps and slices else None,
    }


def overlapping_paths(left: list[str], right: list[str]) -> list[str]:
    overlaps = []
    for left_path in left:
        for right_path in right:
            if paths_overlap(left_path, right_path):
                overlaps.append(shorter_scope(left_path, right_path))
    return sorted(set(overlaps))


def paths_overlap(left: str, right: str) -> bool:
    left_norm = normalize_path(left)
    right_norm = normalize_path(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == "." or right_norm == ".":
        return True
    return left_norm == right_norm or left_norm.startswith(f"{right_norm}/") or right_norm.startswith(f"{left_norm}/")


def shorter_scope(left: str, right: str) -> str:
    left_norm = normalize_path(left)
    right_norm = normalize_path(right)
    return left_norm if len(left_norm) <= len(right_norm) else right_norm


def normalize_path(value: str) -> str:
    return str(value or "").replace("\\", "/").strip("/") or "."


def plan_status(blockers: list[dict[str, Any]], slices: list[dict[str, Any]]) -> str:
    if any(item.get("severity") == "blocks_all" for item in blockers):
        return "blocked"
    if any(item.get("id") == "scope-overlap" for item in blockers):
        return "serial_required"
    if blockers:
        return "partially_blocked"
    return "parallelizable" if len(slices) > 1 else "serial_required"


def dispatch_recommendation(status: str, blockers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "host_dispatch_allowed": status in {"parallelizable", "partially_blocked"},
        "reason": "Parallel scopes are disjoint." if status == "parallelizable" else "Resolve blockers or run serially.",
        "blocking_ids": [str(item.get("id")) for item in blockers if item.get("severity") in {"blocks_all", "blocks_slice"}],
    }


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
