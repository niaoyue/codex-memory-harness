from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import workspace_binding_enforcement
import workspace_task_state
from workspace_session_cleanup import build_cleanup_report, build_prune_plan, execute_prune_confirm, execute_recover_binding
from workspace_session_lock import acquire_registry_lock as acquire_lock
from workspace_session_lock import release_registry_lock

REGISTRY_ENV = "CODEX_MEMORY_WORKTREE_REGISTRY"
ACTIVE_STATUSES = {"active"}

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def safe_id(value: str, fallback: str = "item") -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip().lower()).strip("-._")
    if len(normalized) > 64:
        normalized = f"{normalized[:55].rstrip('-._')}-{short_id(value)}"
    return normalized or fallback
def git_ref_component(value: str, fallback: str = "item") -> str:
    component = re.sub(r"\.+", ".", safe_id(value, fallback)).strip(".")
    component = re.sub(r"\.lock$", "-lock", component)
    return component[:64].strip(".-") or fallback
def short_id(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:8]
def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    memory_home = os.environ.get("CODEX_MEMORY_HOME", "").strip()
    home = Path(memory_home).expanduser() if memory_home else Path.home()
    return home / ".codex"

def registry_path() -> Path:
    configured = os.environ.get(REGISTRY_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return codex_home() / "codex-memory-harness" / "worktrees" / "registry.jsonl"
def acquire_registry_lock(path: Path | None = None) -> Path:
    return acquire_lock(path or registry_path(), utc_now())
def run_git(cwd: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if check and completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "git command failed").strip())
    return completed

def git_text(cwd: Path, args: list[str]) -> str:
    return run_git(cwd, args).stdout.strip()

def git_root(cwd: Path) -> Path:
    return Path(git_text(cwd, ["rev-parse", "--show-toplevel"])).resolve()

def project_info(cwd: Path) -> dict[str, str]:
    root = git_root(cwd)
    common_dir = git_text(root, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    head = git_text(root, ["rev-parse", "HEAD"])
    remote = run_git(root, ["remote", "get-url", "origin"], check=False).stdout.strip()
    key_basis = f"git:{Path(common_dir).resolve()}"
    remote_summary = f"sha1:{hashlib.sha1(remote.encode('utf-8')).hexdigest()}" if remote else ""
    return {
        "project_key": hashlib.sha1(key_basis.encode("utf-8")).hexdigest(),
        "project_root": str(root),
        "git_common_dir": str(Path(common_dir).resolve()),
        "head": head,
        "remote": remote_summary,
    }

def dirty_paths(root: Path) -> list[str]:
    output = run_git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]).stdout
    paths: list[str] = []
    records = [record for record in output.split("\0") if record]
    skip_next = False
    for record in records:
        if skip_next:
            skip_next = False
            continue
        path = record[3:] if len(record) > 3 else record
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if record[:1] in {"R", "C"}:
            skip_next = True
        paths.append(path.replace("\\", "/"))
    return paths

def managed_binding_can_release(binding: dict[str, Any]) -> bool:
    path = Path(str(binding.get("effective_cwd", "")))
    try:
        if dirty_paths(path):
            return False
        if binding.get("worktree_kind") != "managed":
            return True
        head = run_git(path, ["rev-parse", "HEAD"], check=False).stdout.strip()
    except (OSError, RuntimeError):
        return False
    return bool(head) and head == binding.get("base_head")

