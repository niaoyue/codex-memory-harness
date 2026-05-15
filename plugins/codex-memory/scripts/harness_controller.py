from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from hook_runner import HookRunner
import openspec_change_scaffold
from sensitive_scan import sanitized_payload
from task_spec import (
    TaskSpec,
    harness_dir,
    load_payload,
    run_state_path,
    safe_id,
    task_dir,
    task_spec_path,
    utc_now,
)


ARTIFACT_CONTEXT_FIELDS = ("dispatch_id", "binding_id", "subagent_id", "project_id", "domain", "assigned_scope")
ROUTING_ARTIFACTS = (
    "route_plan",
    "adaptive_route_plan",
    "subagent_dispatch_plan",
    "adaptive_subagent_dispatch_plan",
    "scope_guard",
    "verification_aggregation",
)


def _project_root(value: str | None) -> Path:
    return Path(value or os.environ.get("CODEX_MEMORY_CWD") or Path.cwd()).resolve()


def _configure_memory(scope: str, project_root: Path) -> None:
    os.environ["CODEX_MEMORY_SCOPE"] = scope
    os.environ["CODEX_MEMORY_CWD"] = str(project_root)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_spec(project_root: Path, task_id: str) -> TaskSpec:
    path = task_spec_path(project_root, task_id)
    if not path.exists():
        raise FileNotFoundError(f"Task spec not found: {path}")
    return TaskSpec.load(path)


def _task_payload(spec: TaskSpec, *, next_step: str = "") -> dict[str, Any]:
    metadata = _deep_merge_dicts(
        spec.metadata,
        {
            "harness_status": spec.status,
            "acceptance": spec.acceptance,
            "verification": spec.verification,
            "risk_level": spec.risk_level,
        },
    )
    return {
        "task_id": spec.task_id,
        "objective": spec.objective,
        "constraints": spec.constraints,
        "working_set": spec.working_set,
        "next_step": next_step,
        "metadata": metadata,
    }


def _merge_hook_metadata(
    project_root: Path,
    spec: TaskSpec,
    state: dict[str, Any],
    hook_result: dict[str, Any],
) -> bool:
    task_state = _hook_task_state(hook_result)
    metadata = task_state.get("metadata") if isinstance(task_state.get("metadata"), dict) else {}
    if not metadata:
        return False
    spec.metadata = _deep_merge_dicts(spec.metadata, metadata)
    state["metadata"] = spec.metadata
    _write_routing_artifacts(project_root, spec.task_id, spec.metadata)
    return True


def _hook_task_state(hook_result: dict[str, Any]) -> dict[str, Any]:
    result = hook_result.get("result") if isinstance(hook_result.get("result"), dict) else {}
    task_state = result.get("task_state") if isinstance(result.get("task_state"), dict) else {}
    return task_state


def _deep_merge_dicts(base: Any, overlay: Any) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base) if isinstance(base, dict) else {}
    if not isinstance(overlay, dict):
        return merged
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


def _write_routing_artifacts(project_root: Path, task_id: str, metadata: dict[str, Any]) -> None:
    routing = metadata.get("workspace_routing") if isinstance(metadata.get("workspace_routing"), dict) else {}
    if not routing:
        return
    target_dir = task_dir(project_root, task_id)
    _write_json(target_dir / "workspace_routing.json", routing)
    for field in ROUTING_ARTIFACTS:
        value = routing.get(field)
        if isinstance(value, dict):
            _write_json(target_dir / f"{field}.json", value)
    bindings = routing.get("bindings")
    if isinstance(bindings, list):
        _write_json(target_dir / "bindings.json", bindings)


def start_task(args: argparse.Namespace) -> dict[str, Any]:
    project_root = _project_root(args.project_root)
    payload = load_payload(args.task_file, args.payload_json)
    payload = sanitized_payload(payload, context="harness_task_spec")
    spec = TaskSpec.from_payload(payload, project_root)
    spec.update_status("scoped")
    openspec_result = openspec_change_scaffold.ensure_for_task(project_root, spec)
    openspec_change_scaffold.apply_to_spec(spec, openspec_result)
    _configure_memory(spec.memory_scope, project_root)

    spec.save(task_spec_path(project_root, spec.task_id))
    state = {
        "task_id": spec.task_id,
        "status": spec.status,
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "project_root": str(project_root),
        "artifacts": [],
        "checklist": _build_checklist(spec),
    }
    _write_json(run_state_path(project_root, spec.task_id), state)
    hook_result = HookRunner().run_event(
        "before_task",
        _task_payload(spec, next_step="进入执行阶段"),
    )
    _merge_hook_metadata(project_root, spec, state, hook_result)
    spec.update_status("context_loaded")
    spec.save(task_spec_path(project_root, spec.task_id))
    state["status"] = spec.status
    state["updated_at"] = utc_now()
    _write_json(run_state_path(project_root, spec.task_id), state)
    return {"task_spec": spec.to_dict(), "run_state": state, "hook_result": hook_result}


