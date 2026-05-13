from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_store import MemoryStore
from retrieval_store import RetrievalEngine


DEFAULT_CONTEXT_BUDGET = {
    "total_chars": 4200,
    "task_state_chars": 1100,
    "summary_chars": 900,
    "decisions_chars": 800,
    "learned_chars": 500,
    "evidence_chars": 1200,
}


CONTEXT_PACK_SCHEMA = {
    "type": "object",
    "required": ["task_id", "budget", "sections", "rendered_context"],
    "properties": {
        "task_id": {"type": ["string", "null"]},
        "budget": {
            "type": "object",
            "properties": {
                "total_chars": {"type": "integer"},
                "task_state_chars": {"type": "integer"},
                "summary_chars": {"type": "integer"},
                "decisions_chars": {"type": "integer"},
                "learned_chars": {"type": "integer"},
                "evidence_chars": {"type": "integer"},
                "used_chars": {"type": "integer"},
            },
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "title", "content", "chars_used", "truncated"],
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "chars_used": {"type": "integer"},
                    "truncated": {"type": "boolean"},
                },
            },
        },
        "evidence_queries": {
            "type": "array",
            "items": {"type": "string"},
        },
        "rendered_context": {"type": "string"},
    },
}


@dataclass
class SectionResult:
    name: str
    title: str
    content: str
    chars_used: int
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "content": self.content,
            "chars_used": self.chars_used,
            "truncated": self.truncated,
        }


def _clean_query_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    raise ValueError("queries must be a string or a list of strings")


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    text = text.strip()
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    if limit <= 3:
        return text[:limit], True
    return text[: limit - 3].rstrip() + "...", True


def _render_bullets(items: list[str], bullet: str = "- ") -> str:
    lines = [f"{bullet}{item}" for item in items if item]
    return "\n".join(lines).strip()


def _normalize_budget(max_total_chars: int | None = None) -> dict[str, int]:
    budget = dict(DEFAULT_CONTEXT_BUDGET)
    if max_total_chars is not None:
        budget["total_chars"] = max(800, int(max_total_chars))

    total_target = budget["total_chars"]
    alloc_total = (
        budget["task_state_chars"]
        + budget["summary_chars"]
        + budget["decisions_chars"]
        + budget["learned_chars"]
        + budget["evidence_chars"]
    )
    if alloc_total > total_target:
        scale = total_target / alloc_total
        for key in (
            "task_state_chars",
            "summary_chars",
            "decisions_chars",
            "learned_chars",
            "evidence_chars",
        ):
            budget[key] = max(120, int(budget[key] * scale))
    return budget


def _default_queries_from_task_state(task_state: dict[str, Any] | None) -> list[str]:
    if not task_state:
        return []

    seen: set[str] = set()
    queries: list[str] = []

    for item in task_state.get("working_set") or []:
        candidate = Path(str(item).strip()).name
        if candidate and candidate not in seen:
            seen.add(candidate)
            queries.append(candidate)

    objective = str(task_state.get("objective") or "").strip()
    if objective and len(objective) <= 80 and objective not in seen:
        seen.add(objective)
        queries.append(objective)

    return queries[:4]


