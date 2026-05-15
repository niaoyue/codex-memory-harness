from __future__ import annotations

from typing import Any


def append_gap(gaps: list[dict[str, Any]], runtime: dict[str, Any], dispatch_plan: dict[str, Any]) -> None:
    if not runtime.get("dispatch_required"):
        return
    if string(runtime.get("downgrade_reason")):
        return
    missing = missing_dispatch_requests(runtime, dispatch_plan)
    if not missing:
        return
    gaps.append(
        {
            "type": "required_subagent_dispatch",
            "blocking": True,
            "reason": "required SubAgent dispatch has missing artifacts and no downgrade_reason",
            "execution_model": string(runtime.get("execution_model")),
            "status": string(runtime.get("status")),
            "host_spawn_request_count": int_value(runtime.get("host_spawn_request_count")),
            "missing_dispatch_requests": missing,
        }
    )


def missing_dispatch_requests(runtime: dict[str, Any], dispatch_plan: dict[str, Any]) -> list[str]:
    requests = dispatch_plan.get("host_spawn_requests") if isinstance(dispatch_plan.get("host_spawn_requests"), list) else []
    dispatch_ids = set(string_list(runtime.get("artifact_dispatch_ids")))
    if requests:
        missing = []
        for request in requests:
            if not isinstance(request, dict):
                continue
            dispatch_id = string(request.get("dispatch_id"))
            if not dispatch_id or dispatch_id not in dispatch_ids:
                missing.append(dispatch_id or "unknown")
        return missing
    actual = int_value(runtime.get("actual_subagents"))
    expected = int_value(runtime.get("host_spawn_request_count"))
    if expected <= 0:
        return [] if actual > 0 else ["unknown"]
    return [] if actual >= expected else ["unknown"]


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
