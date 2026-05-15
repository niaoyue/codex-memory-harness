from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from task_spec import TaskSpec, safe_id


DISABLE_ENV = "CODEX_MEMORY_DISABLE_OPENSPEC_CHANGE"
UPSTREAM_MANIFEST = Path("openspec") / "upstream" / "openspec" / "manifest.json"
IMPLEMENTATION_HINTS = (
    "implement",
    "fix",
    "repair",
    "update",
    "change",
    "refactor",
    "migrate",
    "deploy",
    "实现",
    "修复",
    "处理",
    "改",
    "迁移",
    "部署",
    "落地",
)
READ_ONLY_HINTS = (
    "read-only",
    "readonly",
    "analysis",
    "analyze",
    "review",
    "diagnose",
    "只读",
    "分析",
    "查看",
    "检查",
    "排查",
    "为什么",
    "原因",
)


def ensure_for_task(project_root: Path, spec: TaskSpec) -> dict[str, Any]:
    metadata = spec.metadata if isinstance(spec.metadata, dict) else {}
    if _disabled(metadata):
        return _skipped("disabled")
    if not (project_root / UPSTREAM_MANIFEST).exists():
        return _skipped("openspec_upstream_missing")
    existing_change_id = _existing_change_id(metadata, spec.working_set)
    change_id = existing_change_id or safe_id(
        str(metadata.get("openspec_change_id") or metadata.get("openspec_change") or spec.task_id)
    )
    if not change_id:
        change_id = safe_id(spec.objective)
    if not existing_change_id and _read_only_task(spec, metadata):
        return _skipped("read_only_task")

    capability = safe_id(str(metadata.get("openspec_capability") or change_id))
    change_dir = project_root / "openspec" / "changes" / change_id
    paths = _change_paths(change_id, capability)
    created = []
    created.extend(_write_if_missing(change_dir / "proposal.md", _proposal_markdown(spec), paths["proposal"]))
    created.extend(_write_if_missing(change_dir / "design.md", _design_markdown(spec), paths["design"]))
    created.extend(_write_if_missing(change_dir / "tasks.md", _tasks_markdown(spec), paths["tasks"]))
    created.extend(
        _write_if_missing(
            change_dir / "specs" / capability / "spec.md",
            _spec_markdown(spec, capability),
            paths["spec"],
        )
    )
    created.extend(
        _write_json_if_missing(
            change_dir / "harness.json",
            _harness_payload(spec, change_id, paths),
            paths["harness"],
        )
    )
    status = "updated" if created and existing_change_id else "created" if created else "existing"
    return {
        "status": status,
        "change_id": change_id,
        "capability": capability,
        "change_dir": paths["change_dir"],
        "working_set": [
            paths["proposal"],
            paths["design"],
            paths["tasks"],
            paths["spec"],
            paths["harness"],
        ],
        "created_files": created,
    }


def apply_to_spec(spec: TaskSpec, result: dict[str, Any]) -> None:
    if result.get("status") not in {"created", "updated", "existing"}:
        spec.metadata["openspec_change"] = result
        return
    spec.metadata["openspec_change"] = result
    spec.metadata["openspec_change_id"] = result["change_id"]
    spec.metadata["openspec_capability"] = result["capability"]
    spec.metadata["openspec_dispatch_required"] = True
    spec.working_set = _merge_lists(spec.working_set, result.get("working_set"))


