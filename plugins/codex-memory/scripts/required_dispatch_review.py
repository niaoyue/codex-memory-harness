from __future__ import annotations

from typing import Any


def append_gap(gaps: list[dict[str, Any]], runtime: dict[str, Any]) -> None:
    if not runtime.get("dispatch_required"):
        return
    if int_value(runtime.get("actual_subagents")) > 0 or string(runtime.get("downgrade_reason")):
        return
    gaps.append(
        {
            "type": "required_subagent_dispatch",
            "blocking": True,
            "reason": "required SubAgent dispatch has no recorded artifact or downgrade_reason",
            "execution_model": string(runtime.get("execution_model")),
            "status": string(runtime.get("status")),
            "host_spawn_request_count": int_value(runtime.get("host_spawn_request_count")),
        }
    )


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