class ContextBuilder:
    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        retrieval_engine: RetrievalEngine | None = None,
    ) -> None:
        self.memory_store = memory_store or MemoryStore()
        self.retrieval_engine = retrieval_engine or RetrievalEngine()

    def build_context_pack(
        self,
        *,
        task_id: str | None = None,
        queries: list[str] | str | None = None,
        retrieval_mode: str = "auto",
        evidence_limit_per_query: int = 4,
        max_total_chars: int | None = None,
        decision_limit: int = 8,
    ) -> dict[str, Any]:
        budget = _normalize_budget(max_total_chars)
        resolved_task_id = task_id or self.memory_store.get_current_task_id()

        task_state = self.memory_store.get_task_state(resolved_task_id) if resolved_task_id else None
        task_summary = (
            self.memory_store.get_task_summary(resolved_task_id) if resolved_task_id else None
        )
        decisions = self.memory_store.list_repo_decisions(
            task_id=resolved_task_id,
            limit=decision_limit,
        )
        learned_candidates = self._accepted_memory_candidates(task_state, limit=5)

        evidence_queries = _clean_query_list(queries)
        if not evidence_queries:
            evidence_queries = _default_queries_from_task_state(task_state)
        evidence_items = self._collect_evidence(
            evidence_queries,
            retrieval_mode=retrieval_mode,
            evidence_limit_per_query=evidence_limit_per_query,
        )

        sections: list[SectionResult] = []
        remaining_total = budget["total_chars"]

        task_state_section = self._build_task_state_section(
            task_state,
            min(budget["task_state_chars"], remaining_total),
        )
        sections.append(task_state_section)
        remaining_total = max(0, remaining_total - task_state_section.chars_used)

        summary_section = self._build_summary_section(
            task_summary,
            min(budget["summary_chars"], remaining_total),
        )
        sections.append(summary_section)
        remaining_total = max(0, remaining_total - summary_section.chars_used)

        decisions_section = self._build_decisions_section(
            decisions,
            min(budget["decisions_chars"], remaining_total),
        )
        sections.append(decisions_section)
        remaining_total = max(0, remaining_total - decisions_section.chars_used)

        learned_section = self._build_learned_preferences_section(
            learned_candidates,
            min(budget["learned_chars"], remaining_total),
        )
        sections.append(learned_section)
        remaining_total = max(0, remaining_total - learned_section.chars_used)

        evidence_section = self._build_evidence_section(
            evidence_items,
            min(budget["evidence_chars"], remaining_total),
        )
        sections.append(evidence_section)

        rendered_parts = []
        for section in sections:
            if not section.content:
                continue
            rendered_parts.append(f"## {section.title}\n{section.content}")
        rendered_context = "\n\n".join(rendered_parts).strip()

        used_chars = sum(section.chars_used for section in sections)
        canonical_task_id = task_state.get("task_id") if isinstance(task_state, dict) else resolved_task_id
        return {
            "task_id": canonical_task_id,
            "budget": budget | {"used_chars": used_chars},
            "sections": [section.to_dict() for section in sections],
            "evidence_queries": evidence_queries,
            "rendered_context": rendered_context,
        }

    def _collect_evidence(
        self,
        queries: list[str],
        *,
        retrieval_mode: str,
        evidence_limit_per_query: int,
    ) -> list[dict[str, Any]]:
        combined: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int | None, str]] = set()
        for query in queries:
            evidence_pack = self.retrieval_engine.search(
                query,
                mode=retrieval_mode,
                limit=evidence_limit_per_query,
            )
            for item in evidence_pack["items"]:
                key = (
                    item["path"],
                    item["match_type"],
                    item.get("line"),
                    item["snippet"],
                )
                if key in seen:
                    continue
                seen.add(key)
                combined.append(item)
        combined.sort(key=lambda item: (-float(item["score"]), item["path"], item.get("line") or 0))
        return combined

    def _accepted_memory_candidates(
        self,
        task_state: dict[str, Any] | None,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        try:
            import memory_mining
        except Exception:
            return []

        metadata = task_state.get("metadata") if isinstance(task_state, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        routing = metadata.get("workspace_routing") or {}
        route_plan = routing.get("route_plan") if isinstance(routing, dict) else {}
        route_plan = route_plan if isinstance(route_plan, dict) else {}
        project_id = str(
            metadata.get("project_id")
            or route_plan.get("primary_project")
            or route_plan.get("project_id")
            or ""
        )
        intent = str(route_plan.get("task_intent") or metadata.get("task_intent") or "")
        working_set = task_state.get("working_set") if isinstance(task_state, dict) else []
        try:
            return memory_mining.accepted_context(
                limit=limit,
                project_id=project_id,
                scope="project",
                intent=intent,
                working_set=list(working_set or []),
            )
        except Exception:
            return []

    def _build_task_state_section(
        self,
        task_state: dict[str, Any] | None,
        limit: int,
    ) -> SectionResult:
        title = "Task State"
        if not task_state:
            return SectionResult("task_state", title, "", 0, False)

        lines: list[str] = []
        if task_state.get("objective"):
            lines.append(f"- Objective: {task_state['objective']}")
        if task_state.get("status"):
            lines.append(f"- Status: {task_state['status']}")
        if task_state.get("next_step"):
            lines.append(f"- Next Step: {task_state['next_step']}")

        for key, label in (
            ("constraints", "Constraints"),
            ("decisions", "Decisions"),
            ("open_questions", "Open Questions"),
            ("working_set", "Working Set"),
            ("recent_findings", "Recent Findings"),
        ):
            values = task_state.get(key) or []
            if values:
                lines.append(f"- {label}:")
                lines.extend([f"  - {value}" for value in values])

        content, truncated = _truncate_text("\n".join(lines), limit)
        return SectionResult("task_state", title, content, len(content), truncated)

    def _build_summary_section(
        self,
        task_summary: dict[str, Any] | None,
        limit: int,
    ) -> SectionResult:
        title = "Task Summary"
        if not task_summary:
            return SectionResult("task_summary", title, "", 0, False)
        content, truncated = _truncate_text(task_summary.get("summary_markdown", ""), limit)
        return SectionResult("task_summary", title, content, len(content), truncated)

    def _build_decisions_section(
        self,
        decisions: list[dict[str, Any]],
        limit: int,
    ) -> SectionResult:
        title = "Repo Decisions"
        if not decisions:
            return SectionResult("repo_decisions", title, "", 0, False)

        lines = []
        seen: set[tuple[str, str]] = set()
        for item in decisions:
            key = (str(item["title"]), str(item["details"]))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {item['title']}: {item['details']}")
        content, truncated = _truncate_text("\n".join(lines), limit)
        return SectionResult("repo_decisions", title, content, len(content), truncated)

    def _build_learned_preferences_section(
        self,
        candidates: list[dict[str, Any]],
        limit: int,
    ) -> SectionResult:
        title = "Learned Preferences"
        if not candidates:
            return SectionResult("learned_preferences", title, "", 0, False)

        lines = []
        for item in candidates:
            statement = str(item.get("statement") or "").strip()
            if not statement:
                continue
            confidence = str(item.get("confidence") or "unknown").strip()
            risk = str(item.get("risk") or "unknown").strip()
            lines.append(f"- {statement} (confidence={confidence}, risk={risk})")
        content, truncated = _truncate_text("\n".join(lines), limit)
        return SectionResult("learned_preferences", title, content, len(content), truncated)

    def _build_evidence_section(
        self,
        evidence_items: list[dict[str, Any]],
        limit: int,
    ) -> SectionResult:
        title = "Evidence"
        if not evidence_items:
            return SectionResult("evidence", title, "", 0, False)

        lines = []
        for item in evidence_items:
            location = item["path"]
            if item.get("line") is not None:
                location = f"{location}:{item['line']}"
            lines.append(
                f"- [{item['match_type']}] {location} | score={item['score']:.1f}"
            )
            lines.append(f"  {item['snippet']}")

        content, truncated = _truncate_text("\n".join(lines), limit)
        return SectionResult("evidence", title, content, len(content), truncated)