def _disabled(metadata: dict[str, Any]) -> bool:
    if os.environ.get(DISABLE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    value = metadata.get("openspec_auto_change")
    return value is False or str(value).strip().lower() in {"0", "false", "no", "off"}


def _existing_change_id(metadata: dict[str, Any], working_set: list[str]) -> str:
    for key in ("openspec_change_id", "openspec_change"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return safe_id(value)
    for item in working_set:
        normalized = str(item).replace("\\", "/")
        marker = "openspec/changes/"
        if marker in normalized:
            suffix = normalized.split(marker, 1)[1]
            return safe_id(suffix.split("/", 1)[0])
    return ""


def _read_only_task(spec: TaskSpec, metadata: dict[str, Any]) -> bool:
    if metadata.get("read_only") is True:
        return True
    task_type = str(metadata.get("task_type") or "").strip().lower()
    if task_type in {"analysis", "review", "diagnostic", "read_only"}:
        return True
    text = " ".join([spec.objective, *spec.constraints, *spec.acceptance]).lower()
    if any(hint in text for hint in IMPLEMENTATION_HINTS):
        return False
    return any(hint in text for hint in READ_ONLY_HINTS)


def _change_paths(change_id: str, capability: str) -> dict[str, str]:
    base = f"openspec/changes/{change_id}"
    return {
        "change_dir": base,
        "proposal": f"{base}/proposal.md",
        "design": f"{base}/design.md",
        "tasks": f"{base}/tasks.md",
        "spec": f"{base}/specs/{capability}/spec.md",
        "harness": f"{base}/harness.json",
    }


def _proposal_markdown(spec: TaskSpec) -> str:
    title = spec.objective or spec.task_id
    return (
        f"# {title}\n\n"
        "## Why\n"
        f"- Harness task `{spec.task_id}` requires a scoped project change.\n\n"
        "## What Changes\n"
        f"- {title}\n\n"
        "## Impact\n"
        f"- Risk level: `{spec.risk_level}`\n"
        f"- Working set: {', '.join(spec.working_set) if spec.working_set else 'to be confirmed'}\n"
    )


def _design_markdown(spec: TaskSpec) -> str:
    constraints = spec.constraints or ["Follow the repository governance and keep changes scoped."]
    return (
        "# Design\n\n"
        "## Context\n"
        f"- Task: `{spec.task_id}`\n"
        f"- Objective: {spec.objective or 'to be confirmed'}\n\n"
        "## Constraints\n"
        + "".join(f"- {item}\n" for item in constraints)
    )


def _tasks_markdown(spec: TaskSpec) -> str:
    acceptance = spec.acceptance or ["Acceptance criteria must be confirmed before implementation."]
    verification = spec.verification or ["Run the repository verification profile."]
    return (
        "# Tasks\n\n"
        "## Acceptance\n"
        + "".join(f"- [ ] {item}\n" for item in acceptance)
        + "\n## Verification\n"
        + "".join(f"- [ ] {item}\n" for item in verification)
        + "\n## Review Gate\n"
        "- [ ] Create a candidate commit and run `codex xhigh review --commit <commit-sha>`.\n"
    )


def _spec_markdown(spec: TaskSpec, capability: str) -> str:
    requirement = " ".join(part.capitalize() for part in capability.replace("_", "-").split("-") if part)
    requirement = requirement or "Harness Task Change"
    return (
        "## ADDED Requirements\n\n"
        f"### Requirement: {requirement}\n"
        f"The system SHALL satisfy the scoped change described by harness task `{spec.task_id}`.\n\n"
        "#### Scenario: Acceptance criteria are validated\n"
        "- **WHEN** the task verification is executed\n"
        "- **THEN** the implementation satisfies the recorded acceptance criteria\n"
    )


def _harness_payload(spec: TaskSpec, change_id: str, paths: dict[str, str]) -> dict[str, Any]:
    return {
        "version": 1,
        "harness_task_id": spec.task_id,
        "openspec_change_id": change_id,
        "risk_level": spec.risk_level,
        "working_set": spec.working_set or [paths["change_dir"]],
        "openspec_upstream": {
            "package": "@fission-ai/openspec",
            "version": "1.3.1",
            "schema": "spec-driven",
            "manifest": "openspec/upstream/openspec/manifest.json",
        },
        "verification_profile_ids": spec.verification or ["primary"],
        "review_gate": {"type": "codex_xhigh_review_commit", "required": True},
        "memory_policy": {"scope": spec.memory_scope},
        "archive_gate": {
            "requires_passed_verification": True,
            "requires_clean_review": True,
            "requires_openspec_validate": True,
        },
    }


def _write_if_missing(path: Path, content: str, relative_path: str = "") -> list[str]:
    if path.exists():
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return [relative_path or path.name]


def _write_json_if_missing(path: Path, payload: dict[str, Any], relative_path: str = "") -> list[str]:
    return _write_if_missing(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", relative_path)


def _merge_lists(left: list[str], right: Any) -> list[str]:
    result: list[str] = []
    for source in (left, right if isinstance(right, list) else []):
        for item in source:
            value = str(item).strip()
            if value and value not in result:
                result.append(value)
    return result


def _skipped(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "reason": reason}
