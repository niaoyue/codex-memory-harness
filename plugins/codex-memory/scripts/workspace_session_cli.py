from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import workspace_binding_enforcement
import workspace_session


def print_json(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok", True) else 2


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--task-id", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Codex workspace session worktree bindings.")
    parser.add_argument("--project-root", default=".", help="Git checkout used to resolve the project.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    session = subparsers.add_parser("session", help="Manage session bindings.")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    status = session_sub.add_parser("status", help="Show active bindings for the current project.")
    status.set_defaults(func=cmd_status)
    bind = session_sub.add_parser("bind", help="Create or reuse a read/write binding.")
    add_common_args(bind)
    bind.add_argument("--mode", choices=["read", "write"], default="write")
    bind.set_defaults(func=cmd_bind)
    heartbeat = session_sub.add_parser("heartbeat", help="Refresh a binding heartbeat.")
    heartbeat.add_argument("--binding-id", required=True)
    heartbeat.set_defaults(func=cmd_heartbeat)
    release = session_sub.add_parser("release", help="Release a binding without deleting worktrees.")
    release.add_argument("--binding-id", required=True)
    release.set_defaults(func=cmd_release)

    guard = subparsers.add_parser("write-guard", help="Check whether a write may run in this checkout.")
    add_common_args(guard)
    guard.add_argument("--path", action="append", default=[], help="Intended write path; may be repeated.")
    guard.add_argument("--route-plan-file", help="Route plan JSON used for requirements gate enforcement.")
    guard.add_argument("--requirements-gate-file", help="Requirements gate JSON used for write enforcement.")
    guard.set_defaults(func=cmd_write_guard)

    worktree = subparsers.add_parser("worktree", help="Inspect managed worktree bindings.")
    worktree_sub = worktree.add_subparsers(dest="worktree_command", required=True)
    list_cmd = worktree_sub.add_parser("list", help="List bindings and cleanup state for the current project.")
    list_cmd.set_defaults(func=cmd_worktree_list)
    prune_cmd = worktree_sub.add_parser("prune", help="Prune released clean managed worktrees.")
    prune_cmd.add_argument("--dry-run", action="store_true", help="Only report candidates; do not delete worktrees.")
    prune_cmd.add_argument("--confirm", action="store_true", help="Remove safe candidates after re-validating guards.")
    prune_cmd.set_defaults(func=cmd_worktree_prune)
    recover_cmd = worktree_sub.add_parser("recover", help="Recover a safe managed worktree binding.")
    recover_cmd.add_argument("binding_id")
    recover_cmd.set_defaults(func=cmd_worktree_recover)
    return parser


def cmd_status(args: argparse.Namespace) -> int:
    return print_json(workspace_session.compact_status(Path(args.project_root)))


def cmd_bind(args: argparse.Namespace) -> int:
    return print_json(
        workspace_session.bind_session(
            Path(args.project_root),
            session_id=args.session_id,
            task_id=args.task_id,
            mode=args.mode,
        )
    )


def cmd_write_guard(args: argparse.Namespace) -> int:
    return print_json(
        workspace_session.write_guard(
            Path(args.project_root),
            session_id=args.session_id,
            task_id=args.task_id,
            intended_paths=list(args.path),
            route_plan=load_route_plan(args.route_plan_file),
            requirements_gate=load_json(args.requirements_gate_file),
        )
    )


def cmd_heartbeat(args: argparse.Namespace) -> int:
    binding = workspace_session.update_binding(args.binding_id, "active")
    ok = binding.get("status") == "active"
    return print_json({"ok": ok, "binding": binding, **({} if ok else {"error": "binding is not active"})})


def cmd_release(args: argparse.Namespace) -> int:
    return print_json({"ok": True, "binding": workspace_session.update_binding(args.binding_id, "released")})


def cmd_worktree_list(args: argparse.Namespace) -> int:
    return print_json(workspace_session.worktree_status(Path(args.project_root)))


def cmd_worktree_prune(args: argparse.Namespace) -> int:
    if args.dry_run and args.confirm:
        return print_json({"ok": False, "error": "choose only one of --dry-run or --confirm"})
    if args.dry_run:
        return print_json(workspace_session.worktree_prune_plan(Path(args.project_root)))
    if args.confirm:
        return print_json(workspace_session.worktree_prune_confirm(Path(args.project_root)))
    return print_json({"ok": False, "error": "worktree prune requires --dry-run or --confirm"})


def cmd_worktree_recover(args: argparse.Namespace) -> int:
    return print_json(workspace_session.worktree_recover(Path(args.project_root), args.binding_id))


def load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def load_route_plan(path: str | None) -> dict[str, Any] | None:
    value = load_json(path)
    return workspace_binding_enforcement.current_route_plan(value)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as exc:
        return print_json({"ok": False, "error": str(exc)})
