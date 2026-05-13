from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import init_storage
from memory_store import MemoryStore
from sensitive_scan import sanitized_payload
from task_spec import task_dir, task_spec_path


UNFINISHED_STATUSES = {"todo", "doing", "blocked", "open", "in_progress", "executing", "verifying"}
UNKNOWN = "unknown"
DEFAULT_TASK_LIST_PATHS = (
    Path(".codex/specs/backlog-governance/tasks.md"),
    Path("docs/codex-memory-plugin-task-list.md"),
)
PROGRESS_SNAPSHOT_KEYS = {
    "status",
    "recent_checkpoint_or_update",
    "completed_acceptance",
    "remaining_acceptance",
    "blockers",
    "next_step",
    "evidence_sources",
}


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
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [text for item in value if (text := _string(item))]
    return [_string(value)] if _string(value) else []


def _unknown_if_empty(items: list[str]) -> list[str]:
    return items if items else [UNKNOWN]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s`*_]+", "", value).lower()


def _candidate_task_list_paths(project_root: Path, task_list_path: Path | None) -> list[Path]:
    if task_list_path:
        return [task_list_path if task_list_path.is_absolute() else project_root / task_list_path]
    return [project_root / path for path in DEFAULT_TASK_LIST_PATHS]


def parse_task_list(path: Path) -> tuple[list[dict[str, str]], dict[str, str], list[str]]:
    warnings: list[str] = []
    if not path.exists():
        return [], {}, [f"task list not found: {path}"]
    lines = path.read_text(encoding="utf-8").splitlines()
    tasks: list[dict[str, str]] = []
    step_by_task: dict[str, str] = {}
    headers: list[str] = []
    header_map: dict[str, int] = {}
    saw_task_table = False

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = _split_table_row(stripped)
            normalized = [_normalize_header(cell) for cell in cells]
            if "id" in normalized and ("状态" in normalized or "status" in normalized):
                headers = normalized
                header_map = {name: pos for pos, name in enumerate(headers)}
                saw_task_table = True
                continue
            if set(normalized) <= {"", "---", ":---", "---:", ":---:"}:
                continue
            if not header_map or len(cells) < len(header_map):
                continue
            task_id = cells[header_map.get("id", 0)].strip("` ")
            status_pos = header_map.get("状态", header_map.get("status", len(cells) - 1))
            status = cells[status_pos].lower()
            if not task_id or status not in UNFINISHED_STATUSES:
                continue
            title = cells[header_map.get("任务", header_map.get("task", 2 if len(cells) > 2 else 0))]
            output = cells[header_map.get("产出物", header_map.get("output", 3 if len(cells) > 3 else status_pos))]
            deps = cells[header_map.get("依赖", header_map.get("dependencies", 4 if len(cells) > 4 else status_pos))]
            tasks.append(
                {
                    "task_id": task_id,
                    "title": title,
                    "status": status,
                    "output": output,
                    "dependencies": deps,
                    "line": str(index),
                }
            )
            continue

        step_match = re.search(r"(Step\s+\d+[^：:]*[：:]\s*.*?(T\d+).*?)$", stripped)
        if step_match:
            step_by_task[step_match.group(2)] = step_match.group(1)

    if not saw_task_table:
        warnings.append(f"task list has no task table: {path}")
    return tasks, step_by_task, warnings


def _parse_default_task_list(candidates: list[Path]) -> tuple[Path, list[dict[str, str]], dict[str, str], list[str]]:
    warnings: list[str] = []
    fallback: tuple[Path, list[dict[str, str]], dict[str, str], list[str]] | None = None
    for index, candidate in enumerate(candidates):
        rows, step_by_task, candidate_warnings = parse_task_list(candidate)
        has_no_table = any("has no task table" in warning for warning in candidate_warnings)
        if candidate.exists() and not has_no_table:
            warnings.extend(candidate_warnings)
            return candidate, rows, step_by_task, warnings
        warnings.extend(candidate_warnings)
        if index == 0:
            fallback = (candidate, rows, step_by_task, candidate_warnings)
    if fallback:
        selected, rows, step_by_task, _ = fallback
    else:
        selected, rows, step_by_task = candidates[0], [], {}
    return selected, rows, step_by_task, list(dict.fromkeys(warnings))


