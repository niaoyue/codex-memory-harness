from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from context_builder import CONTEXT_PACK_SCHEMA, ContextBuilder
from distillation_store import (
    DISTILLED_ASSET_SCHEMA,
    DISTILLATION_RESULT_SCHEMA,
    DistillationStore,
)
from memory_store import MemoryStore, TASK_STATE_SCHEMA
from retrieval_store import EVIDENCE_PACK_SCHEMA, RETRIEVAL_MODES, RetrievalEngine


STORE = MemoryStore()
RETRIEVAL = RetrievalEngine()
CONTEXT_BUILDER = ContextBuilder(STORE, RETRIEVAL)
DISTILLATION = DistillationStore(STORE, CONTEXT_BUILDER)


def resource_specs() -> list[dict[str, Any]]:
    return [
        {"uri": "memory://schema/task-state", "name": "Task State Schema", "description": "The canonical schema for Codex task state records.", "mimeType": "application/json"},
        {"uri": "memory://schema/evidence-pack", "name": "Evidence Pack Schema", "description": "The canonical schema for retrieval evidence packs.", "mimeType": "application/json"},
        {"uri": "memory://schema/context-pack", "name": "Context Pack Schema", "description": "The canonical schema for context packs.", "mimeType": "application/json"},
        {"uri": "memory://schema/distilled-asset", "name": "Distilled Asset Schema", "description": "The canonical schema for distilled assets.", "mimeType": "application/json"},
        {"uri": "memory://schema/distillation-result", "name": "Distillation Result Schema", "description": "The canonical schema for distillation results.", "mimeType": "application/json"},
        {"uri": "memory://task/current", "name": "Current Task State", "description": "The current task state snapshot.", "mimeType": "application/json"},
        {"uri": "memory://task/current/summary", "name": "Current Task Summary", "description": "The latest summary for the current task.", "mimeType": "text/markdown"},
        {"uri": "memory://repo/decisions", "name": "Repo Decisions", "description": "Recent project decisions captured by the memory plugin.", "mimeType": "application/json"},
        {"uri": "memory://retrieval/modes", "name": "Retrieval Modes", "description": "Supported retrieval modes for the local MVP.", "mimeType": "application/json"},
        {"uri": "memory://distilled/assets", "name": "Distilled Assets", "description": "Recent distilled assets captured by the plugin.", "mimeType": "application/json"},
    ]


def tool_specs() -> list[dict[str, Any]]:
    return [
        _tool("memory.search_evidence", "Search the local workspace with exact, full-text, auto, or semantic-placeholder mode.", {"query": {"type": "string"}, "mode": _mode_schema(), "limit": {"type": "integer"}}, ["query"]),
        _tool("memory.build_context_pack", "Build a grouped context pack from task state, summary, decisions, and evidence.", _context_args()),
        _tool("memory.distill_task", "Distill the current task into a reusable asset and write it to storage/distilled.", _distill_args()),
        _tool("memory.list_distilled_assets", "List recent distilled assets, optionally filtered by task_id.", _list_args()),
        _tool("memory.get_distilled_asset", "Read a distilled asset by asset_id or the latest asset for a task.", {"asset_id": {"type": "integer"}, "task_id": {"type": "string"}}),
        _tool("memory.get_task_state", "Read a task state by task_id or fall back to the current task.", {"task_id": {"type": "string"}}),
        _tool("memory.upsert_task_state", "Create or update a task state and optionally mark it current.", _task_state_args(), ["task_id"]),
        _tool("memory.list_repo_decisions", "List recent repo decisions, optionally filtered by task_id.", _list_args()),
        _tool("memory.write_repo_decision", "Write a project decision into the memory store.", {"task_id": {"type": "string"}, "title": {"type": "string"}, "details": {"type": "string"}}, ["title", "details"]),
        _tool("memory.get_task_summary", "Read a task summary by task_id or fall back to the current task.", {"task_id": {"type": "string"}}),
        _tool("memory.write_task_summary", "Write a markdown summary for a task and persist it to storage.", {"task_id": {"type": "string"}, "summary_markdown": {"type": "string"}}, ["task_id", "summary_markdown"]),
    ]


