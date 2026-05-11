from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIVE_STALE_SECONDS = 30 * 60
SUSPENDED_STALE_SECONDS = 24 * 60 * 60


def build_cleanup_report(
    project_info: dict[str, str],
    bindings: list[dict[str, Any]],
    registry_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    inspected = [inspect_binding(binding, now=now) for binding in bindings]
    return {
        "ok": True,
        "project_key": project_info["project_key"],
        "project_root": project_info["project_root"],
        "registry_path": str(registry_path),
        "bindings": inspected,
        "active_bindings": [item for item in inspected if item["computed_status"] == "active"],
        "stale_bindings": [item for item in inspected if item["computed_status"] == "stale"],
        "dirty_orphans": [item for item in inspected if item["cleanup_state"] == "dirty_orphan"],
        "prunable": [item for item in inspected if item["cleanup_state"] == "prunable"],
        "pruned_bindings": [item for item in inspected if item["cleanup_state"] == "pruned"],
        "needs_user_review": [
            item for item in inspected if item["cleanup_state"] in {"dirty_orphan", "needs_user_review"}
        ],
    }


def build_prune_plan(
    project_info: dict[str, str],
    bindings: list[dict[str, Any]],
    registry_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    report = build_cleanup_report(project_info, bindings, registry_path, now=now)
    candidates = report["prunable"]
    return {
        "ok": True,
        "dry_run": True,
        "project_key": report["project_key"],
        "project_root": report["project_root"],
        "registry_path": report["registry_path"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "blocked": [
            item for item in report["bindings"]
            if item["worktree_kind"] == "managed" and item["cleanup_state"] not in {"prunable", "pruned"}
        ],
    }


def execute_prune_confirm(
    project_info: dict[str, str],
    bindings: list[dict[str, Any]],
    registry_path: Path,
    record_pruned: Callable[[dict[str, Any]], None],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    report = build_cleanup_report(project_info, bindings, registry_path, now=now)
    latest_by_id = {str(binding.get("binding_id") or ""): binding for binding in bindings}
    timestamp = format_timestamp(now)
    pruned: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    blocked = [
        item for item in report["bindings"]
        if item["worktree_kind"] == "managed" and item["cleanup_state"] not in {"prunable", "pruned"}
    ]
    candidates: list[dict[str, Any]] = []

    for candidate in report["prunable"]:
        guard = validate_prune_candidate(project_info, candidate)
        if guard["ok"]:
            candidates.append({**candidate, "prune_guard": guard})
        else:
            blocked.append({**candidate, "prune_guard": guard})

    for candidate in candidates:
        guard = candidate["prune_guard"]
        binding_id = str(candidate["binding_id"])
        raw = latest_by_id.get(binding_id)
        if raw is None:
            failed.append({**candidate, "error": "binding vanished before prune"})
            break
        try:
            run_git(Path(project_info["project_root"]), ["worktree", "remove", guard["path"]])
            updated = dict(raw)
            updated["status"] = "pruned"
            updated["updated_at"] = timestamp
            updated["pruned_at"] = timestamp
            updated["reason"] = "managed worktree pruned after explicit confirm"
            record_pruned(updated)
            pruned.append({**candidate, "status_after": "pruned"})
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            failed.append({**candidate, "error": str(exc)})
            break

    return {
        "ok": not failed,
        "dry_run": False,
        "project_key": report["project_key"],
        "project_root": report["project_root"],
        "registry_path": report["registry_path"],
        "candidate_count": len(candidates),
        "pruned_count": len(pruned),
        "pruned": pruned,
        "blocked": blocked,
        "failed": failed,
    }


def execute_recover_binding(
    project_info: dict[str, str],
    bindings: list[dict[str, Any]],
    registry_path: Path,
    binding_id: str,
    record_recovered: Callable[[dict[str, Any]], None],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    report = build_cleanup_report(project_info, bindings, registry_path, now=now)
    target = next((item for item in report["bindings"] if item["binding_id"] == binding_id), None)
    latest_by_id = {str(binding.get("binding_id") or ""): binding for binding in bindings}
    if target is None:
        return {
            "ok": False,
            "action": "binding_not_found",
            "binding_id": binding_id,
            "project_key": report["project_key"],
            "project_root": report["project_root"],
            "registry_path": report["registry_path"],
            "error": "binding is not registered for this project",
        }
    if target["cleanup_state"] == "pruned":
        return {
            "ok": False,
            "action": "cannot_recover_pruned",
            "binding": target,
            "error": "binding is already pruned and cannot be recovered automatically",
        }
    if target["computed_status"] == "active" and target["cleanup_state"] == "active":
        return {
            "ok": True,
            "action": "already_active",
            "binding": target,
            "effective_cwd": target["effective_cwd"],
        }

    guard = validate_recover_candidate(project_info, target)
    if not guard["ok"]:
        return {
            "ok": False,
            "action": recover_block_action(target),
            "binding": target,
            "recover_guard": guard,
            "error": "binding requires manual review before recovery",
        }

    raw = latest_by_id.get(binding_id)
    if raw is None:
        return {
            "ok": False,
            "action": "binding_not_found",
            "binding_id": binding_id,
            "error": "binding vanished before recovery",
        }
    timestamp = format_timestamp(now)
    updated = dict(raw)
    updated["status"] = "active"
    updated["updated_at"] = timestamp
    updated["heartbeat_at"] = timestamp
    updated["reason"] = "managed worktree recovered after explicit recover command"
    record_recovered(updated)
    return {
        "ok": True,
        "action": "recovered",
        "binding": target,
        "recover_guard": guard,
        "recovered_binding": updated,
        "effective_cwd": updated["effective_cwd"],
    }


def inspect_binding(binding: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    git_state = inspect_worktree(binding)
    stale = binding_is_stale(binding, now=now)
    computed_status = "stale" if stale else str(binding.get("status") or "unknown")
    cleanup_state = classify_cleanup_state(binding, git_state, stale=stale)
    return {
        "binding_id": binding.get("binding_id", ""),
        "session_id": binding.get("session_id", ""),
        "task_id": binding.get("task_id", ""),
        "mode": binding.get("mode", ""),
        "status": binding.get("status", ""),
        "computed_status": computed_status,
        "cleanup_state": cleanup_state,
        "worktree_kind": binding.get("worktree_kind", ""),
        "effective_cwd": binding.get("effective_cwd", ""),
        "branch": binding.get("branch", ""),
        "base_head": binding.get("base_head", ""),
        "heartbeat_at": binding.get("heartbeat_at", ""),
        "updated_at": binding.get("updated_at", ""),
        "reason": cleanup_reason(binding, git_state, stale=stale, cleanup_state=cleanup_state),
        "git": git_state,
    }


def classify_cleanup_state(binding: dict[str, Any], git_state: dict[str, Any], *, stale: bool) -> str:
    status = str(binding.get("status") or "")
    if binding.get("worktree_kind") != "managed":
        return "stale" if stale else "not_managed"
    if status == "pruned":
        return "pruned"
    if status == "released" and git_state.get("clean_at_base"):
        return "prunable"
    if stale and not git_state.get("clean_at_base"):
        return "dirty_orphan"
    if stale:
        return "stale"
    if status in {"released_dirty", "orphaned_dirty"}:
        return "needs_user_review"
    if status == "released":
        return "needs_user_review"
    return "active"


def cleanup_reason(
    binding: dict[str, Any],
    git_state: dict[str, Any],
    *,
    stale: bool,
    cleanup_state: str,
) -> str:
    if cleanup_state == "prunable":
        return "managed worktree is released, clean, and still at the recorded base head"
    if cleanup_state == "dirty_orphan":
        return "binding is stale and the managed worktree is dirty, missing, or no longer at base head"
    if cleanup_state == "stale":
        return "binding heartbeat exceeded the stale threshold"
    if cleanup_state == "needs_user_review":
        if git_state.get("dirty_paths"):
            return "managed worktree has dirty paths and needs user review"
        if git_state.get("head") and not git_state.get("base_head_matches"):
            return "managed worktree branch is ahead or no longer at the recorded base head"
        return "managed worktree is not safe to prune automatically"
    if cleanup_state == "pruned":
        return "managed worktree was already pruned"
    if binding.get("worktree_kind") != "managed":
        return "primary checkout bindings are never pruned"
    if stale:
        return "binding heartbeat exceeded the stale threshold"
    return "binding is still active"


def recover_block_action(candidate: dict[str, Any]) -> str:
    cleanup_state = str(candidate.get("cleanup_state") or "")
    if cleanup_state in {"dirty_orphan", "needs_user_review"}:
        return "needs_user_review"
    if candidate.get("worktree_kind") != "managed":
        return "not_managed"
    return "not_recoverable"


def validate_recover_candidate(project_info: dict[str, str], candidate: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    git_state = candidate.get("git") if isinstance(candidate.get("git"), dict) else {}
    cleanup_state = str(candidate.get("cleanup_state") or "")
    raw_path = str(candidate.get("effective_cwd") or git_state.get("path") or "")
    path = Path(raw_path)

    if cleanup_state not in {"stale", "prunable"}:
        errors.append("cleanup_state is not recoverable")
    if candidate.get("worktree_kind") != "managed":
        errors.append("binding is not a managed worktree")
    if not raw_path:
        errors.append("effective_cwd is empty")
    if not git_state.get("exists"):
        errors.append("worktree path does not exist")
    if not git_state.get("is_git_worktree"):
        errors.append("path is not a git worktree")
    if not git_state.get("status_ok"):
        errors.append("git status did not complete successfully")
    if git_state.get("dirty_paths"):
        errors.append("worktree has dirty paths")
    if not git_state.get("base_head_matches"):
        errors.append("worktree HEAD does not match the recorded base head")

    managed_root = managed_worktree_root(project_info)
    resolved_path = path.resolve(strict=False)
    resolved_managed_root = managed_root.resolve(strict=False)
    if not path.is_absolute():
        errors.append("effective_cwd must be absolute")
    if resolved_path == resolved_managed_root:
        errors.append("refusing to recover the managed worktree container")
    try:
        resolved_path.relative_to(resolved_managed_root)
    except ValueError:
        errors.append("effective_cwd is outside the managed worktree container")

    return {
        "ok": not errors,
        "errors": errors,
        "path": str(resolved_path),
        "managed_root": str(resolved_managed_root),
    }


def validate_prune_candidate(project_info: dict[str, str], candidate: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    git_state = candidate.get("git") if isinstance(candidate.get("git"), dict) else {}
    raw_path = str(candidate.get("effective_cwd") or git_state.get("path") or "")
    path = Path(raw_path)
    if candidate.get("cleanup_state") != "prunable":
        errors.append("cleanup_state is not prunable")
    if candidate.get("worktree_kind") != "managed":
        errors.append("binding is not a managed worktree")
    if not raw_path:
        errors.append("effective_cwd is empty")
    if not git_state.get("exists"):
        errors.append("worktree path does not exist")
    if not git_state.get("is_git_worktree"):
        errors.append("path is not a git worktree")
    if not git_state.get("status_ok"):
        errors.append("git status did not complete successfully")
    if not git_state.get("clean_at_base"):
        errors.append("worktree is not clean at the recorded base head")

    managed_root = managed_worktree_root(project_info)
    resolved_path = path.resolve(strict=False)
    resolved_managed_root = managed_root.resolve(strict=False)
    project_root = Path(project_info["project_root"]).resolve(strict=False)
    if not path.is_absolute():
        errors.append("effective_cwd must be absolute")
    if resolved_path == project_root:
        errors.append("refusing to prune the project root")
    if resolved_path == resolved_managed_root:
        errors.append("refusing to prune the managed worktree container")
    try:
        resolved_path.relative_to(resolved_managed_root)
    except ValueError:
        errors.append("effective_cwd is outside the managed worktree container")

    return {
        "ok": not errors,
        "errors": errors,
        "path": str(resolved_path),
        "managed_root": str(resolved_managed_root),
    }


def managed_worktree_root(project_info: dict[str, str]) -> Path:
    git_common_dir = str(project_info.get("git_common_dir") or "").strip()
    anchor = Path(git_common_dir).parent if git_common_dir else Path(project_info["project_root"])
    return anchor.parent / ".codex-worktrees" / anchor.name


def format_timestamp(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def inspect_worktree(binding: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(binding.get("effective_cwd") or ""))
    state: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_git_worktree": False,
        "status_ok": False,
        "status_error": "",
        "dirty_paths": [],
        "head": "",
        "base_head_matches": False,
        "clean_at_base": False,
    }
    if not state["exists"]:
        return state
    state["is_git_worktree"] = run_git(path, ["rev-parse", "--is-inside-work-tree"], check=False).returncode == 0
    if not state["is_git_worktree"]:
        return state
    status = dirty_paths(path)
    state["status_ok"] = status["ok"]
    state["status_error"] = status["error"]
    state["dirty_paths"] = status["paths"]
    state["head"] = run_git(path, ["rev-parse", "HEAD"], check=False).stdout.strip()
    state["base_head_matches"] = bool(state["head"]) and state["head"] == binding.get("base_head")
    state["clean_at_base"] = state["status_ok"] and not state["dirty_paths"] and state["base_head_matches"]
    return state


def binding_is_stale(binding: dict[str, Any], *, now: datetime | None = None) -> bool:
    status = str(binding.get("status") or "")
    if status == "active":
        limit = ACTIVE_STALE_SECONDS
        timestamp = parse_timestamp(str(binding.get("heartbeat_at") or binding.get("updated_at") or ""))
    elif status == "suspended":
        limit = SUSPENDED_STALE_SECONDS
        timestamp = parse_timestamp(str(binding.get("updated_at") or ""))
    else:
        return False
    if timestamp is None:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - timestamp).total_seconds() > limit


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def dirty_paths(root: Path) -> dict[str, Any]:
    completed = run_git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], check=False)
    if completed.returncode != 0:
        return {
            "ok": False,
            "error": (completed.stderr or completed.stdout or "git status failed").strip(),
            "paths": [],
        }
    output = completed.stdout
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
    return {"ok": True, "error": "", "paths": paths}


def run_git(cwd: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    if check and completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "git command failed").strip())
    return completed