def _parse_progress_snapshots(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    snapshots: dict[str, dict[str, str]] = {}
    current_task_id = ""
    for line in lines:
        stripped = line.strip()
        heading = re.match(r"^#{2,6}\s+(T\d+)\b", stripped)
        if heading:
            current_task_id = heading.group(1)
            snapshots.setdefault(current_task_id, {})
            continue
        if not current_task_id or not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        normalized_key = key.strip().lower()
        if normalized_key in PROGRESS_SNAPSHOT_KEYS:
            snapshots[current_task_id][normalized_key] = value.strip()
    return snapshots


def _latest_artifact(project_root: Path, task_id: str) -> dict[str, Any]:
    artifacts = _read_jsonl(task_dir(project_root, task_id) / "artifacts.jsonl")
    if not artifacts:
        return {}
    return max(artifacts, key=lambda item: _string(item.get("recorded_at")))


def _state_exists(state: dict[str, Any] | None) -> bool:
    return bool(state and (state.get("updated_at") or state.get("objective") or state.get("recent_findings")))


def _project_memory_store(project_root: Path) -> MemoryStore:
    paths = init_storage.ensure_storage_layout(scope="project", cwd=project_root)
    return MemoryStore(db_path=Path(paths["db_path"]))


def _safe_list(value: Any) -> list[str]:
    return _string_list(sanitized_payload(value, context="unfinished_task_summary"))


def build_unfinished_task_summary(
    *,
    project_root: Path | str,
    task_list_path: Path | str | None = None,
    store: MemoryStore | None = None,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    selected_ids = {item for item in (task_ids or []) if item}
    candidate_task_lists = _candidate_task_list_paths(root, Path(task_list_path) if task_list_path else None)
    resolved_task_list, rows, step_by_task, warnings = _parse_default_task_list(candidate_task_lists)
    progress_snapshots = _parse_progress_snapshots(resolved_task_list)
    if selected_ids:
        rows = [row for row in rows if row["task_id"] in selected_ids]
    memory = store or _project_memory_store(root)
    tasks = [
        _build_task_progress(
            root,
            resolved_task_list,
            row,
            step_by_task.get(row["task_id"], ""),
            memory,
            progress_snapshots.get(row["task_id"], {}),
        )
        for row in rows
    ]
    return {
        "task_list_path": str(resolved_task_list),
        "task_list_candidates": [str(path) for path in candidate_task_lists],
        "tasks": tasks,
        "warnings": warnings,
    }


def _build_task_progress(
    project_root: Path,
    task_list: Path,
    row: dict[str, str],
    step_text: str,
    store: MemoryStore,
    progress_snapshot: dict[str, str],
) -> dict[str, Any]:
    task_id = row["task_id"]
    state = store.get_task_state(task_id)
    summary = store.get_task_summary(task_id)
    spec = _read_json(task_spec_path(project_root, task_id))
    run_state = _read_json(task_dir(project_root, task_id) / "run_state.json")
    artifact = _latest_artifact(project_root, task_id)
    evidence = [f"task_list:{task_list}:{row['line']}"]

    if _state_exists(state):
        evidence.append(f"task_state:{task_id}")
    if summary:
        evidence.append(f"task_summary:{task_id}")
    if spec:
        evidence.append(f"harness_task_spec:{task_id}")
    if run_state:
        evidence.append(f"harness_run_state:{task_id}")
    if artifact:
        evidence.append(f"harness_artifact:{task_id}")
    if progress_snapshot:
        evidence.append(f"progress_snapshot:{task_list}:{row['line']}")
        evidence.extend(_safe_list(progress_snapshot.get("evidence_sources")))

    recent = (
        _string(artifact.get("recorded_at"))
        or _string(run_state.get("updated_at"))
        or _string(state.get("updated_at") if state else "")
        or _string(summary.get("updated_at") if summary else "")
        or _string(progress_snapshot.get("recent_checkpoint_or_update"))
        or UNKNOWN
    )
    recent_findings = _safe_list((state or {}).get("recent_findings"))[:5]
    if not recent_findings and artifact:
        recent_findings = _safe_list(artifact.get("summary"))[:3]
    if not recent_findings:
        recent_findings = _safe_list(progress_snapshot.get("completed_acceptance"))
    completed = _unknown_if_empty(recent_findings)

    metadata = (state or {}).get("metadata") if isinstance((state or {}).get("metadata"), dict) else {}
    remaining = (
        _safe_list((spec or {}).get("acceptance"))
        or _safe_list(metadata.get("acceptance"))
        or _safe_list(progress_snapshot.get("remaining_acceptance"))
    )
    if not remaining:
        output = row.get("output") or row.get("title")
        if step_text:
            remaining = [f"{output}; {step_text}"]
        elif output:
            remaining = [output]
    remaining = _unknown_if_empty(remaining)

    blockers = _safe_list((state or {}).get("open_questions")) or _safe_list(progress_snapshot.get("blockers"))
    if not blockers and row["status"] == "blocked" and row.get("output"):
        blockers = blockers + [row["output"]]
    blockers = _unknown_if_empty(blockers)

    next_step = _string((state or {}).get("next_step")) or _string(progress_snapshot.get("next_step")) or step_text or UNKNOWN
    return {
        "task_id": task_id,
        "title": row.get("title") or UNKNOWN,
        "status": row["status"],
        "recent_checkpoint_or_update": recent,
        "completed_acceptance": completed,
        "remaining_acceptance": remaining,
        "blockers": blockers,
        "next_step": next_step,
        "evidence_sources": evidence,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Unfinished Task Progress Summary", ""]
    tasks = summary.get("tasks") if isinstance(summary.get("tasks"), list) else []
    warnings = _string_list(summary.get("warnings"))
    if warnings:
        lines.append("## Warnings")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    if not tasks:
        lines.append("No unfinished tasks found.")
        return "\n".join(lines)
    for task in tasks:
        lines.append(f"## {task.get('task_id', UNKNOWN)} - {task.get('title', UNKNOWN)}")
        lines.append(f"- status: {task.get('status', UNKNOWN)}")
        lines.append(f"- recent_checkpoint_or_update: {task.get('recent_checkpoint_or_update', UNKNOWN)}")
        lines.append(f"- completed_acceptance: {'; '.join(_string_list(task.get('completed_acceptance'))) or UNKNOWN}")
        lines.append(f"- remaining_acceptance: {'; '.join(_string_list(task.get('remaining_acceptance'))) or UNKNOWN}")
        lines.append(f"- blockers: {'; '.join(_string_list(task.get('blockers'))) or UNKNOWN}")
        lines.append(f"- next_step: {task.get('next_step') or UNKNOWN}")
        lines.append(f"- evidence_sources: {'; '.join(_string_list(task.get('evidence_sources'))) or UNKNOWN}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_from_hook_payload(payload: dict[str, Any], store: MemoryStore) -> tuple[dict[str, Any], str]:
    project_root = Path(os.environ.get("CODEX_MEMORY_CWD") or Path.cwd()).resolve()
    task_list_path = _string(payload.get("task_list_path"))
    summary = build_unfinished_task_summary(
        project_root=project_root,
        task_list_path=Path(task_list_path) if task_list_path else None,
        store=store,
        task_ids=_string_list(payload.get("unfinished_task_ids")),
    )
    return summary, render_markdown(summary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an unfinished task progress summary.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--task-list", default="")
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()
    summary = build_unfinished_task_summary(
        project_root=Path(args.project_root).resolve(),
        task_list_path=Path(args.task_list) if args.task_list else None,
        task_ids=args.task_id,
    )
    if args.format == "markdown":
        print(render_markdown(summary))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