def resource_payload(uri: str) -> tuple[str, str]:
    schema_payloads = {
        "memory://schema/task-state": TASK_STATE_SCHEMA,
        "memory://schema/evidence-pack": EVIDENCE_PACK_SCHEMA,
        "memory://schema/context-pack": CONTEXT_PACK_SCHEMA,
        "memory://schema/distilled-asset": DISTILLED_ASSET_SCHEMA,
        "memory://schema/distillation-result": DISTILLATION_RESULT_SCHEMA,
    }
    if uri in schema_payloads:
        return json.dumps(schema_payloads[uri], ensure_ascii=False, indent=2), "application/json"
    if uri == "memory://repo/decisions":
        return _json({"items": STORE.list_repo_decisions(limit=20)}), "application/json"
    if uri == "memory://retrieval/modes":
        return _json(RETRIEVAL_MODES), "application/json"
    if uri == "memory://distilled/assets":
        return _json({"items": DISTILLATION.list_distilled_assets(limit=20)}), "application/json"
    if uri == "memory://task/current":
        return _json(STORE.get_task_state() or {}), "application/json"
    if uri == "memory://task/current/summary":
        return (STORE.get_task_summary() or {}).get("summary_markdown", ""), "text/markdown"
    if uri.startswith("memory://task/") and uri.endswith("/summary"):
        task_id = uri[len("memory://task/") : -len("/summary")]
        return (STORE.get_task_summary(task_id) or {}).get("summary_markdown", ""), "text/markdown"
    if uri.startswith("memory://task/"):
        return _json(STORE.get_task_state(uri[len("memory://task/") :]) or {}), "application/json"
    raise ValueError(f"Unknown resource URI: {uri}")


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handlers = {
        "memory.search_evidence": _search_evidence,
        "memory.build_context_pack": _build_context_pack,
        "memory.distill_task": _distill_task,
        "memory.list_distilled_assets": _list_distilled_assets,
        "memory.get_distilled_asset": _get_distilled_asset,
        "memory.get_task_state": lambda args: {"task_state": STORE.get_task_state(args.get("task_id"))},
        "memory.upsert_task_state": _upsert_task_state,
        "memory.list_repo_decisions": _list_repo_decisions,
        "memory.write_repo_decision": _write_repo_decision,
        "memory.get_task_summary": lambda args: {"summary": STORE.get_task_summary(args.get("task_id"))},
        "memory.write_task_summary": lambda args: {"summary": STORE.write_task_summary(args["task_id"], args["summary_markdown"])},
    }
    if name not in handlers:
        raise ValueError(f"Unknown tool: {name}")
    return _tool_result(handlers[name](arguments))


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return {"name": name, "description": description, "inputSchema": schema}


def _mode_schema() -> dict[str, Any]:
    return {"type": "string", "enum": ["auto", "exact", "fulltext", "semantic"]}


def _queries_schema() -> dict[str, Any]:
    return {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}


def _context_args() -> dict[str, Any]:
    return {"task_id": {"type": "string"}, "queries": _queries_schema(), "retrieval_mode": _mode_schema(), "evidence_limit_per_query": {"type": "integer"}, "max_total_chars": {"type": "integer"}, "decision_limit": {"type": "integer"}}


def _distill_args() -> dict[str, Any]:
    args = _context_args()
    args["asset_type"] = {"type": "string"}
    return args


def _list_args() -> dict[str, Any]:
    return {"task_id": {"type": "string"}, "limit": {"type": "integer"}}


def _task_state_args() -> dict[str, Any]:
    return {"task_id": {"type": "string"}, "objective": {"type": "string"}, "status": {"type": "string"}, "constraints": {"type": "array", "items": {"type": "string"}}, "decisions": {"type": "array", "items": {"type": "string"}}, "open_questions": {"type": "array", "items": {"type": "string"}}, "working_set": {"type": "array", "items": {"type": "string"}}, "recent_findings": {"type": "array", "items": {"type": "string"}}, "next_step": {"type": "string"}, "metadata": {"type": "object"}, "set_current": {"type": "boolean"}}


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_result(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _json(payload)}], "structuredContent": payload}


def _search_evidence(args: dict[str, Any]) -> dict[str, Any]:
    return {"evidence_pack": RETRIEVAL.search(args["query"], mode=str(args.get("mode", "auto")), limit=int(args.get("limit", 10)))}


def _build_context_pack(args: dict[str, Any]) -> dict[str, Any]:
    return {"context_pack": CONTEXT_BUILDER.build_context_pack(task_id=args.get("task_id"), queries=args.get("queries"), retrieval_mode=str(args.get("retrieval_mode", "auto")), evidence_limit_per_query=int(args.get("evidence_limit_per_query", 4)), max_total_chars=args.get("max_total_chars"), decision_limit=int(args.get("decision_limit", 8)))}


def _distill_task(args: dict[str, Any]) -> dict[str, Any]:
    return {"distillation_result": DISTILLATION.distill_task(task_id=args.get("task_id"), queries=args.get("queries"), retrieval_mode=str(args.get("retrieval_mode", "auto")), max_total_chars=int(args.get("max_total_chars", 2400)), asset_type=str(args.get("asset_type", "task_pattern")), decision_limit=int(args.get("decision_limit", 8)))}


def _list_distilled_assets(args: dict[str, Any]) -> dict[str, Any]:
    return {"items": DISTILLATION.list_distilled_assets(task_id=args.get("task_id"), limit=int(args.get("limit", 20)))}


def _get_distilled_asset(args: dict[str, Any]) -> dict[str, Any]:
    return {"asset": DISTILLATION.get_distilled_asset(asset_id=args.get("asset_id"), task_id=args.get("task_id"))}


def _upsert_task_state(args: dict[str, Any]) -> dict[str, Any]:
    task_id = str(args["task_id"]).strip()
    payload = {key: value for key, value in args.items() if key != "set_current"}
    return {"task_state": STORE.upsert_task_state(task_id, payload, set_current=bool(args.get("set_current", True)))}


def _list_repo_decisions(args: dict[str, Any]) -> dict[str, Any]:
    return {"items": STORE.list_repo_decisions(task_id=args.get("task_id"), limit=int(args.get("limit", 20)))}


def _write_repo_decision(args: dict[str, Any]) -> dict[str, Any]:
    return {"decision": STORE.write_repo_decision(args["title"], args["details"], task_id=args.get("task_id"))}
