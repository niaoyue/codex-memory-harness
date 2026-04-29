from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from context_builder import ContextBuilder
from distillation_store import DistillationStore
import init_storage
from memory_store import MemoryStore
from retrieval_store import RetrievalEngine
from sensitive_scan import sanitized_payload
from workspace_artifact_filters import is_subagent_artifact
import workspace_lifecycle


HOOK_EVENTS = [
    "on_session_start",
    "before_task",
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


class HookRunner:
    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        context_builder: ContextBuilder | None = None,
        distillation_store: DistillationStore | None = None,
    ) -> None:
        self.memory_store = memory_store or MemoryStore()
        self.retrieval_engine = retrieval_engine or RetrievalEngine()
        self.context_builder = context_builder or ContextBuilder(
            self.memory_store,
            self.retrieval_engine,
        )
        self.distillation_store = distillation_store or DistillationStore(
            self.memory_store,
            self.context_builder,
        )

    def run_event(self, event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if event not in HOOK_EVENTS:
            raise ValueError(f"Unsupported hook event: {event}")

        task_id = _string(payload.get("task_id")) or self.memory_store.get_current_task_id()
        if event == "before_task" and not task_id:
            task_id = _default_task_id()

        try:
            if event == "on_session_start":
                result = self._on_session_start(payload)
            elif event == "before_task":
                result = self._before_task(task_id or _default_task_id(), payload)
            elif event == "after_tool":
                result = self._after_tool(task_id, payload)
            elif event == "before_response":
                result = self._before_response(task_id, payload)
            elif event == "on_task_complete":
                result = self._on_task_complete(task_id, payload)
            else:
                raise ValueError(f"Unsupported hook event: {event}")
            return {
                "ok": True,
                "degraded": False,
                "event": event,
                "task_id": _result_task_id(result, task_id),
                "result": result,
            }
        except Exception as exc:
            return self._degraded_response(event, task_id, payload, exc)

    def _on_session_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        current_task = self.memory_store.get_task_state()
        recent_decisions = self.memory_store.list_repo_decisions(limit=5)
        return {
            "current_task": current_task,
            "recent_decisions": recent_decisions,
            "plugin_ready": True,
        }

    def _before_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current_state = self.memory_store.get_task_state(task_id) or {"task_id": task_id}
        objective = (
            _string(payload.get("objective"))
            or _string(payload.get("user_request"))
            or _string(payload.get("prompt"))
            or _string(current_state.get("objective"))
        )
        metadata = _merge_dicts(current_state.get("metadata"), payload.get("metadata"))
        workspace_routing = workspace_lifecycle.safe_workspace_routing(
            task_id,
            {
                "objective": objective,
                "working_set": _merge_lists(
                    _string_list(current_state.get("working_set")),
                    _string_list(payload.get("working_set")),
                ),
                "cwd": payload.get("cwd"),
            },
        )
        if workspace_routing:
            metadata["workspace_routing"] = workspace_routing
        merged_payload = {
            "objective": objective,
            "status": _string(payload.get("status")) or _string(current_state.get("status")) or "open",
            "constraints": _merge_lists(
                _string_list(current_state.get("constraints")),
                _string_list(payload.get("constraints")),
            ),
            "decisions": _string_list(current_state.get("decisions")),
            "open_questions": _merge_lists(
                _string_list(current_state.get("open_questions")),
                _string_list(payload.get("open_questions")),
            ),
            "working_set": _merge_lists(
                _string_list(current_state.get("working_set")),
                _string_list(payload.get("working_set")),
            ),
            "recent_findings": _string_list(current_state.get("recent_findings")),
            "next_step": _string(payload.get("next_step")) or _string(current_state.get("next_step")),
            "metadata": metadata,
        }
        task_state = self.memory_store.upsert_task_state(task_id, merged_payload, set_current=True)
        canonical_task_id = _string(task_state.get("task_id")) or task_id
        context_pack = self.context_builder.build_context_pack(
            task_id=canonical_task_id,
            queries=payload.get("queries"),
            retrieval_mode=_string(payload.get("retrieval_mode")) or "auto",
            max_total_chars=payload.get("max_total_chars"),
        )
        return {
            "task_state": task_state,
            "context_pack": context_pack,
        }

    def _after_tool(self, task_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        resolved_task_id = task_id or _default_task_id()
        current_state = self.memory_store.get_task_state(resolved_task_id) or {"task_id": resolved_task_id}
        tool_name = _string(payload.get("tool_name")) or "tool"
        summary = (
            _string(payload.get("summary"))
            or _string(payload.get("tool_output_summary"))
            or _string(payload.get("output"))
            or "Tool executed."
        )
        touched_paths = _string_list(payload.get("touched_paths")) or _string_list(payload.get("files"))
        metadata = _merge_dicts(current_state.get("metadata"), payload.get("metadata"))
        previous_routing = metadata.get("workspace_routing") if isinstance(metadata.get("workspace_routing"), dict) else {}
        previous_bindings = previous_routing.get("bindings") if isinstance(previous_routing, dict) else None
        adaptive_routing = workspace_lifecycle.safe_workspace_routing(
            resolved_task_id,
            {
                "objective": current_state.get("objective"),
                "working_set": _merge_lists(_string_list(current_state.get("working_set")), touched_paths),
                "touched_paths": touched_paths,
                "cwd": payload.get("cwd"),
            },
        )
        workspace_routing = dict(previous_routing) if previous_routing else adaptive_routing
        if workspace_routing:
            if previous_routing and adaptive_routing:
                if isinstance(adaptive_routing.get("route_plan"), dict):
                    workspace_routing["adaptive_route_plan"] = adaptive_routing["route_plan"]
                if isinstance(adaptive_routing.get("bindings"), list):
                    workspace_routing["adaptive_bindings"] = adaptive_routing["bindings"]
                if adaptive_routing.get("degraded"):
                    workspace_routing["adaptive_degraded"] = adaptive_routing
            signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
            scope_source_bindings = previous_bindings or workspace_routing.get("bindings")
            if not scope_source_bindings and isinstance(adaptive_routing.get("bindings"), list):
                scope_source_bindings = adaptive_routing["bindings"]
            if isinstance(signals.get("route_plan"), dict):
                workspace_routing["route_plan"] = signals["route_plan"]
                workspace_routing["bindings"] = workspace_lifecycle.create_bindings(signals["route_plan"])
                scope_source_bindings = workspace_routing["bindings"]
            if isinstance(signals.get("verification_aggregation"), dict):
                workspace_routing["verification_aggregation"] = signals["verification_aggregation"]
            scope_bindings = _select_scope_bindings(scope_source_bindings, payload)
            if is_subagent_artifact(payload):
                next_scope_guard = workspace_lifecycle.safe_scope_guard(
                    scope_bindings,
                    touched_paths,
                )
                workspace_routing["scope_guard"] = workspace_lifecycle.merge_scope_guard_history(
                    workspace_routing.get("scope_guard"), next_scope_guard
                )
            metadata["workspace_routing"] = workspace_routing
        finding = f"{tool_name}: {summary}"
        merged_payload = {
            "objective": _string(current_state.get("objective")),
            "status": _string(current_state.get("status")) or "in_progress",
            "constraints": _string_list(current_state.get("constraints")),
            "decisions": _string_list(current_state.get("decisions")),
            "open_questions": _string_list(current_state.get("open_questions")),
            "working_set": _merge_lists(_string_list(current_state.get("working_set")), touched_paths),
            "recent_findings": _merge_lists(
                _string_list(current_state.get("recent_findings")),
                [finding],
            ),
            "next_step": _string(payload.get("next_step")) or _string(current_state.get("next_step")),
            "metadata": metadata,
        }
        task_state = self.memory_store.upsert_task_state(resolved_task_id, merged_payload, set_current=True)
        return {"task_state": task_state}

    def _before_response(self, task_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        resolved_task_id = task_id or self.memory_store.get_current_task_id()
        context_pack = self.context_builder.build_context_pack(
            task_id=resolved_task_id,
            queries=payload.get("queries"),
            retrieval_mode=_string(payload.get("retrieval_mode")) or "auto",
            max_total_chars=payload.get("max_total_chars"),
        )
        task_state = self.memory_store.get_task_state(resolved_task_id)
        return {
            "context_pack": context_pack,
            "workspace_routing_review": workspace_lifecycle.routing_review(task_state),
        }

    def _on_task_complete(self, task_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        resolved_task_id = task_id or self.memory_store.get_current_task_id() or _default_task_id()
        current_state = self.memory_store.get_task_state(resolved_task_id) or {"task_id": resolved_task_id}
        merged_payload = {
            "objective": _string(current_state.get("objective")) or _string(payload.get("objective")),
            "status": _string(payload.get("status")) or "done",
            "constraints": _string_list(current_state.get("constraints")),
            "decisions": _string_list(current_state.get("decisions")),
            "open_questions": _string_list(current_state.get("open_questions")),
            "working_set": _string_list(current_state.get("working_set")),
            "recent_findings": _string_list(current_state.get("recent_findings")),
            "next_step": _string(payload.get("next_step")),
            "metadata": current_state.get("metadata") or {},
        }
        task_state = self.memory_store.upsert_task_state(resolved_task_id, merged_payload, set_current=True)

        summary_markdown = _string(payload.get("summary_markdown"))
        if not summary_markdown:
            lines = ["# Task Completion Summary", ""]
            if task_state.get("objective"):
                lines.append(f"- Objective: {task_state['objective']}")
            lines.append(f"- Status: {task_state.get('status', 'done')}")
            recent_findings = task_state.get("recent_findings") or []
            if recent_findings:
                lines.append("- Recent Findings:")
                lines.extend([f"  - {item}" for item in recent_findings[:5]])
            summary_markdown = "\n".join(lines)

        summary = self.memory_store.write_task_summary(resolved_task_id, summary_markdown)
        distillation_result = self.distillation_store.distill_task(
            task_id=resolved_task_id,
            queries=payload.get("queries"),
            retrieval_mode=_string(payload.get("retrieval_mode")) or "auto",
            max_total_chars=int(payload.get("max_total_chars", 2400)),
        )
        return {
            "task_state": task_state,
            "summary": summary,
            "distillation_result": distillation_result,
        }

    def _degraded_response(
        self,
        event: str,
        task_id: str | None,
        payload: dict[str, Any],
        exc: Exception,
    ) -> dict[str, Any]:
        reason = f"{type(exc).__name__}: {exc}"
        safe_task_id = _safe_task_id(task_id)
        fallback: dict[str, Any]
        if event in ("before_task", "before_response"):
            fallback = {"context_pack": _build_fallback_context(safe_task_id, reason)}
        elif event == "on_task_complete":
            fallback = {
                "summary": {
                    "task_id": safe_task_id,
                    "summary_markdown": f"Task completed in degraded mode.\n\nReason: {reason}",
                }
            }
        else:
            fallback = {"message": f"Hook degraded: {reason}"}

        return {
            "ok": False,
            "degraded": True,
            "event": event,
            "task_id": safe_task_id,
            "reason": reason,
            "fallback": fallback,
        }


def _cleanup_demo_task(task_id: str) -> None:
    init_storage.ensure_storage_layout()
    paths = init_storage.resolve_storage_paths()
    with closing(sqlite3.connect(paths.db_path)) as conn:
        conn.execute("DELETE FROM task_state WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM repo_decision WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task_summary WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM distilled_asset WHERE task_id = ?", (task_id,))
        conn.execute(
            "DELETE FROM plugin_meta WHERE key = ? AND value_json = ?",
            ("current_task_id", json.dumps(task_id, ensure_ascii=False)),
        )
        conn.commit()
    summary_file = paths.summary_dir / f"{task_id}.md"
    if summary_file.exists():
        summary_file.unlink()
    for file_path in paths.distilled_dir.glob(f"{task_id}*.md"):
        file_path.unlink()
    if paths.event_log_path.exists():
        lines = paths.event_log_path.read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if task_id not in line]
        paths.event_log_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Codex Memory plugin hooks.")
    parser.add_argument("--event", required=True, choices=HOOK_EVENTS, help="Hook event name")
    parser.add_argument("--payload-json", help="Inline JSON object payload")
    parser.add_argument("--payload-file", help="Path to a JSON object payload file")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on degraded execution")
    parser.add_argument("--cleanup-task-id", help="Delete all stored data for a task id and exit")
    parser.add_argument("--memory-scope", choices=["project", "global", "auto"], help="Memory storage scope")
    parser.add_argument("--memory-cwd", help="Directory used to resolve project memory")
    args = parser.parse_args()

    if args.memory_scope:
        import os

        os.environ["CODEX_MEMORY_SCOPE"] = args.memory_scope
    if args.memory_cwd:
        import os

        os.environ["CODEX_MEMORY_CWD"] = args.memory_cwd

    init_storage.ensure_storage_layout()

    if args.cleanup_task_id:
        _cleanup_demo_task(args.cleanup_task_id)
        print(json.dumps({"ok": True, "cleaned_task_id": args.cleanup_task_id}, ensure_ascii=False, indent=2))
        return 0

    payload = _load_payload(args.payload_json, args.payload_file)
    runner = HookRunner()
    result = runner.run_event(args.event, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and result.get("degraded"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