def checkpoint_task(args: argparse.Namespace) -> dict[str, Any]:
    project_root = _project_root(args.project_root)
    spec = _load_spec(project_root, args.task_id)
    _configure_memory(spec.memory_scope, project_root)
    payload = load_payload(args.result_file, args.payload_json)
    payload = sanitized_payload(payload, context="harness_checkpoint")
    phase = str(payload.get("phase") or "").strip().lower()

    artifact = {
        "recorded_at": utc_now(),
        "tool_name": payload.get("tool_name") or payload.get("tool") or "tool",
        "summary": payload.get("summary") or payload.get("output") or "Tool checkpoint recorded.",
        "touched_paths": payload.get("touched_paths") or payload.get("files") or [],
        "exit_code": payload.get("exit_code"),
        "phase": phase,
        "signals": payload.get("signals") if isinstance(payload.get("signals"), dict) else {},
    }
    if isinstance(payload.get("_sensitive_scan"), dict):
        artifact["_sensitive_scan"] = payload["_sensitive_scan"]
    for field in ARTIFACT_CONTEXT_FIELDS:
        if field in payload:
            artifact[field] = payload[field]
    artifact_path = task_dir(project_root, spec.task_id) / "artifacts.jsonl"
    _append_jsonl(artifact_path, artifact)

    spec.update_status("verifying" if phase in {"verification", "workspace_verification"} else "executing")
    spec.save(task_spec_path(project_root, spec.task_id))
    state = _load_state(project_root, spec.task_id)
    state["status"] = spec.status
    state["updated_at"] = utc_now()
    state.setdefault("artifacts", []).append(artifact)
    _write_json(run_state_path(project_root, spec.task_id), state)

    hook_payload = {
        "task_id": spec.task_id,
        "tool_name": artifact["tool_name"],
        "summary": artifact["summary"],
        "touched_paths": artifact["touched_paths"],
        "phase": artifact["phase"],
        "signals": artifact["signals"],
        "metadata": spec.metadata,
        "next_step": payload.get("next_step") or "继续执行或进入验证",
    }
    for field in ARTIFACT_CONTEXT_FIELDS:
        if field in artifact:
            hook_payload[field] = artifact[field]
    hook_result = HookRunner().run_event("after_tool", hook_payload)
    _merge_hook_metadata(project_root, spec, state, hook_result)
    spec.save(task_spec_path(project_root, spec.task_id))
    _write_json(run_state_path(project_root, spec.task_id), state)
    return {"task_spec": spec.to_dict(), "artifact": artifact, "hook_result": hook_result}


def complete_task(args: argparse.Namespace) -> dict[str, Any]:
    project_root = _project_root(args.project_root)
    spec = _load_spec(project_root, args.task_id)
    _configure_memory(spec.memory_scope, project_root)
    summary = str(sanitized_payload(_load_summary(args.summary_file, args.summary), context="harness_summary"))
    state = _load_state(project_root, spec.task_id)
    checklist = _complete_checklist(spec, state, bool(summary.strip()))

    spec.update_status("completed")
    spec.save(task_spec_path(project_root, spec.task_id))
    state["status"] = spec.status
    state["updated_at"] = utc_now()
    state["checklist"] = checklist
    _write_json(run_state_path(project_root, spec.task_id), state)

    hook_result = HookRunner().run_event(
        "on_task_complete",
        {
            "task_id": spec.task_id,
            "summary_markdown": summary,
            "next_step": "",
            "queries": [Path(item).name for item in spec.working_set[:3]],
        },
    )
    _merge_hook_metadata(project_root, spec, state, hook_result)
    spec.update_status("distilled")
    spec.save(task_spec_path(project_root, spec.task_id))
    state["status"] = spec.status
    state["updated_at"] = utc_now()
    _write_json(run_state_path(project_root, spec.task_id), state)
    return {"task_spec": spec.to_dict(), "run_state": state, "hook_result": hook_result}


def _load_state(project_root: Path, task_id: str) -> dict[str, Any]:
    path = run_state_path(project_root, task_id)
    if not path.exists():
        return {"task_id": task_id, "artifacts": [], "checklist": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_summary(path: str | None, inline_summary: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return (inline_summary or "").strip()


def _build_checklist(spec: TaskSpec) -> dict[str, bool]:
    return {
        "objective_defined": bool(spec.objective),
        "acceptance_defined": bool(spec.acceptance),
        "verification_defined": bool(spec.verification),
        "memory_scope_selected": spec.memory_scope in {"project", "global", "auto"},
        "summary_written": False,
    }


def _complete_checklist(spec: TaskSpec, state: dict[str, Any], has_summary: bool) -> dict[str, bool]:
    checklist = dict(state.get("checklist") or _build_checklist(spec))
    checklist["artifact_recorded"] = bool(state.get("artifacts"))
    checklist["summary_written"] = has_summary
    checklist["ready_to_distill"] = all(
        checklist.get(key, False)
        for key in ["objective_defined", "memory_scope_selected", "summary_written"]
    )
    return checklist


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Codex Memory harness controller.")
    parser.add_argument("--project-root", help="Project root for project memory and harness files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Create a task spec and load context.")
    start.add_argument("--task-file", help="JSON task spec input.")
    start.add_argument("--payload-json", help="Inline JSON task spec.")

    checkpoint = subparsers.add_parser("checkpoint", help="Record a tool checkpoint.")
    checkpoint.add_argument("--task-id", required=True)
    checkpoint.add_argument("--result-file", help="JSON tool result input.")
    checkpoint.add_argument("--payload-json", help="Inline JSON tool result.")

    complete = subparsers.add_parser("complete", help="Complete and distill a task.")
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--summary-file", help="Markdown summary file.")
    complete.add_argument("--summary", help="Inline markdown summary.")

    args = parser.parse_args()
    if args.command == "start":
        result = start_task(args)
    elif args.command == "checkpoint":
        result = checkpoint_task(args)
    elif args.command == "complete":
        result = complete_task(args)
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
