from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sensitive_scan import sanitized_payload

HOOK_EVENTS = [
    "on_session_start",
    "before_task",
    "before_first_write",
    "after_tool",
    "before_response",
    "on_task_complete",
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    return [str(value).strip()]


def _merge_lists(base: list[str], extra: list[str]) -> list[str]:
    seen = set()
    merged: list[str] = []
    for item in [*base, *extra]:
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _merge_dicts(base: Any, extra: Any) -> dict[str, Any]:
    merged = base if isinstance(base, dict) else {}
    merged = dict(merged)
    if isinstance(extra, dict):
        merged.update(extra)
    return merged


def _select_scope_bindings(bindings: Any, payload: dict[str, Any]) -> Any:
    if not isinstance(bindings, list):
        return bindings
    specialists = [
        item for item in bindings if isinstance(item, dict) and item.get("binding_mode") == "specialist"
    ]
    for key in ("binding_id", "subagent_id"):
        value = _string(payload.get(key))
        if value:
            matched = [item for item in specialists if _string(item.get(key)) == value]
            if matched:
                return matched
    project_id = _string(payload.get("project_id"))
    if project_id:
        matched = [item for item in specialists if _string(item.get("project_id")) == project_id]
        if matched:
            return matched
    return bindings


def _default_task_id() -> str:
    return f"task-{_utc_stamp()}"


def _safe_task_id(value: str | None) -> str | None:
    if not value:
        return value
    try:
        return str(sanitized_payload(value, context="task_id")).strip() or "task"
    except Exception:
        return "task"


def _result_task_id(result: dict[str, Any], fallback: str | None) -> str | None:
    state = result.get("task_state") if isinstance(result.get("task_state"), dict) else {}
    context = result.get("context_pack") if isinstance(result.get("context_pack"), dict) else {}
    return _string(state.get("task_id")) or _string(context.get("task_id")) or _safe_task_id(fallback)


def _load_payload(payload_json: str | None, payload_file: str | None) -> dict[str, Any]:
    if payload_json:
        value = json.loads(payload_json)
        if not isinstance(value, dict):
            raise ValueError("payload_json must decode to an object.")
        return value

    if payload_file:
        value = json.loads(Path(payload_file).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("payload_file must contain a JSON object.")
        return value

    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("stdin payload must decode to an object.")
            return value

    return {}


def _build_fallback_context(task_id: str | None, reason: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "budget": {
            "total_chars": 0,
            "task_state_chars": 0,
            "summary_chars": 0,
            "decisions_chars": 0,
            "evidence_chars": 0,
            "used_chars": 0,
        },
        "sections": [
            {
                "name": "fallback",
                "title": "Fallback",
                "content": f"Hook degraded: {reason}",
                "chars_used": len(f"Hook degraded: {reason}"),
                "truncated": False,
            }
        ],
        "evidence_queries": [],
        "rendered_context": f"Hook degraded: {reason}",
    }
