from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from context_builder import ContextBuilder
from distillation_store import DistillationStore
from hook_runner_cleanup import cleanup_demo_task
from hook_runner_write_guard import run_before_first_write
from hook_runner_utils import (
    HOOK_EVENTS,
    _build_fallback_context,
    _default_task_id,
    _load_payload,
    _merge_dicts,
    _merge_lists,
    _result_task_id,
    _safe_task_id,
    _select_scope_bindings,
    _string,
    _string_list,
    _utc_stamp,
)
import init_storage
from memory_store import MemoryStore
from retrieval_store import RetrievalEngine
import skill_routing_audit
import unfinished_task_summary
from workspace_artifact_filters import (
    is_subagent_artifact,
    routing_excluded_paths as filtered_routing_excluded_paths,
    routing_touched_paths as filtered_routing_touched_paths,
)
import workspace_lifecycle
import workspace_memory_writer

TRANSIENT_ROUTING_FIELDS = (
    "review_gate_running",
    "xhigh_review_dispatch_disabled",
)

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
            elif event == "before_first_write":
                result = run_before_first_write(task_id, payload)
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
        routing_excluded_paths = _without_paths(_string_list(metadata.get("routing_excluded_paths")), _string_list(payload.get("working_set")))
        metadata["routing_excluded_paths"] = routing_excluded_paths
        routing_working_set = _merge_lists(_without_paths(_string_list(current_state.get("working_set")), routing_excluded_paths), _string_list(payload.get("working_set")))
        routing_payload = {
            "objective": objective,
            "working_set": routing_working_set,
            "cwd": payload.get("cwd"),
            "metadata": metadata,
        }
        _copy_transient_routing_fields(payload, routing_payload)
        for field in ("use_subagents", "subagent_mode"):
            if field in payload:
                routing_payload[field] = payload[field]
                metadata[field] = payload[field]
        for field in workspace_lifecycle.requirement_task_fields():
            if field in payload:
                routing_payload[field] = payload[field]
                metadata[field] = payload[field]
        workspace_routing = workspace_lifecycle.safe_workspace_routing(task_id, routing_payload)
        if workspace_routing:
            metadata["workspace_routing"] = workspace_routing
        metadata["skill_routing_audit"] = skill_routing_audit.match_task_skills(
            task_id=task_id,
            task={
                "objective": objective,
                "working_set": routing_working_set,
                "metadata": metadata,
            },
            previous=metadata.get("skill_routing_audit") if isinstance(metadata.get("skill_routing_audit"), dict) else None,
        )
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
            retrieval_mode=_context_retrieval_mode(payload),
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
        routing_touched_paths = filtered_routing_touched_paths(tool_name, payload, touched_paths)
        metadata = _merge_dicts(current_state.get("metadata"), payload.get("metadata"))
        metadata["skill_routing_audit"] = skill_routing_audit.merge_payload_decisions(
            metadata.get("skill_routing_audit") if isinstance(metadata.get("skill_routing_audit"), dict) else {},
            payload,
            event="after_tool",
        )
        existing_excluded_paths = _string_list(metadata.get("routing_excluded_paths"))
        owned_working_set = _without_paths(_merge_lists(_string_list(current_state.get("working_set")), _string_list(payload.get("working_set"))), existing_excluded_paths)
        stored_excluded_paths = _without_paths(existing_excluded_paths, routing_touched_paths)
        candidate_excluded_paths = _without_paths(filtered_routing_excluded_paths(tool_name, payload, touched_paths), owned_working_set)
        routing_excluded_paths = _merge_lists(stored_excluded_paths, candidate_excluded_paths)
        if routing_excluded_paths:
            metadata["routing_excluded_paths"] = routing_excluded_paths
        else:
            metadata.pop("routing_excluded_paths", None)
        previous_routing = metadata.get("workspace_routing") if isinstance(metadata.get("workspace_routing"), dict) else {}
        previous_bindings = previous_routing.get("bindings") if isinstance(previous_routing, dict) else None
        adaptive_routing = {}
        if routing_touched_paths or _has_routing_signal(payload) or _has_routing_metadata(payload):
            previous_working_set = _without_paths(_string_list(current_state.get("working_set")), routing_excluded_paths)
            adaptive_routing = workspace_lifecycle.safe_workspace_routing(
                resolved_task_id,
                _with_transient_routing_fields(
                    payload,
                    {
                        "objective": current_state.get("objective"),
                        "working_set": _merge_lists(previous_working_set, routing_touched_paths),
                        "touched_paths": routing_touched_paths,
                        "cwd": payload.get("cwd"),
                        "metadata": metadata,
                    },
                ),
            )
        workspace_routing = dict(previous_routing) if previous_routing else adaptive_routing
        if workspace_routing:
            if previous_routing and adaptive_routing:
                workspace_lifecycle.merge_adaptive_routing(workspace_routing, adaptive_routing)
            signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
            explicit_scope = _has_explicit_scope(payload)
            scope_source_bindings = previous_bindings or workspace_routing.get("bindings")
            if not explicit_scope and isinstance(adaptive_routing.get("bindings"), list):
                scope_source_bindings = adaptive_routing["bindings"]
            elif not scope_source_bindings and isinstance(adaptive_routing.get("bindings"), list):
                scope_source_bindings = adaptive_routing["bindings"]
            if isinstance(signals.get("route_plan"), dict):
                workspace_lifecycle.apply_signal_route_plan(workspace_routing, signals["route_plan"], payload)
                scope_source_bindings = workspace_routing["bindings"]
            if isinstance(signals.get("verification_aggregation"), dict):
                workspace_routing["verification_aggregation"] = signals["verification_aggregation"]
            scope_bindings = _select_scope_bindings(scope_source_bindings, payload)
            if is_subagent_artifact(payload):
                workspace_lifecycle.note_subagent_artifact(workspace_routing, payload)
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
            retrieval_mode=_context_retrieval_mode(payload),
            max_total_chars=payload.get("max_total_chars"),
        )
        task_state = self.memory_store.get_task_state(resolved_task_id)
        result = {
            "context_pack": context_pack,
            "workspace_routing_review": workspace_lifecycle.routing_review(task_state),
        }
        metadata = task_state.get("metadata") if isinstance(task_state, dict) and isinstance(task_state.get("metadata"), dict) else {}
        result["skill_routing_audit"] = skill_routing_audit.render_skill_audit(
            audit=metadata.get("skill_routing_audit") if isinstance(metadata.get("skill_routing_audit"), dict) else {},
            target="brief",
        )["brief"]
        if payload.get("include_unfinished_tasks") or payload.get("include_unfinished_task_progress"):
            unfinished, markdown = unfinished_task_summary.build_from_hook_payload(payload, self.memory_store)
            result["unfinished_task_summary"] = unfinished
            result["unfinished_task_summary_markdown"] = markdown
        if payload.get("writeback"):
            result["writeback"] = self._write_response_memory(resolved_task_id, payload, task_state)
        return result

    def _write_response_memory(
        self,
        task_id: str | None,
        payload: dict[str, Any],
        task_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        resolved_task_id = task_id or self.memory_store.get_current_task_id() or _default_task_id()
        summary_markdown = _string(payload.get("summary_markdown")) or _string(payload.get("summary"))
        if not summary_markdown:
            state = task_state or self.memory_store.get_task_state(resolved_task_id) or {}
            lines = ["# Response Checkpoint", ""]
            if state.get("objective"):
                lines.append(f"- Objective: {state['objective']}")
            lines.append(f"- Status: {state.get('status', 'open')}")
            summary_markdown = "\n".join(lines)
        summary = self.memory_store.write_task_summary(resolved_task_id, summary_markdown)
        distillation_result = self.distillation_store.distill_task(
            task_id=resolved_task_id,
            queries=payload.get("queries"),
            retrieval_mode=_context_retrieval_mode(payload),
            max_total_chars=int(payload.get("max_total_chars", 2400)),
        )
        return {
            "task_id": resolved_task_id,
            "summary": summary,
            "distillation_result": distillation_result,
            "task_completed": False,
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
            retrieval_mode=_context_retrieval_mode(payload),
            max_total_chars=int(payload.get("max_total_chars", 2400)),
        )
        workspace_memory = self._write_workspace_memory(resolved_task_id, task_state, summary_markdown)
        return {
            "task_state": task_state,
            "summary": summary,
            "distillation_result": distillation_result,
            "workspace_memory": workspace_memory,
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

    def _write_workspace_memory(
        self,
        task_id: str,
        task_state: dict[str, Any],
        summary_markdown: str,
    ) -> dict[str, Any]:
        if os.environ.get("CODEX_WORKSPACE_MEMORY_WRITE_DISABLE") == "1":
            return {"ok": True, "skipped": True, "reason": "disabled by CODEX_WORKSPACE_MEMORY_WRITE_DISABLE"}
        metadata = task_state.get("metadata") if isinstance(task_state.get("metadata"), dict) else {}
        routing = metadata.get("workspace_routing") if isinstance(metadata.get("workspace_routing"), dict) else {}
        route_plan = routing.get("route_plan") if isinstance(routing.get("route_plan"), dict) else {}
        if not route_plan.get("memory_plan"):
            return {"ok": True, "skipped": True, "reason": "no workspace memory plan"}
        try:
            project_root = Path(os.environ.get("CODEX_MEMORY_CWD") or Path.cwd()).resolve()
            return workspace_memory_writer.write_from_route_plan(
                project_root,
                route_plan,
                task_id=task_id,
                summary=summary_markdown,
                confirm=True,
            )
        except Exception as exc:
            return {"ok": False, "degraded": True, "reason": f"{type(exc).__name__}: {exc}"}

def _copy_transient_routing_fields(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    for field in TRANSIENT_ROUTING_FIELDS:
        if field in source:
            target[field] = source[field]
    return target


def _with_transient_routing_fields(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return _copy_transient_routing_fields(source, target)

def _context_retrieval_mode(payload: dict[str, Any]) -> str:
    return _string(payload.get("retrieval_mode")) or _string(os.environ.get("CODEX_MEMORY_RETRIEVAL_MODE")) or "auto"

def _has_routing_signal(payload: dict[str, Any]) -> bool:
    signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
    return isinstance(signals.get("route_plan"), dict) or isinstance(signals.get("verification_aggregation"), dict)


def _has_routing_metadata(payload: dict[str, Any]) -> bool:
    keys = ("acceptance", "acceptance_criteria", "architecture", "architecture_notes", "requirement_sources", "design_docs", "source_docs", "requirements", "rollback", "rollback_plan", "task_intent", "intent")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return any(key in payload or key in metadata for key in keys)


def _without_paths(paths: list[str], excluded: list[str]) -> list[str]:
    excluded_set = set(excluded)
    return [path for path in paths if path not in excluded_set]


def _has_explicit_scope(payload: dict[str, Any]) -> bool:
    return any(_string(payload.get(key)) for key in ("binding_id", "subagent_id", "project_id"))

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
        cleanup_demo_task(args.cleanup_task_id)
        print(json.dumps({"ok": True, "cleaned_task_id": args.cleanup_task_id}, ensure_ascii=False, indent=2))
        return 0

    runner = HookRunner()
    try:
        payload = _load_payload(args.payload_json, args.payload_file)
    except Exception as exc:
        result = runner._degraded_response(args.event, None, {}, exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.strict:
            return 1
        return 0

    result = runner.run_event(args.event, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and result.get("degraded"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
