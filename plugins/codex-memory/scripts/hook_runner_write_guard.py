from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hook_runner_utils import _string, _string_list
import workspace_session

SESSION_ID_KEYS = ("session_id", "sessionId", "conversation_id", "thread_id", "chat_id", "run_id")
TASK_ID_KEYS = ("task_id", "taskId", "codex_memory_task_id")
PROJECT_ROOT_KEYS = ("project_root", "cwd")
INTENDED_PATH_KEYS = ("intended_paths", "paths", "path")


def run_before_first_write(task_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    resolved_task_id = _first_string(payload, TASK_ID_KEYS) or _string(task_id)
    session_id = _first_string(payload, SESSION_ID_KEYS)
    route_plan, route_plan_source, route_error = _route_plan(payload)
    if route_error:
        return _blocked(resolved_task_id, session_id, "invalid_route_plan", {"field": route_error}, payload)
    requirements_gate, requirements_source, requirements_error = _requirements_gate(payload, route_plan)
    if requirements_error:
        return _blocked(
            resolved_task_id,
            session_id,
            "invalid_requirements_gate",
            {"field": requirements_error},
            payload,
        )

    missing = [field for field, value in (("task_id", resolved_task_id), ("session_id", session_id)) if not value]
    if missing:
        return _blocked(
            resolved_task_id,
            session_id,
            "missing_write_guard_identity",
            {"missing": missing},
            payload,
        )

    intended_paths = _first_string_list(payload, INTENDED_PATH_KEYS)
    project_root = _project_root(payload)
    guard = workspace_session.write_guard(
        project_root,
        session_id=session_id,
        task_id=resolved_task_id,
        intended_paths=intended_paths,
        route_plan=route_plan,
        requirements_gate=requirements_gate,
    )
    return _result(
        resolved_task_id,
        session_id,
        project_root,
        intended_paths,
        guard,
        route_plan_source,
        requirements_source,
    )


def _blocked(
    task_id: str,
    session_id: str,
    action: str,
    extra: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    guard = {"ok": False, "action": action, **extra}
    return _result(task_id, session_id, _project_root(payload), [], guard, "", "")


def _result(
    task_id: str,
    session_id: str,
    project_root: Path,
    intended_paths: list[str],
    guard: dict[str, Any],
    route_plan_source: str,
    requirements_gate_source: str,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "session_id": session_id,
        "project_root": str(project_root),
        "intended_paths": intended_paths,
        "route_plan_source": route_plan_source,
        "requirements_gate_source": requirements_gate_source,
        "write_allowed": bool(guard.get("ok") is True and guard.get("action") == "allow_write"),
        "write_guard": guard,
    }


def _route_plan(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str, str]:
    value, source, error = _dict_from(payload, "route_plan", "payload")
    if value is not None or error:
        return value, source, error
    signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
    value, source, error = _dict_from(signals, "route_plan", "signals")
    if value is not None or error:
        return value, source, error
    routing = payload.get("workspace_routing") if isinstance(payload.get("workspace_routing"), dict) else {}
    value, source, error = _dict_from(routing, "route_plan", "workspace_routing")
    return value, source, error


def _requirements_gate(
    payload: dict[str, Any],
    route_plan: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str, str]:
    value, source, error = _dict_from(payload, "requirements_gate", "payload")
    if value is not None or error:
        return value, source, error
    if isinstance(route_plan, dict):
        value, source, error = _dict_from(route_plan, "requirements_gate", "route_plan")
        if value is not None or error:
            return value, source, error
    signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
    return _dict_from(signals, "requirements_gate", "signals")


def _dict_from(source: dict[str, Any], key: str, label: str) -> tuple[dict[str, Any] | None, str, str]:
    if key not in source or source.get(key) is None:
        return None, "", ""
    value = source.get(key)
    if isinstance(value, dict):
        return value, label, ""
    return None, "", key


def _first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _string(payload.get(key))
        if value:
            return value
    return ""


def _first_string_list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    for key in keys:
        value = _string_list(payload.get(key))
        if value:
            return value
    return []


def _project_root(payload: dict[str, Any]) -> Path:
    for key in PROJECT_ROOT_KEYS:
        value = _string(payload.get(key))
        if value:
            return Path(value).expanduser()
    configured = _string(os.environ.get("CODEX_MEMORY_CWD"))
    return Path(configured).expanduser() if configured else Path.cwd()
