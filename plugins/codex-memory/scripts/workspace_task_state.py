from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any

import init_storage
import workspace_binding_enforcement

REGISTRY_ENV = "CODEX_MEMORY_WORKTREE_REGISTRY"
ACTIVE_STATUSES = {"active"}


def stored_task_route_plan(project_root: Path, task_id: str, *, session_id: str = "") -> dict[str, Any]:
    for root in _candidate_storage_roots(project_root, task_id, session_id):
        route_plan = _read_task_route_plan(root, task_id)
        if route_plan:
            return route_plan
    return {}


def _candidate_storage_roots(project_root: Path, task_id: str, session_id: str) -> list[Path]:
    requested_root = project_root.resolve(strict=False)
    project_key = _git_project_key(requested_root)
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        normalized = path.expanduser().resolve(strict=False)
        key = str(normalized).casefold()
        if key not in seen:
            seen.add(key)
            candidates.append(normalized)

    env_cwd = os.environ.get("CODEX_MEMORY_CWD", "").strip()
    if env_cwd:
        env_root = Path(env_cwd)
        if _matches_project(env_root, requested_root, project_key):
            add(env_root)

    if project_key:
        bindings = _active_registry_bindings(project_key)
        matching = [
            item
            for item in bindings
            if item.get("task_id") == task_id and (not session_id or item.get("session_id") == session_id)
        ]
        for item in [*matching, *[binding for binding in bindings if binding not in matching]]:
            root = str(item.get("project_root") or "").strip()
            if root:
                add(Path(root))

    add(requested_root)
    return candidates


def _read_task_route_plan(project_root: Path, task_id: str) -> dict[str, Any]:
    try:
        paths = init_storage.resolve_storage_paths(cwd=project_root)
        if not paths.db_path.exists():
            return {}
        with closing(sqlite3.connect(paths.db_path)) as conn:
            row = conn.execute(
                "SELECT payload_json FROM task_state WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return {}
        state = json.loads(str(row[0]))
    except (OSError, sqlite3.Error, json.JSONDecodeError):
        return {}
    metadata = state.get("metadata") if isinstance(state, dict) and isinstance(state.get("metadata"), dict) else {}
    routing = metadata.get("workspace_routing") if isinstance(metadata.get("workspace_routing"), dict) else {}
    return workspace_binding_enforcement.current_route_plan(routing)


def _matches_project(candidate: Path, requested_root: Path, project_key: str) -> bool:
    if candidate.expanduser().resolve(strict=False) == requested_root:
        return True
    return bool(project_key) and _git_project_key(candidate) == project_key


def _active_registry_bindings(project_key: str) -> list[dict[str, Any]]:
    source = _registry_path()
    if not source.exists():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        binding_id = str(record.get("binding_id") or "")
        if binding_id:
            latest[binding_id] = record
    return [
        item
        for item in latest.values()
        if item.get("project_key") == project_key and item.get("status") in ACTIVE_STATUSES
    ]


def _registry_path() -> Path:
    configured = os.environ.get(REGISTRY_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return _codex_home() / "codex-memory-harness" / "worktrees" / "registry.jsonl"


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    memory_home = os.environ.get("CODEX_MEMORY_HOME", "").strip()
    home = Path(memory_home).expanduser() if memory_home else Path.home()
    return home / ".codex"


def _git_project_key(cwd: Path) -> str:
    common_dir = _git_common_dir(cwd)
    if not common_dir:
        return ""
    return hashlib.sha1(f"git:{common_dir}".encode("utf-8")).hexdigest()


def _git_common_dir(cwd: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return str(Path(completed.stdout.strip()).resolve(strict=False))
