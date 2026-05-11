from __future__ import annotations

from typing import Any


SYSTEM_ARTIFACT_TOOL_NAMES = frozenset({"verification_runner", "workspace_verifier"})
SYSTEM_ARTIFACT_PHASES = frozenset({"verification", "workspace_verification"})


def is_subagent_artifact(artifact: dict[str, Any]) -> bool:
    if str(artifact.get("binding_id") or "").strip() or str(artifact.get("subagent_id") or "").strip():
        return True
    tool_name = str(artifact.get("tool_name") or artifact.get("tool") or "").strip()
    phase = str(artifact.get("phase") or "").strip()
    return tool_name not in SYSTEM_ARTIFACT_TOOL_NAMES and phase not in SYSTEM_ARTIFACT_PHASES


def routing_touched_paths(tool_name: str, payload: dict[str, Any], touched_paths: list[str]) -> list[str]:
    return [] if is_verification_artifact(tool_name, payload) else touched_paths


def routing_excluded_paths(tool_name: str, payload: dict[str, Any], touched_paths: list[str]) -> list[str]:
    return touched_paths if is_verification_artifact(tool_name, payload) else []


def has_bound_scope(payload: dict[str, Any]) -> bool:
    return bool(str(payload.get("binding_id") or "").strip() or str(payload.get("subagent_id") or "").strip())


def is_verification_artifact(tool_name: str, payload: dict[str, Any]) -> bool:
    signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
    payload_tool_name = str(payload.get("tool_name") or payload.get("tool") or tool_name or "").strip()
    phase = str(payload.get("phase") or "").strip()
    return (
        payload_tool_name in SYSTEM_ARTIFACT_TOOL_NAMES
        or phase in SYSTEM_ARTIFACT_PHASES
        or isinstance(signals.get("verification_aggregation"), dict)
    )
