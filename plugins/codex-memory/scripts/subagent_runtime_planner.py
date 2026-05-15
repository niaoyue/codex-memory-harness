from __future__ import annotations

from typing import Any

import subagent_task_classifier


AUTONOMOUS_INTENTS = {"feature_story", "system_change", "release_gate"}
AUTONOMOUS_TASK_TYPES = {"implementation", "ui", "contract", "release"}
REVIEW_INTENTS = {"feature_story", "system_change", "release_gate"}


def runtime_decision(
    route_plan: dict[str, Any],
    bindings: list[dict[str, Any]],
    task_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = decision_context(route_plan, bindings, task_payload or {})
    hard_blocked = context["hard_disabled"] or context["requirements_blocked"]
    eligible = not (hard_blocked or context["user_disabled"])
    dispatch_required = not hard_blocked and context["dispatch_required_signal"]
    recommended = dispatch_required or (eligible and (
        context["explicit"]
        or context["review_gate"]
        or context["route_policy"]
        or context["route_recommended"]
        or context["complex_task"]
        or context["autonomous_task"]
    ))
    dispatch_allowed = dispatch_required or (eligible and (
        context["explicit"]
        or context["review_gate"]
        or context["route_policy"]
        or context["complex_task"]
        or context["autonomous_task"]
    ))
    status, trigger, reason = status_reason(context)
    roles = dispatch_roles(context, recommended, bindings)
    execution_model = "host_subagent_required" if dispatch_required else (
        "host_subagent_or_manual" if recommended else "main_agent_serial"
    )
    return {
        "version": 1,
        "status": status,
        "trigger": trigger,
        "execution_model": execution_model,
        "autostart": bool(dispatch_required or (recommended and context["policy_autostart"])),
        "recommended": recommended,
        "dispatch_required": dispatch_required,
        "required_dispatch_reason": required_dispatch_reason(context) if dispatch_required else "",
        "host_dispatch_allowed": dispatch_allowed,
        "host_dispatch_recommended": recommended,
        "requires_user_explicit_choice": recommended and not dispatch_allowed,
        "dispatch_plan_required": recommended,
        "dispatch_plan_source": "workspace_routing.subagent_dispatch_plan" if recommended else "",
        "main_agent_action": main_agent_action(
            dispatch_allowed,
            recommended,
            context["requirements_blocked"],
            dispatch_required,
        ),
        "fallback_action": fallback_action(context, recommended, dispatch_required),
        "planned_bindings": len(bindings),
        "planned_specialists": len(context["specialists"]),
        "actual_subagents": 0,
        "reason": reason,
        "policy": (
            "Route bindings and dispatch plans are planning metadata. For host_subagent_required, the "
            "main Agent must call host SubAgent tools before implementation or record a blocking downgrade."
        ),
        "recommended_role": "XHigh Review Runner" if context["review_gate"] else "",
        "timeout_policy": "progress_output_observation" if context["review_gate"] else "no_fixed_total_timeout" if recommended else "",
        "total_timeout_policy": "none" if recommended else "",
        "observation_window_policy": "poll_only_never_interrupt" if recommended else "",
        "decision_factors": decision_factors(context),
        "dispatch_roles": [str(item["kind"]) for item in roles],
        "role_plan": roles,
        "review_subagent_required": any(item.get("kind") == "route_reviewer" for item in roles),
    }


def decision_context(
    route_plan: dict[str, Any],
    bindings: list[dict[str, Any]],
    task_payload: dict[str, Any],
) -> dict[str, Any]:
    policy = runtime_policy(route_plan)
    policy_execution_model = string(policy.get("execution_model"))
    policy_disabled = policy.get("enabled") is False or policy_execution_model == "main_agent_serial"
    policy_required = policy_execution_model == "host_subagent_required"
    user_disabled = subagent_task_classifier.explicitly_disabled(task_payload)
    review_gate_dispatch_disabled = subagent_task_classifier.xhigh_review_dispatch_disabled(task_payload)
    specialists = [item for item in bindings if item.get("binding_mode") == "specialist"]
    requirements = route_plan.get("requirements_gate") if isinstance(route_plan.get("requirements_gate"), dict) else {}
    task_intent = string(requirements.get("task_intent"))
    task_type = string(route_plan.get("task_type") or "implementation")
    risk_level = string(route_plan.get("risk_level") or "medium")
    route_count = len(route_plan.get("routes") if isinstance(route_plan.get("routes"), list) else [])
    route_recommended = bool(route_plan.get("coordinator_required")) or route_plan.get("mode") in {
        "multi_project_parallel",
        "cross_project_contract",
        "release_train",
    } or len(specialists) > 1
    explicit = subagent_task_classifier.explicitly_requested(task_payload)
    review_gate = subagent_task_classifier.review_gate_recommended(task_payload)
    complex_task = subagent_task_classifier.complex_task_recommended(task_payload, route_plan)
    route_policy = not policy_disabled and subagent_task_classifier.route_policy_recommended(route_plan)
    openspec_required = subagent_task_classifier.openspec_subagent_required(task_payload, route_plan)
    context = {
        "route_plan": route_plan,
        "bindings": bindings,
        "task_payload": task_payload,
        "specialists": specialists,
        "disabled": user_disabled or policy_disabled or review_gate_dispatch_disabled,
        "user_disabled": user_disabled,
        "policy_disabled": policy_disabled,
        "hard_disabled": policy_disabled or review_gate_dispatch_disabled,
        "review_gate_dispatch_disabled": review_gate_dispatch_disabled,
        "policy_execution_model": policy_execution_model,
        "policy_autostart": bool(policy.get("autostart")),
        "policy_required": policy_required and not policy_disabled,
        "policy_reason": string(policy.get("reason")),
        "explicit": explicit,
        "review_gate": review_gate,
        "route_policy": route_policy,
        "route_policy_reason": subagent_task_classifier.route_policy_reason(route_plan),
        "openspec_required": openspec_required,
        "openspec_required_reason": subagent_task_classifier.openspec_required_reason(task_payload, route_plan) if openspec_required else "",
        "complex_task": complex_task,
        "requirements_blocked": requirements_gate_blocking(route_plan) and not review_gate,
        "route_recommended": route_recommended,
        "task_intent": task_intent,
        "task_type": task_type,
        "risk_level": risk_level,
        "route_count": route_count,
        "scope_size": subagent_task_classifier.scope_size(task_payload, route_plan),
    }
    context["complexity_level"] = complexity_level(context)
    context["autonomous_task"] = autonomous_task(context)
    context["reviewer_required"] = reviewer_required(context)
    context["dispatch_required_signal"] = context["openspec_required"] or context["policy_required"]
    return context


def autonomous_task(context: dict[str, Any]) -> bool:
    if context["task_type"] not in AUTONOMOUS_TASK_TYPES:
        return False
    if context["risk_level"] in {"high", "release_blocking"}:
        return True
    if context["task_intent"] in AUTONOMOUS_INTENTS:
        return True
    return context["complexity_level"] == "high"


def reviewer_required(context: dict[str, Any]) -> bool:
    if context["review_gate"]:
        return False
    return (
        context["task_intent"] in REVIEW_INTENTS
        or context["risk_level"] in {"high", "release_blocking"}
        or context["complexity_level"] == "high"
    )


def complexity_level(context: dict[str, Any]) -> str:
    if context["complex_task"] or context["risk_level"] in {"high", "release_blocking"}:
        return "high"
    if context["route_count"] > 1 and context["task_intent"] in AUTONOMOUS_INTENTS:
        return "high"
    if context["route_recommended"] or context["task_intent"] in AUTONOMOUS_INTENTS or context["scope_size"] >= 3:
        return "medium"
    return "low"


def status_reason(context: dict[str, Any]) -> tuple[str, str, str]:
    if context["review_gate_dispatch_disabled"]:
        return (
            "main_agent_serial",
            "review_gate_dispatch_disabled",
            "SubAgent dispatch is disabled inside an active review gate.",
        )
    if context["requirements_blocked"]:
        return (
            "requirements_blocked",
            "requirements_gate",
            "Requirements gate is blocking; collect clarification before dispatching implementation SubAgents.",
        )
    if context["policy_disabled"]:
        return (
            "main_agent_serial",
            "policy_disabled",
            context["policy_reason"] or "SubAgent runtime policy requires main Agent serial execution.",
        )
    if context["openspec_required"]:
        return (
            "dispatch_required_not_started",
            "openspec_required",
            context["openspec_required_reason"],
        )
    if context["policy_required"]:
        return (
            "dispatch_required_not_started",
            "route_policy_required",
            context["policy_reason"] or "Route policy requires host SubAgent dispatch.",
        )
    if context["user_disabled"]:
        return "main_agent_serial", "user_disabled", "User explicitly disabled SubAgent, delegation, or parallel agent work."
    if context["explicit"]:
        return (
            "requested_not_started",
            "user_explicit",
            "User explicitly requested SubAgent, delegation, role split, or parallel agent work.",
        )
    if context["review_gate"]:
        return (
            "recommended_not_started",
            "xhigh_review_gate",
            "XHigh review gate is long-running; use an XHigh Review Runner SubAgent when the host supports it.",
        )
    if context["route_policy"]:
        return "recommended_not_started", "route_policy", context["route_policy_reason"]
    if context["complex_task"]:
        return (
            "recommended_not_started",
            "complex_task",
            "Complex or app-sized task should be delegated to route-bound SubAgents to reduce main Agent context pressure.",
        )
    if context["autonomous_task"]:
        return (
            "recommended_not_started",
            "autonomous_task_analysis",
            "Task intent, task type, risk, and complexity indicate route-bound SubAgent execution is appropriate.",
        )
    if context["route_recommended"]:
        return (
            "recommended_not_started",
            "route_recommended",
            "Route plan has coordinator or multiple specialist bindings; lifecycle records the plan but does not autostart host SubAgents.",
        )
    return "main_agent_serial", "serial_default", "Single or tightly coupled route; main Agent execution is the default."


def dispatch_roles(context: dict[str, Any], recommended: bool, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not recommended:
        return []
    if context["review_gate"]:
        return [{"kind": "xhigh_review_runner", "role": "XHigh Review Runner", "agent_type": "XHigh Review Runner"}]
    roles: list[dict[str, Any]] = []
    if any(item.get("binding_mode") == "coordinator" for item in bindings):
        roles.append({"kind": "workspace_coordinator", "role": "Workspace Coordinator", "agent_type": "Workspace Coordinator"})
    roles.append({"kind": "route_specialist", "role": "Implementation Specialist", "agent_type": "Implementation Specialist"})
    if context["reviewer_required"]:
        roles.append({"kind": "route_reviewer", "role": "Route Review Specialist", "agent_type": "Route Review Specialist"})
    return roles


def decision_factors(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_intent": context["task_intent"],
        "task_type": context["task_type"],
        "risk_level": context["risk_level"],
        "complexity_level": context["complexity_level"],
        "route_count": context["route_count"],
        "specialist_count": len(context["specialists"]),
        "scope_size": context["scope_size"],
        "requirements_blocked": context["requirements_blocked"],
        "user_disabled": context["user_disabled"],
        "policy_disabled": context["policy_disabled"],
        "hard_disabled": context["hard_disabled"],
        "policy_required": context["policy_required"],
        "policy_autostart": context["policy_autostart"],
        "review_gate_dispatch_disabled": context["review_gate_dispatch_disabled"],
        "policy_execution_model": context["policy_execution_model"],
        "openspec_required": context["openspec_required"],
        "dispatch_required_signal": context["dispatch_required_signal"],
        "route_policy": context["route_policy"],
        "review_gate": context["review_gate"],
        "complex_task": context["complex_task"],
        "autonomous_task": context["autonomous_task"],
    }


def requirements_gate_blocking(route_plan: dict[str, Any]) -> bool:
    requirements = route_plan.get("requirements_gate")
    return bool(isinstance(requirements, dict) and requirements.get("blocking")) or string(route_plan.get("fallback_action")) == "ask_user"


def runtime_policy(route_plan: dict[str, Any]) -> dict[str, Any]:
    policy = route_plan.get("subagent_runtime_policy")
    return policy if isinstance(policy, dict) else {}


def main_agent_action(
    dispatch_allowed: bool,
    recommended: bool,
    requirements_blocked: bool = False,
    dispatch_required: bool = False,
) -> str:
    if requirements_blocked:
        return "ask_user_for_requirements"
    if dispatch_required:
        return "read_dispatch_plan_and_call_host_subagents"
    if dispatch_allowed:
        return "read_dispatch_plan_and_call_host_subagents"
    if recommended:
        return "record_dispatch_plan_for_host_or_manual_use"
    return "execute_on_main_agent"


def fallback_action(context: dict[str, Any], recommended: bool, dispatch_required: bool) -> str:
    if context["requirements_blocked"]:
        return "ask_user"
    if dispatch_required:
        return "report_blocking_downgrade"
    if recommended:
        return "main_agent_serial"
    return ""


def required_dispatch_reason(context: dict[str, Any]) -> str:
    if context["openspec_required"]:
        return context["openspec_required_reason"]
    if context["policy_required"]:
        return context["policy_reason"] or "Route policy requires host SubAgent dispatch."
    return ""


def string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