def read_records(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or registry_path()
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records

def append_record(record: dict[str, Any], path: Path | None = None) -> None:
    target = path or registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

def latest_bindings(path: Path | None = None) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in read_records(path):
        binding_id = str(record.get("binding_id") or "")
        if not binding_id:
            continue
        latest[binding_id] = record
    return list(latest.values())

def active_bindings(project_key: str, *, path: Path | None = None) -> list[dict[str, Any]]:
    return [
        item
        for item in latest_bindings(path)
        if item.get("project_key") == project_key and item.get("status") in ACTIVE_STATUSES
    ]
def find_existing_binding(
    bindings: list[dict[str, Any]],
    *,
    session_id: str,
    task_id: str,
    mode: str,
) -> dict[str, Any] | None:
    return next(
        (
            binding
            for binding in bindings
            if binding.get("session_id") == session_id
            and binding.get("task_id") == task_id
            and binding.get("mode") == mode
        ),
        None,
    )

def managed_worktree_path(root: Path, task_id: str, session_id: str) -> Path:
    return root.parent / ".codex-worktrees" / root.name / f"{safe_id(task_id, 'task')}-{short_id(task_id)}-{short_id(session_id)}"

def managed_branch(task_id: str, session_id: str) -> str:
    return f"codex/{git_ref_component(task_id, 'task')}-{short_id(task_id)}/{short_id(session_id)}"

def ensure_managed_worktree(root: Path, task_id: str, session_id: str, base_head: str, anchor_root: Path | None = None) -> tuple[Path, str]:
    path = managed_worktree_path(anchor_root or root, task_id, session_id)
    branch = managed_branch(task_id, session_id)
    if path.exists():
        actual_root = run_git(path, ["rev-parse", "--show-toplevel"], check=False).stdout.strip()
        actual_branch = run_git(path, ["branch", "--show-current"], check=False).stdout.strip()
        if Path(actual_root).resolve(strict=False) != path.resolve(strict=False) or actual_branch != branch:
            raise RuntimeError(f"managed worktree path exists but is not the expected worktree: {path}")
        if dirty_paths(path) or run_git(path, ["rev-parse", "HEAD"], check=False).stdout.strip() != base_head:
            raise RuntimeError(f"managed worktree path exists but is not clean at the expected base head: {path}")
        return path.resolve(), branch

    path.parent.mkdir(parents=True, exist_ok=True)
    branch_exists = run_git(root, ["show-ref", "--verify", f"refs/heads/{branch}"], check=False).returncode == 0
    if branch_exists:
        if run_git(root, ["rev-parse", branch], check=False).stdout.strip() != base_head:
            raise RuntimeError(f"managed branch exists but is not at the expected base head: {branch}")
        run_git(root, ["worktree", "add", str(path), branch])
    else:
        run_git(root, ["worktree", "add", "-b", branch, str(path), base_head])
    return path.resolve(), branch

def binding_record(
    *,
    info: dict[str, str],
    session_id: str,
    task_id: str,
    mode: str,
    effective_cwd: Path,
    worktree_kind: str,
    branch: str,
    dirty_snapshot: list[str],
    reason: str,
) -> dict[str, Any]:
    now = utc_now()
    binding_id = f"bind-{short_id(info['project_key'])}-{safe_id(task_id, 'task')}-{short_id(task_id)}-{short_id(session_id)}-{worktree_kind}"
    return {
        "version": 1,
        "binding_id": binding_id,
        "project_key": info["project_key"],
        "session_id": session_id,
        "task_id": task_id,
        "mode": mode,
        "status": "active",
        "project_root": info["project_root"],
        "git_common_dir": info["git_common_dir"],
        "base_head": info["head"],
        "remote": info.get("remote", ""),
        "effective_cwd": str(effective_cwd),
        "worktree_kind": worktree_kind,
        "branch": branch,
        "dirty_snapshot": dirty_snapshot,
        "reason": reason,
        "created_at": now,
        "updated_at": now,
        "heartbeat_at": now,
    }


def bind_session(
    project_root: Path,
    *,
    session_id: str,
    task_id: str,
    mode: str = "write",
) -> dict[str, Any]:
    root = git_root(project_root)
    info = project_info(root)
    lock_path = acquire_registry_lock()
    try:
        active = active_bindings(info["project_key"])
        active_write = [item for item in active if item.get("mode") == "write"]
        existing = find_existing_binding(active, session_id=session_id, task_id=task_id, mode=mode)
        existing_write = find_existing_binding(active_write, session_id=session_id, task_id=task_id, mode="write")
        if mode == "read" and existing_write:
            return {"ok": True, "action": "reuse_binding", "binding": existing_write}
        same_session_writers = [
            item for item in active_write if item.get("session_id") == session_id and item.get("task_id") != task_id
        ]
        if mode == "write" and same_session_writers:
            return {
                "ok": False,
                "action": "release_existing_write_binding_required",
                "reason": "same session already has an active write binding for another task",
                "conflicts": same_session_writers,
            }
        if existing and not (mode == "write" and existing.get("worktree_kind") == "managed"):
            return {"ok": True, "action": "reuse_binding", "binding": existing}
        dirty = dirty_paths(root)
        other_writers = [
            item for item in active_write if item.get("binding_id") != (existing or {}).get("binding_id")
        ]
        if existing:
            if Path(str(existing.get("effective_cwd", ""))).resolve(strict=False) == root.resolve(strict=False) or dirty or other_writers:
                return {"ok": True, "action": "reuse_binding", "binding": existing}
            if not managed_binding_can_release(existing):
                return {"ok": True, "action": "reuse_binding", "binding": existing}
            released = dict(existing, status="released", updated_at=utc_now(), reason="primary checkout is free")
            append_record(released)

        if mode == "read":
            binding = binding_record(
                info=info,
                session_id=session_id,
                task_id=task_id,
                mode=mode,
                effective_cwd=root,
                worktree_kind="primary",
                branch="",
                dirty_snapshot=dirty,
                reason="read binding uses current checkout",
            )
            append_record(binding)
            return {"ok": True, "action": "bind_primary", "binding": binding}

        if dirty or other_writers:
            path, branch = ensure_managed_worktree(root, task_id, session_id, info["head"], Path(info["git_common_dir"]).parent)
            reasons = []
            if dirty:
                reasons.append("current checkout has dirty changes without this session binding")
            if other_writers:
                reasons.append("another active write session exists for this project")
            binding = binding_record(
                info=info,
                session_id=session_id,
                task_id=task_id,
                mode=mode,
                effective_cwd=path,
                worktree_kind="managed",
                branch=branch,
                dirty_snapshot=dirty,
                reason="; ".join(reasons),
            )
            append_record(binding)
            return {"ok": True, "action": "bind_managed_worktree", "binding": binding}

        branch = git_text(root, ["branch", "--show-current"])
        binding = binding_record(
            info=info,
            session_id=session_id,
            task_id=task_id,
            mode=mode,
            effective_cwd=root,
            worktree_kind="primary",
            branch=branch,
            dirty_snapshot=[],
            reason="primary checkout is clean and no other active write session exists",
        )
        append_record(binding)
        return {"ok": True, "action": "bind_primary", "binding": binding}
    finally:
        release_registry_lock(lock_path)

def path_outside_effective_cwd(path: str, effective_cwd: Path) -> bool:
    candidate = Path(path)
    base = effective_cwd.resolve(strict=False)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        candidate.resolve(strict=False).relative_to(base)
        return False
    except ValueError:
        return True


def write_guard(
    project_root: Path,
    *,
    session_id: str,
    task_id: str,
    intended_paths: list[str] | None = None,
    route_plan: dict[str, Any] | None = None,
    requirements_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_route_plan = route_plan or workspace_task_state.stored_task_route_plan(
        project_root,
        task_id,
        session_id=session_id,
    )
    enforcement = requirements_gate_write_enforcement(current_route_plan, requirements_gate)
    if enforcement:
        return {
            "ok": False,
            "action": "requirements_gate_blocked",
            "reason": enforcement["reason"],
            "requirements_gate_enforcement": enforcement,
        }
    binding_result = bind_session(project_root, session_id=session_id, task_id=task_id, mode="write")
    if not binding_result.get("ok", True):
        return binding_result
    binding = binding_result["binding"]
    current_root = git_root(project_root).resolve()
    effective_cwd = Path(str(binding["effective_cwd"])).resolve(strict=False)

    if current_root != effective_cwd:
        return {
            "ok": False,
            "action": "switch_to_effective_cwd",
            "reason": binding.get("reason") or "writes must use the bound effective cwd",
            "effective_cwd": str(effective_cwd),
            "binding": binding,
        }

    outside = [path for path in intended_paths or [] if path_outside_effective_cwd(path, effective_cwd)]
    if outside:
        if binding_result.get("action") != "reuse_binding":
            binding = update_binding(str(binding["binding_id"]), "released")
        return {
            "ok": False,
            "action": "path_outside_effective_cwd",
            "reason": "one or more intended paths are outside the effective cwd",
            "effective_cwd": str(effective_cwd),
            "binding": binding,
            "violations": outside,
        }

    return {
        "ok": True,
        "action": "allow_write",
        "reason": "current checkout matches the active write binding",
        "effective_cwd": str(effective_cwd),
        "binding": binding,
    }


def requirements_gate_write_enforcement(
    route_plan: dict[str, Any] | None = None,
    requirements_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = dict(route_plan) if isinstance(route_plan, dict) else {}
    if requirements_gate is not None:
        plan["requirements_gate"] = requirements_gate
    return workspace_binding_enforcement.requirements_write_enforcement(plan)


def update_binding(binding_id: str, status: str) -> dict[str, Any]:
    lock_path = acquire_registry_lock()
    try:
        binding = next((item for item in latest_bindings() if item.get("binding_id") == binding_id), None)
        if not binding:
            raise ValueError(f"binding not found: {binding_id}")
        if status == "active" and binding.get("status") not in ACTIVE_STATUSES:
            return binding
        if status == "released" and binding.get("mode") == "write" and not managed_binding_can_release(binding):
            status = "released_dirty"
        updated = dict(binding)
        updated["status"] = status
        updated["updated_at"] = utc_now()
        if status == "active":
            updated["heartbeat_at"] = updated["updated_at"]
        append_record(updated)
        return updated
    finally:
        release_registry_lock(lock_path)


def compact_status(project_root: Path) -> dict[str, Any]:
    info = project_info(project_root)
    bindings = active_bindings(info["project_key"])
    return {
        "ok": True,
        "project_key": info["project_key"],
        "project_root": info["project_root"],
        "registry_path": str(registry_path()),
        "active_bindings": bindings,
    }


def project_bindings(project_root: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    info = project_info(project_root)
    return info, [item for item in latest_bindings() if item.get("project_key") == info["project_key"]]


def worktree_status(project_root: Path) -> dict[str, Any]:
    info, bindings = project_bindings(project_root)
    return build_cleanup_report(info, bindings, registry_path())


def worktree_prune_plan(project_root: Path) -> dict[str, Any]:
    info, bindings = project_bindings(project_root)
    return build_prune_plan(info, bindings, registry_path())


def worktree_prune_confirm(project_root: Path) -> dict[str, Any]:
    lock_path = acquire_registry_lock()
    try:
        info, bindings = project_bindings(project_root)
        return execute_prune_confirm(info, bindings, registry_path(), append_record)
    finally:
        release_registry_lock(lock_path)


def worktree_recover(project_root: Path, binding_id: str) -> dict[str, Any]:
    lock_path = acquire_registry_lock()
    try:
        info, bindings = project_bindings(project_root)
        return execute_recover_binding(info, bindings, registry_path(), binding_id, append_record)
    finally:
        release_registry_lock(lock_path)


def main(argv: list[str] | None = None) -> int:
    from workspace_session_cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
