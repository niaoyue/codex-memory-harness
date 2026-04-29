from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import init_storage
from memory_store import MemoryStore
from sensitive_scan import sanitize_for_persistence, sanitized_payload


SHARED_DIRS = {
    "decision": "decisions",
    "fact": "facts",
    "workflow": "workflows",
    "route": "routes",
}
REQUIRED_FRONT_MATTER = ("id", "scope", "status", "confidence", "source", "updated_at")
VALID_STATUS = {"proposed", "accepted", "deprecated"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_SCOPE = {"workspace", "project", "module", "workflow"}
SHARED_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WORKSPACE_SCOPED_KINDS = {"route"}


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _project_root(value: str | None) -> Path:
    start = Path(value or os.environ.get("CODEX_MEMORY_CWD") or Path.cwd()).resolve()
    paths = init_storage.resolve_storage_paths(scope="project", cwd=start)
    return paths.project_root or start


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return normalized[:96] or f"shared-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def shared_root(project_root: Path) -> Path:
    return project_root / ".codex" / "shared"


def ensure_shared_layout(project_root: Path) -> Path:
    root = shared_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    for directory in SHARED_DIRS.values():
        (root / directory).mkdir(parents=True, exist_ok=True)
    index = root / "index.json"
    if not index.exists():
        _write_json(index, {"version": 1, "entries": []})
    return root


def promote_task(
    project_root: Path,
    task_id: str,
    *,
    kind: str = "fact",
    title: str | None = None,
    status: str = "proposed",
    confidence: str = "medium",
    overwrite: bool = False,
) -> dict[str, Any]:
    if kind not in SHARED_DIRS:
        raise ValueError(f"Unsupported shared memory kind: {kind}")
    if status not in VALID_STATUS:
        raise ValueError(f"Unsupported status: {status}")
    if confidence not in VALID_CONFIDENCE:
        raise ValueError(f"Unsupported confidence: {confidence}")

    old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
    old_cwd = os.environ.get("CODEX_MEMORY_CWD")
    try:
        os.environ["CODEX_MEMORY_SCOPE"] = "project"
        os.environ["CODEX_MEMORY_CWD"] = str(project_root)
        init_storage.ensure_storage_layout(scope="project", cwd=project_root)
        store = MemoryStore()
        summary = store.get_task_summary(task_id)
        decisions = store.list_repo_decisions(task_id=task_id, limit=20)
    finally:
        _restore_env("CODEX_MEMORY_SCOPE", old_scope)
        _restore_env("CODEX_MEMORY_CWD", old_cwd)
    if summary is None and not decisions:
        raise FileNotFoundError(f"No task summary or decisions found for task_id: {task_id}")

    resolved_title = _sanitize_title(title or _title_from_summary(summary, task_id))
    entry_id = _safe_id(f"{_utc_date()}-{kind}-{resolved_title}")
    folder = SHARED_DIRS[kind]
    path = ensure_shared_layout(project_root) / folder / f"{entry_id}.md"
    if path.exists() and not overwrite:
        raise FileExistsError(f"Shared memory entry already exists: {path}")

    markdown = _render_entry(
        entry_id=entry_id,
        title=resolved_title,
        kind=kind,
        status=status,
        confidence=confidence,
        source=f"task:{task_id}",
        task_id=task_id,
        summary=summary,
        decisions=decisions,
    )
    safe_markdown = str(sanitized_payload(markdown, context="shared_memory_promote"))
    path.write_text(safe_markdown, encoding="utf-8")
    index = rebuild_index(project_root)
    return {"ok": True, "path": str(path), "entry_id": entry_id, "index": index}


def validate_shared(project_root: Path) -> dict[str, Any]:
    root = ensure_shared_layout(project_root)
    failures: list[dict[str, str]] = []
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8")
        metadata = _parse_front_matter(text)
        failures.extend(_validate_metadata(path, metadata))
        scan = sanitize_for_persistence(text)
        if scan.findings:
            failures.append({"path": str(path), "error": "sensitive content detected"})
        entries.append(_index_entry(root, path, metadata))
    return {"ok": not failures, "failures": failures, "entries": entries}


def rebuild_index(project_root: Path) -> dict[str, Any]:
    root = ensure_shared_layout(project_root)
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        metadata = _parse_front_matter(path.read_text(encoding="utf-8"))
        entries.append(_index_entry(root, path, metadata))
    payload = {"version": 1, "updated_at": _utc_date(), "entries": entries}
    _write_json(root / "index.json", payload)
    return payload


def _title_from_summary(summary: dict[str, Any] | None, task_id: str) -> str:
    if summary and summary.get("summary_markdown"):
        for line in str(summary["summary_markdown"]).splitlines():
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                return cleaned[:80]
    return task_id


def _sanitize_title(value: str) -> str:
    result = sanitize_for_persistence(value)
    if result.blocked:
        categories = ", ".join(result.report()["categories"])
        raise ValueError(f"Blocked sensitive content before persisting shared memory title: {categories}")
    return str(result.value).strip() or "shared-memory-entry"


def _front_matter_value(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _scope_for_kind(kind: str) -> str:
    if kind == "workflow":
        return "workflow"
    if kind in WORKSPACE_SCOPED_KINDS:
        return "workspace"
    return "project"


def _render_entry(
    *,
    entry_id: str,
    title: str,
    kind: str,
    status: str,
    confidence: str,
    source: str,
    task_id: str,
    summary: dict[str, Any] | None,
    decisions: list[dict[str, Any]],
) -> str:
    scope = _scope_for_kind(kind)
    lines = [
        "---",
        f"id: {_front_matter_value(entry_id)}",
        f"scope: {_front_matter_value(scope)}",
        f"project_id: {_front_matter_value('project')}",
        f"domain: {_front_matter_value(kind)}",
        f"status: {_front_matter_value(status)}",
        f"confidence: {_front_matter_value(confidence)}",
        f"source: {_front_matter_value(source)}",
        'supersedes: ""',
        f"updated_at: {_front_matter_value(_utc_date())}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    if summary and summary.get("summary_markdown"):
        lines.extend(["## Summary", str(summary["summary_markdown"]).strip(), ""])
    if decisions:
        lines.append("## Decisions")
        for item in decisions:
            lines.append(f"- {item.get('title', '')}: {item.get('details', '')}")
        lines.append("")
    lines.extend(["## Source Task", f"- `{task_id}`", ""])
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


def _parse_front_matter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata


def _validate_metadata(path: Path, metadata: dict[str, str]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for key in REQUIRED_FRONT_MATTER:
        if not metadata.get(key):
            failures.append({"path": str(path), "error": f"missing front matter: {key}"})
    if metadata.get("scope") and metadata["scope"] not in VALID_SCOPE:
        failures.append({"path": str(path), "error": "invalid scope"})
    if metadata.get("id") and not SHARED_ID_RE.fullmatch(metadata["id"]):
        failures.append({"path": str(path), "error": "invalid id"})
    if metadata.get("status") and metadata["status"] not in VALID_STATUS:
        failures.append({"path": str(path), "error": "invalid status"})
    if metadata.get("confidence") and metadata["confidence"] not in VALID_CONFIDENCE:
        failures.append({"path": str(path), "error": "invalid confidence"})
    if metadata.get("updated_at") and not DATE_RE.fullmatch(metadata["updated_at"]):
        failures.append({"path": str(path), "error": "invalid updated_at"})
    return failures


def _index_entry(root: Path, path: Path, metadata: dict[str, str]) -> dict[str, Any]:
    return sanitized_payload(
        {
            "id": metadata.get("id") or _safe_id(path.stem),
            "path": path.relative_to(root).as_posix(),
            "scope": metadata.get("scope", ""),
            "project_id": metadata.get("project_id", ""),
            "domain": metadata.get("domain", ""),
            "status": metadata.get("status", ""),
            "confidence": metadata.get("confidence", ""),
            "updated_at": metadata.get("updated_at", ""),
        },
        context="shared_memory_index",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = sanitized_payload(payload, context="shared_memory_index")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage project shared Codex memory.")
    parser.add_argument("--project-root", help="Project root containing .codex/shared.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote = subparsers.add_parser("promote", help="Promote a task summary to .codex/shared.")
    promote.add_argument("--task-id", required=True)
    promote.add_argument("--kind", choices=sorted(SHARED_DIRS), default="fact")
    promote.add_argument("--title")
    promote.add_argument("--status", choices=sorted(VALID_STATUS), default="proposed")
    promote.add_argument("--confidence", choices=sorted(VALID_CONFIDENCE), default="medium")
    promote.add_argument("--overwrite", action="store_true")

    shared = subparsers.add_parser("shared", help="Validate or rebuild shared memory.")
    shared_sub = shared.add_subparsers(dest="shared_command", required=True)
    shared_sub.add_parser("validate", help="Validate .codex/shared Markdown entries.")
    index = shared_sub.add_parser("index", help="Manage .codex/shared/index.json.")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("rebuild", help="Rebuild .codex/shared/index.json.")

    args = parser.parse_args()
    project_root = _project_root(args.project_root)
    if args.command == "promote":
        result = promote_task(
            project_root,
            args.task_id,
            kind=args.kind,
            title=args.title,
            status=args.status,
            confidence=args.confidence,
            overwrite=args.overwrite,
        )
    elif args.command == "shared" and args.shared_command == "validate":
        result = validate_shared(project_root)
    elif args.command == "shared" and args.shared_command == "index" and args.index_command == "rebuild":
        result = rebuild_index(project_root)
    else:
        raise ValueError("Unsupported shared memory command.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
