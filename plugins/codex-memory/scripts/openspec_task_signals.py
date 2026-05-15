from __future__ import annotations

from typing import Any


CONTRACT_PATH_PREFIXES = (
    "openspec/changes/",
    "openspec/specs/",
)
CONTRACT_FILES = (
    "harness.json",
    "harness.md",
)


def contract_paths_from_signals(signals: dict[str, Any]) -> list[str]:
    return [path for path in string_list(signals.get("paths")) if is_contract_path(path)]


def contract_paths_from_task(task_payload: dict[str, Any], route_plan: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("working_set", "touched_paths", "paths"):
        paths.extend(string_list(task_payload.get(key)))
    for route in route_plan.get("routes") if isinstance(route_plan.get("routes"), list) else []:
        if isinstance(route, dict):
            paths.extend(string_list(route.get("assigned_scope")))
    return [path for path in paths if is_required_dispatch_path(path)]


def acceptance_evidence_from_signals(signals: dict[str, Any]) -> list[str]:
    paths = contract_paths_from_signals(signals)
    if not paths:
        return []
    result = [
        path
        for path in paths
        if path.lower().replace("\\", "/").endswith(("/tasks.md", "/proposal.md"))
        or "/specs/" in path.lower().replace("\\", "/")
    ]
    return result or ["openspec_change_contract"]


def architecture_evidence_from_signals(signals: dict[str, Any]) -> list[str]:
    paths = contract_paths_from_signals(signals)
    if not paths:
        return []
    result = [
        path
        for path in paths
        if path.lower().replace("\\", "/").endswith(("/design.md", "/harness.json", "/harness.md"))
    ]
    return result or ["openspec_change_contract"]


def is_contract_path(value: str) -> bool:
    path = normalize_path(value)
    if not path.startswith("openspec/") or path.startswith("openspec/upstream/"):
        return False
    return any(path.startswith(prefix) for prefix in CONTRACT_PATH_PREFIXES)


def is_required_dispatch_path(value: str) -> bool:
    path = normalize_path(value)
    if not path.startswith("openspec/") or path.startswith("openspec/upstream/"):
        return False
    if any(path.startswith(prefix) for prefix in CONTRACT_PATH_PREFIXES):
        return True
    return any(path.endswith(f"/{name}") for name in CONTRACT_FILES)


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip().lstrip("./").lower()


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
