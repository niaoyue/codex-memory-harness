from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from context_builder import ContextBuilder
import init_storage
from memory_store import MemoryStore


DISTILLED_ASSET_SCHEMA = {
    "type": "object",
    "required": ["id", "asset_type", "title", "summary_text", "file_path", "created_at"],
    "properties": {
        "id": {"type": "integer"},
        "task_id": {"type": ["string", "null"]},
        "asset_type": {"type": "string"},
        "title": {"type": "string"},
        "summary_text": {"type": "string"},
        "file_path": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "payload": {"type": "object"},
        "created_at": {"type": "string"},
    },
}


DISTILLATION_RESULT_SCHEMA = {
    "type": "object",
    "required": ["asset", "context_pack"],
    "properties": {
        "asset": DISTILLED_ASSET_SCHEMA,
        "context_pack": {"type": "object"},
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return normalized or "asset"


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


@dataclass
class DistilledAsset:
    id: int
    task_id: str | None
    asset_type: str
    title: str
    summary_text: str
    file_path: str
    tags: list[str]
    payload: dict[str, Any]
    created_at: str

    def to_dict(self, *, include_payload: bool = True) -> dict[str, Any]:
        data = {
            "id": self.id,
            "task_id": self.task_id,
            "asset_type": self.asset_type,
            "title": self.title,
            "summary_text": self.summary_text,
            "file_path": self.file_path,
            "tags": self.tags,
            "created_at": self.created_at,
        }
        if include_payload:
            data["payload"] = self.payload
        return data


class DistillationStore:
    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        context_builder: ContextBuilder | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.memory_store = memory_store or MemoryStore()
        self.context_builder = context_builder or ContextBuilder(self.memory_store)
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
        record = {
            "timestamp": _utc_now(),
            "event_type": event_type,
            "payload": payload,
        }
        with init_storage.resolve_storage_paths().event_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def distill_task(
        self,
        *,
        task_id: str | None = None,
        queries: list[str] | str | None = None,
        retrieval_mode: str = "auto",
        max_total_chars: int = 2400,
        asset_type: str = "task_pattern",
        decision_limit: int = 8,
    ) -> dict[str, Any]:
        context_pack = self.context_builder.build_context_pack(
            task_id=task_id,
            queries=queries,
            retrieval_mode=retrieval_mode,
            max_total_chars=max_total_chars,
            decision_limit=decision_limit,
        )
        resolved_task_id = context_pack.get("task_id") or task_id

        task_state = self.memory_store.get_task_state(resolved_task_id) if resolved_task_id else None
        task_summary = (
            self.memory_store.get_task_summary(resolved_task_id) if resolved_task_id else None
        )
        repo_decisions = self.memory_store.list_repo_decisions(
            task_id=resolved_task_id,
            limit=decision_limit,
        )

        title = self._build_title(task_state, resolved_task_id)
        summary_text = self._build_summary_text(task_state, task_summary, repo_decisions)
        tags = self._build_tags(task_state, context_pack)
        payload = {
            "task_state": task_state,
            "task_summary": task_summary,
            "repo_decisions": repo_decisions,
            "context_pack": context_pack,
            "suggested_skill_draft": self._build_skill_draft(task_state, context_pack),
        }
        markdown = self._render_asset_markdown(title, summary_text, payload)

        created_at = _utc_now()
        file_path = self._write_asset_file(
            task_id=resolved_task_id,
            title=title,
            created_at=created_at,
            markdown=markdown,
        )

        payload_json = json.dumps(payload, ensure_ascii=False)
        tags_json = json.dumps(tags, ensure_ascii=False)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO distilled_asset (
                    task_id,
                    asset_type,
                    title,
                    summary_text,
                    file_path,
                    tags_json,
                    payload_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_task_id,
                    asset_type,
                    title,
                    summary_text,
                    str(file_path),
                    tags_json,
                    payload_json,
                    created_at,
                ),
            )
            asset_id = int(cursor.lastrowid)

        asset = DistilledAsset(
            id=asset_id,
            task_id=resolved_task_id,
            asset_type=asset_type,
            title=title,
            summary_text=summary_text,
            file_path=str(file_path),
            tags=tags,
            payload=payload,
            created_at=created_at,
        )
        self._append_event("distilled_asset.created", asset.to_dict())
        return {
            "asset": asset.to_dict(),
            "context_pack": context_pack,
        }

    def list_distilled_assets(
        self,
        *,
        task_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        query = """
            SELECT id, task_id, asset_type, title, summary_text, file_path, tags_json, payload_json, created_at
            FROM distilled_asset
        """
        params: tuple[Any, ...]
        if task_id:
            query += " WHERE task_id = ? ORDER BY id DESC LIMIT ?"
            params = (task_id, limit)
        else:
            query += " ORDER BY id DESC LIMIT ?"
            params = (limit,)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_asset(row).to_dict(include_payload=False) for row in rows]

    def get_distilled_asset(
        self,
        *,
        asset_id: int | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT id, task_id, asset_type, title, summary_text, file_path, tags_json, payload_json, created_at
            FROM distilled_asset
        """
        params: tuple[Any, ...]
        if asset_id is not None:
            query += " WHERE id = ?"
            params = (int(asset_id),)
        elif task_id is not None:
            query += " WHERE task_id = ? ORDER BY id DESC LIMIT 1"
            params = (task_id,)
        else:
            raise ValueError("Either asset_id or task_id is required.")

        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            return None
        return self._row_to_asset(row).to_dict()

    def _row_to_asset(self, row: sqlite3.Row) -> DistilledAsset:
        return DistilledAsset(
            id=int(row["id"]),
            task_id=row["task_id"],
            asset_type=str(row["asset_type"]),
            title=str(row["title"]),
            summary_text=str(row["summary_text"]),
            file_path=str(row["file_path"]),
            tags=_string_list(json.loads(str(row["tags_json"]))),
            payload=json.loads(str(row["payload_json"])),
            created_at=str(row["created_at"]),
        )

    def _build_title(self, task_state: dict[str, Any] | None, task_id: str | None) -> str:
        objective = (task_state or {}).get("objective")
        if isinstance(objective, str) and objective.strip():
            return objective.strip()
        if task_id:
            return f"Distilled Asset for {task_id}"
        return "Distilled Task Asset"

    def _build_summary_text(
        self,
        task_state: dict[str, Any] | None,
        task_summary: dict[str, Any] | None,
        repo_decisions: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        if task_state:
            if task_state.get("objective"):
                parts.append(f"目标：{task_state['objective']}")
            if task_state.get("next_step"):
                parts.append(f"下一步：{task_state['next_step']}")
        if repo_decisions:
            parts.append(f"关键决策数：{len(repo_decisions)}")
        if task_summary and task_summary.get("summary_markdown"):
            summary_line = str(task_summary["summary_markdown"]).splitlines()[0].strip()
            if summary_line:
                parts.append(f"总结：{summary_line}")
        return " | ".join(parts) if parts else "Task distillation asset"

    def _build_tags(
        self,
        task_state: dict[str, Any] | None,
        context_pack: dict[str, Any],
    ) -> list[str]:
        tags = {"task-pattern"}
        for item in (task_state or {}).get("working_set") or []:
            suffix = Path(str(item)).suffix.lower()
            if suffix:
                tags.add(suffix.lstrip("."))
        for query in context_pack.get("evidence_queries", [])[:3]:
            cleaned = str(query).strip()
            if cleaned:
                tags.add(cleaned[:32])
        return sorted(tags)

    def _build_skill_draft(
        self,
        task_state: dict[str, Any] | None,
        context_pack: dict[str, Any],
    ) -> dict[str, Any]:
        objective = (task_state or {}).get("objective") or "Task distillation placeholder"
        evidence_queries = context_pack.get("evidence_queries", [])
        return {
            "name": f"{_safe_filename(str(objective))}-draft",
            "trigger_hint": "在相似任务重复出现时升级为真实技能",
            "starter_queries": evidence_queries[:3],
            "notes": [
                "优先读取 task state 与最近决策",
                "必要时根据 working_set 自动派生检索词",
                "将高分证据包裁剪后再注入上下文",
            ],
        }

    def _render_asset_markdown(
        self,
        title: str,
        summary_text: str,
        payload: dict[str, Any],
    ) -> str:
        task_state = payload.get("task_state") or {}
        task_summary = payload.get("task_summary") or {}
        repo_decisions = payload.get("repo_decisions") or []
        context_pack = payload.get("context_pack") or {}
        skill_draft = payload.get("suggested_skill_draft") or {}

        lines = [f"# {title}", "", f"摘要：{summary_text}", ""]

        if task_state:
            lines.extend(
                [
                    "## Task Snapshot",
                    f"- Objective: {task_state.get('objective', '')}",
                    f"- Status: {task_state.get('status', '')}",
                    f"- Next Step: {task_state.get('next_step', '')}",
                    "",
                ]
            )

        constraints = task_state.get("constraints") or []
        if constraints:
            lines.append("## Constraints")
            lines.extend([f"- {item}" for item in constraints])
            lines.append("")

        if repo_decisions:
            lines.append("## Reusable Decisions")
            seen: set[tuple[str, str]] = set()
            for item in repo_decisions:
                key = (str(item["title"]), str(item["details"]))
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"- {item['title']}: {item['details']}")
            lines.append("")

        if task_summary.get("summary_markdown"):
            lines.extend(["## Task Summary", str(task_summary["summary_markdown"]).strip(), ""])

        if context_pack.get("evidence_queries"):
            lines.append("## Retrieval Hints")
            lines.extend([f"- {query}" for query in context_pack["evidence_queries"]])
            lines.append("")

        rendered_context = str(context_pack.get("rendered_context") or "").strip()
        if rendered_context:
            lines.extend(["## Context Pack Snapshot", rendered_context, ""])

        if skill_draft:
            lines.append("## Skill Draft Placeholder")
            lines.append(f"- Name: {skill_draft.get('name', '')}")
            lines.append(f"- Trigger Hint: {skill_draft.get('trigger_hint', '')}")
            starter_queries = skill_draft.get("starter_queries") or []
            if starter_queries:
                lines.append("- Starter Queries:")
                lines.extend([f"  - {query}" for query in starter_queries])
            notes = skill_draft.get("notes") or []
            if notes:
                lines.append("- Notes:")
                lines.extend([f"  - {note}" for note in notes])
            lines.append("")

        return "\n".join(line.rstrip() for line in lines).strip() + "\n"

    def _write_asset_file(
        self,
        *,
        task_id: str | None,
        title: str,
        created_at: str,
        markdown: str,
    ) -> Path:
        stamp = created_at.replace(":", "").replace("-", "").replace("+00:00", "Z")
        name_parts = [_safe_filename(task_id or "task"), _safe_filename(title)[:48], stamp]
        filename = "--".join(part for part in name_parts if part) + ".md"
        file_path = init_storage.resolve_storage_paths().distilled_dir / filename
        file_path.write_text(markdown, encoding="utf-8")
        return file_path
