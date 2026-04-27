from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_STATUSES = [
    "created",
    "scoped",
    "context_loaded",
    "plan_ready",
    "executing",
    "verifying",
    "completed",
    "distilled",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return normalized[:80] or f"task-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    return [str(value).strip()]


@dataclass
class TaskSpec:
    task_id: str
    objective: str
    memory_scope: str = "project"
    project_root: str = ""
    status: str = "created"
    constraints: list[str] = field(default_factory=list)
    working_set: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], project_root: Path) -> "TaskSpec":
        objective = str(payload.get("objective") or payload.get("user_request") or "").strip()
        task_id = str(payload.get("task_id") or safe_id(objective)).strip()
        return cls(
            task_id=task_id,
            objective=objective,
            memory_scope=str(payload.get("memory_scope") or "project"),
            project_root=str(payload.get("project_root") or project_root),
            status=str(payload.get("status") or "created"),
            constraints=string_list(payload.get("constraints")),
            working_set=string_list(payload.get("working_set")),
            acceptance=string_list(payload.get("acceptance")),
            verification=string_list(payload.get("verification")),
            risk_level=str(payload.get("risk_level") or "medium"),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )

    @classmethod
    def load(cls, path: Path) -> "TaskSpec":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    def update_status(self, status: str) -> None:
        if status not in TASK_STATUSES:
            raise ValueError(f"Unknown task status: {status}")
        self.status = status
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_payload(path: str | None, inline_json: str | None) -> dict[str, Any]:
    if inline_json:
        value = json.loads(inline_json)
    elif path:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("Payload must be a JSON object.")
    return value


def harness_dir(project_root: Path) -> Path:
    return project_root / ".codex" / "harness"


def task_dir(project_root: Path, task_id: str) -> Path:
    return harness_dir(project_root) / "tasks" / safe_id(task_id)


def task_spec_path(project_root: Path, task_id: str) -> Path:
    return task_dir(project_root, task_id) / "task_spec.json"


def run_state_path(project_root: Path, task_id: str) -> Path:
    return task_dir(project_root, task_id) / "run_state.json"
