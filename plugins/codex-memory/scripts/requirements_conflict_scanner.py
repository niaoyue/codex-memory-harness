from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import requirements_gate_schema


CONFLICT_MARKER = re.compile(
    r"^\s*(?:[-*]\s*)?"
    r"(CONFLICT|SPEC CONFLICT|IMPLEMENTATION MISMATCH|SPEC MISMATCH)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
CHANGE_DOCS = ("proposal.md", "design.md", "tasks.md")


def scan(
    project_root: Path,
    *,
    task: dict[str, Any] | None = None,
    change_id: str = "",
) -> dict[str, Any]:
    task = task or {}
    conflicts = task_conflicts(task)
    if change_id:
        conflicts.extend(openspec_conflicts(project_root, change_id))
    gate = requirements_gate_schema.build_result(
        task=task,
        task_intent=str(task.get("task_intent") or task.get("intent") or "system_change"),
        status="blocked_by_conflict" if conflicts else "passed",
        blocking=bool(conflicts),
        requirement_sources=requirement_sources(task, change_id),
        missing=[],
        open_questions=[],
    )
    if conflicts:
        gate["logical_conflicts"] = _unique(gate.get("logical_conflicts", []) + [item["summary"] for item in conflicts])
        gate["implementation_spec_mismatches"] = _unique(
            gate.get("implementation_spec_mismatches", [])
            + [item["summary"] for item in conflicts if item["kind"] == "implementation_spec_mismatch"]
        )
    return {
        "version": 1,
        "ok": not conflicts,
        "status": "passed" if not conflicts else "blocked_by_conflict",
        "change_id": change_id,
        "conflicts": conflicts,
        "requirements_gate": gate,
    }


def task_conflicts(task: dict[str, Any]) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    for key, kind in (
        ("logical_conflicts", "logical_conflict"),
        ("implementation_spec_mismatches", "implementation_spec_mismatch"),
        ("conflict_evidence", "logical_conflict"),
    ):
        for value in string_list(task.get(key)):
            conflicts.append({"kind": kind, "source": f"task.{key}", "summary": value})
    return conflicts


def openspec_conflicts(project_root: Path, change_id: str) -> list[dict[str, str]]:
    change_dir = project_root / "openspec" / "changes" / change_id
    conflicts: list[dict[str, str]] = []
    for name in CHANGE_DOCS:
        path = change_dir / name
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = CONFLICT_MARKER.match(line)
            if not match:
                continue
            label = match.group(1).lower()
            kind = "implementation_spec_mismatch" if "mismatch" in label else "logical_conflict"
            conflicts.append(
                {
                    "kind": kind,
                    "source": f"openspec/changes/{change_id}/{name}:{line_number}",
                    "summary": match.group(2).strip(),
                }
            )
    return conflicts


def requirement_sources(task: dict[str, Any], change_id: str) -> list[str]:
    sources = string_list(task.get("requirement_sources"))
    if change_id:
        sources.append(f"openspec/changes/{change_id}")
    return _unique(sources)


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan explicit requirement/spec conflict evidence.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--task-file")
    parser.add_argument("--change", default="")
    args = parser.parse_args()
    task: dict[str, Any] = {}
    if args.task_file:
        value = json.loads(Path(args.task_file).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("task-file must contain a JSON object.")
        task = value
    result = scan(Path(args.project_root).resolve(), task=task, change_id=args.change)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
