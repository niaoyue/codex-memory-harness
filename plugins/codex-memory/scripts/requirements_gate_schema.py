from __future__ import annotations

from typing import Any


GATE_SCHEMA_VERSION = 1
VALID_GATE_STATUSES = (
    "passed",
    "warning",
    "needs_clarification",
    "needs_bmad_upstream",
    "blocked_by_conflict",
)
BLOCKING_GATE_STATUSES = frozenset(
    {"needs_clarification", "needs_bmad_upstream", "blocked_by_conflict"}
)
BLOCKING_REQUIREMENT_INTENTS = frozenset({"feature_story", "system_change", "release_gate"})
ASSUMPTIONS_POLICY = "Do not infer missing product or design behavior. Ask for clarification before implementation."
TECHNICAL_DECISION_POLICY = (
    "Follow existing project conventions first. If none exist, choose a production-grade modular "
    "and interface-driven design, then record the decision."
)


def requested_status(task: dict[str, Any]) -> str:
    return _first_task_value(task, "requirements_gate_status", "requirements_status")


def normalize_status(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in VALID_GATE_STATUSES else ""


def resolve_status(
    *,
    intent: str,
    missing: list[dict[str, str]],
    requested: str,
    task: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    status = normalize_status(requested)
    if status in BLOCKING_GATE_STATUSES:
        return status, True
    if _has_conflict_evidence(task or {}):
        return "blocked_by_conflict", True

    missing_blocks = bool(missing) and intent in BLOCKING_REQUIREMENT_INTENTS
    if missing_blocks:
        return "needs_clarification", True
    if missing:
        return "warning", False
    if status == "warning":
        return "warning", False
    return "passed", False


def build_result(
    *,
    task: dict[str, Any],
    task_intent: str,
    status: str,
    blocking: bool,
    requirement_sources: list[str],
    missing: list[dict[str, str]],
    open_questions: list[str],
) -> dict[str, Any]:
    report = _report_fields(task, missing)
    return {
        "version": GATE_SCHEMA_VERSION,
        "task_intent": task_intent,
        "status": status,
        "blocking": blocking,
        "requirement_sources": list(requirement_sources),
        "missing": [dict(item) for item in missing],
        "open_questions": _status_questions(status, open_questions),
        "assumptions_policy": ASSUMPTIONS_POLICY,
        "technical_decision_policy": TECHNICAL_DECISION_POLICY,
        "assumptions": report["assumptions"],
        "missing_requirements": report["missing_requirements"],
        "logical_conflicts": report["logical_conflicts"],
        "acceptance_gaps": report["acceptance_gaps"],
        "scope_gaps": report["scope_gaps"],
        "non_goals": report["non_goals"],
        "implementation_spec_mismatches": report["implementation_spec_mismatches"],
        "safety_security_migration_rollback_gaps": report["safety_security_migration_rollback_gaps"],
        "recommended_next_step": recommended_next_step(status),
    }


def recommended_next_step(status: str) -> str:
    return {
        "passed": "Proceed with the bounded implementation under the selected change contract.",
        "warning": "Proceed only after acknowledging non-blocking requirement gaps.",
        "needs_clarification": "Ask the user to resolve missing requirements before implementation.",
        "needs_bmad_upstream": "Produce BMAD-style upstream planning artifacts before implementation.",
        "blocked_by_conflict": "Record and resolve requirement conflicts before implementation.",
    }.get(status, "Ask the user to clarify requirements before implementation.")


def _report_fields(task: dict[str, Any], missing: list[dict[str, str]]) -> dict[str, Any]:
    missing_reasons = _missing_reasons_by_field(missing)
    scope_gaps = _field_list(task, "scope_gaps")
    scope_gaps.extend(missing_reasons.get("requirement_sources", []))
    scope_gaps.extend(missing_reasons.get("architecture", []))
    rollback_gaps = _field_list(task, "safety_security_migration_rollback_gaps")
    rollback_gaps.extend(missing_reasons.get("rollback_plan", []))
    acceptance_gaps = _field_list(task, "acceptance_gaps")
    acceptance_gaps.extend(missing_reasons.get("acceptance_criteria", []))
    return {
        "assumptions": _field_list(task, "assumptions"),
        "missing_requirements": [dict(item) for item in missing],
        "logical_conflicts": _field_list(task, "logical_conflicts"),
        "acceptance_gaps": _unique(acceptance_gaps),
        "scope_gaps": _unique(scope_gaps),
        "non_goals": _field_list(task, "non_goals"),
        "implementation_spec_mismatches": _field_list(task, "implementation_spec_mismatches"),
        "safety_security_migration_rollback_gaps": _unique(rollback_gaps),
    }


def _has_conflict_evidence(task: dict[str, Any]) -> bool:
    return bool(
        _field_list(task, "logical_conflicts")
        or _field_list(task, "implementation_spec_mismatches")
    )


def _status_questions(status: str, questions: list[str]) -> list[str]:
    result = list(questions)
    if result:
        return _unique(result)
    if status == "needs_bmad_upstream":
        result.append("Which BMAD-style planning artifact is required before this can become one OpenSpec change?")
    elif status == "blocked_by_conflict":
        result.append("Which existing spec, doc, implementation behavior, or task list conflicts with the request?")
    elif status == "needs_clarification":
        result.append("Which missing requirement must be resolved before implementation?")
    return _unique(result)


def _missing_reasons_by_field(missing: list[dict[str, str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in missing:
        field = str(item.get("field") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if field and reason:
            result.setdefault(field, []).append(reason)
    return result


def _first_task_value(task: dict[str, Any], *keys: str) -> str:
    for key in keys:
        values = _field_list(task, key)
        if values:
            return values[0]
    return ""


def _field_list(task: dict[str, Any], key: str) -> list[str]:
    values = _string_list(task.get(key))
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    values.extend(_string_list(metadata.get(key)))
    return _unique(values)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
