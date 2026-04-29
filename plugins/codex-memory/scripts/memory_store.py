from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import init_storage
from sensitive_scan import sanitized_payload


TASK_STATE_SCHEMA = {
    "type": "object",
    "required": ["task_id", "objective", "status"],
    "properties": {
        "task_id": {"type": "string"},
        "objective": {"type": "string"},
        "status": {"type": "string"},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "working_set": {"type": "array", "items": {"type": "string"}},
        "recent_findings": {"type": "array", "items": {"type": "string"}},
        "next_step": {"type": "string"},
        "metadata": {"type": "object"},
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [_string(item) for item in value]
        return [item for item in items if item]
    normalized = _string(value)
    return [normalized] if normalized else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_filename(task_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("._")
    return normalized or "task"


def _safe_task_id(task_id: str | None) -> str | None:
    if task_id is None:
        return None
    return str(sanitized_payload(task_id, context="task_id")).strip() or "task"


@dataclass
class TaskState:
    task_id: str
    objective: str = ""
    status: str = "open"
    constraints: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    working_set: list[str] = field(default_factory=list)
    recent_findings: list[str] = field(default_factory=list)
    next_step: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, task_id: str, payload: dict[str, Any] | None) -> "TaskState":
        payload = payload or {}
        return cls(
            task_id=task_id,
            objective=_string(payload.get("objective")),
            status=_string(payload.get("status")) or "open",
            constraints=_string_list(payload.get("constraints")),
            decisions=_string_list(payload.get("decisions")),
            open_questions=_string_list(payload.get("open_questions")),
            working_set=_string_list(payload.get("working_set")),
            recent_findings=_string_list(payload.get("recent_findings")),
            next_step=_string(payload.get("next_step")),
            metadata=_object(payload.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryStore:
    def __init__(self, db_path: Path | None = None) -> None:
        init_storage.ensure_storage_layout()
        self.db_path = db_path or init_storage.resolve_storage_paths().db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        safe_payload = sanitized_payload(payload, context=f"event:{event_type}")
        record = {
            "timestamp": _utc_now(),
            "event_type": event_type,
            "payload": safe_payload,
        }
        with init_storage.resolve_storage_paths().event_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _set_meta(self, key: str, value: Any) -> None:
        value_json = json.dumps(value, ensure_ascii=False)
        updated_at = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO plugin_meta (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, value_json, updated_at),
            )

    def _get_meta(self, key: str) -> Any | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM plugin_meta WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["value_json"]))

    def get_current_task_id(self) -> str | None:
        value = self._get_meta("current_task_id")
        if not isinstance(value, str) or not value.strip():
            return None
        return value

    def upsert_task_state(
        self,
        task_id: str,
        payload: dict[str, Any] | None,
        *,
        set_current: bool = True,
    ) -> dict[str, Any]:
        safe_task_id = _safe_task_id(task_id) or "task"
        state = TaskState.from_payload(safe_task_id, payload)
        updated_at = _utc_now()
        safe_state = sanitized_payload(state.to_dict(), context="task_state")
        payload_json = json.dumps(safe_state, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_state (task_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (safe_task_id, payload_json, updated_at),
            )
        if set_current:
            self._set_meta("current_task_id", safe_task_id)
        result = safe_state | {"updated_at": updated_at}
        self._append_event("task_state.upserted", result)
        return result

    def get_task_state(self, task_id: str | None = None) -> dict[str, Any] | None:
        resolved_task_id = _safe_task_id(task_id) if task_id is not None else self.get_current_task_id()
        if not resolved_task_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, updated_at FROM task_state WHERE task_id = ?",
                (resolved_task_id,),
            ).fetchone()
        if row is None:
            return TaskState(task_id=resolved_task_id).to_dict() | {"updated_at": None}
        payload = json.loads(str(row["payload_json"]))
        state = TaskState.from_payload(resolved_task_id, payload)
        return state.to_dict() | {"updated_at": row["updated_at"]}

    def write_repo_decision(
        self,
        title: str,
        details: str,
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        safe_task_id = _safe_task_id(task_id)
        safe_decision = sanitized_payload(
            {"title": _string(title), "details": _string(details)},
            context="repo_decision",
        )
        created_at = _utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO repo_decision (task_id, title, details, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (safe_task_id, safe_decision["title"], safe_decision["details"], created_at),
            )
            decision_id = int(cursor.lastrowid)
        result = {
            "id": decision_id,
            "task_id": safe_task_id,
            "title": safe_decision["title"],
            "details": safe_decision["details"],
            "created_at": created_at,
        }
        self._append_event("repo_decision.created", result)
        return result

    def list_repo_decisions(
        self,
        *,
        task_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        query = """
            SELECT id, task_id, title, details, created_at
            FROM repo_decision
        """
        params: tuple[Any, ...]
        if task_id:
            query += " WHERE task_id = ?"
            params = (_safe_task_id(task_id), limit)
            query += " ORDER BY id DESC LIMIT ?"
        else:
            params = (limit,)
            query += " ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "task_id": row["task_id"],
                "title": row["title"],
                "details": row["details"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def write_task_summary(self, task_id: str, summary_markdown: str) -> dict[str, Any]:
        safe_task_id = _safe_task_id(task_id) or "task"
        normalized_summary = str(
            sanitized_payload(summary_markdown.strip(), context="task_summary")
        )
        timestamp = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_summary (task_id, summary_markdown, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    summary_markdown = excluded.summary_markdown,
                    updated_at = excluded.updated_at
                """,
                (safe_task_id, normalized_summary, timestamp, timestamp),
            )
        file_path = init_storage.resolve_storage_paths().summary_dir / f"{_safe_filename(safe_task_id)}.md"
        file_path.write_text(normalized_summary + "\n", encoding="utf-8")
        result = {
            "task_id": safe_task_id,
            "summary_markdown": normalized_summary,
            "updated_at": timestamp,
            "file_path": str(file_path),
        }
        self._append_event("task_summary.written", result)
        return result

    def get_task_summary(self, task_id: str | None = None) -> dict[str, Any] | None:
        resolved_task_id = _safe_task_id(task_id) if task_id is not None else self.get_current_task_id()
        if not resolved_task_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT task_id, summary_markdown, updated_at
                FROM task_summary
                WHERE task_id = ?
                """,
                (resolved_task_id,),
            ).fetchone()
        if row is None:
            return None
        file_path = init_storage.resolve_storage_paths().summary_dir / f"{_safe_filename(resolved_task_id)}.md"
        return {
            "task_id": row["task_id"],
            "summary_markdown": row["summary_markdown"],
            "updated_at": row["updated_at"],
            "file_path": str(file_path),
        }
