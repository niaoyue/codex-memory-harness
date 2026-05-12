from __future__ import annotations

from typing import Any

import requirements_gate_schema


def apply_requirements_write_enforcement(
    route_plan: dict[str, Any],
    bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enforcement = requirements_write_enforcement(route_plan)
    if not enforcement:
        return bindings
    return [binding_with_write_block(binding, enforcement) for binding in bindings]


def current_route_plan(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if isinstance(value.get("adaptive_route_plan"), dict):
        return value["adaptive_route_plan"]
    if isinstance(value.get("route_plan"), dict):
        return value["route_plan"]
    return value


def requirements_write_enforcement(route_plan: dict[str, Any]) -> dict[str, Any]:
    current_plan = current_route_plan(route_plan)
    requirements = (
        current_plan.get("requirements_gate") if isinstance(current_plan.get("requirements_gate"), dict) else {}
    )
    enforcement = requirements_gate_schema.write_enforcement(requirements)
    if enforcement or str(current_plan.get("fallback_action") or "") != "ask_user":
        return enforcement
    fallback_gate = dict(requirements)
    fallback_gate["blocking"] = True
    fallback_gate.setdefault("status", "needs_clarification")
    fallback_gate.setdefault(
        "open_questions",
        ["Route plan fallback_action=ask_user requires clarification before writes."],
    )
    fallback_gate.setdefault(
        "missing",
        [{"field": "requirements_gate", "reason": "fallback_action ask_user blocks writes"}],
    )
    return requirements_gate_schema.write_enforcement(fallback_gate)


def binding_with_write_block(binding: dict[str, Any], enforcement: dict[str, Any]) -> dict[str, Any]:
    blocked = dict(binding)
    permissions = dict(blocked.get("permissions")) if isinstance(blocked.get("permissions"), dict) else {}
    permissions["may_write"] = False
    permissions["write_blocked"] = True
    permissions["write_block_reason"] = str(enforcement.get("reason") or "requirements gate blocked write")
    blocked["permissions"] = permissions
    blocked["requirements_gate_enforcement"] = dict(enforcement)
    return blocked
