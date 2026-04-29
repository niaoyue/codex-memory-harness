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
