from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_workspace_session import _info, session_env, temp_registry, write_text, workspace_session
import workspace_session_cli
import workspace_session_cleanup


OLD_HEARTBEAT = "2000-01-01T00:00:00+00:00"


class WorkspaceSessionCleanupTests(unittest.TestCase):
    def test_confirm_prunes_released_clean_managed_worktree(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "primary-dirty.txt", "dirty\n")
            result = workspace_session.write_guard(repo, session_id="confirm", task_id="confirm-task")
            managed = Path(result["effective_cwd"])
            released = workspace_session.update_binding(result["binding"]["binding_id"], "released")

            report = workspace_session.worktree_status(repo)
            plan = workspace_session.worktree_prune_plan(repo)
            managed_exists_after_plan = managed.exists()
            prune = workspace_session.worktree_prune_confirm(repo)
            latest = {
                item["binding_id"]: item
                for item in workspace_session.latest_bindings()
            }
            follow_up_plan = workspace_session.worktree_prune_plan(repo)

        self.assertEqual(released["status"], "released")
        self.assertEqual([item["binding_id"] for item in report["prunable"]], [released["binding_id"]])
        self.assertEqual(plan["candidate_count"], 1)
        self.assertEqual(plan["candidates"][0]["cleanup_state"], "prunable")
        self.assertTrue(managed_exists_after_plan, "dry-run cleanup must not delete the worktree")
        self.assertTrue(prune["ok"], prune)
        self.assertFalse(prune["dry_run"])
        self.assertEqual(prune["pruned_count"], 1)
        self.assertEqual(prune["pruned"][0]["binding_id"], released["binding_id"])
        self.assertFalse(managed.exists(), "confirmed cleanup should remove the managed worktree")
        self.assertEqual(latest[released["binding_id"]]["status"], "pruned")
        self.assertEqual(follow_up_plan["candidate_count"], 0)

    def test_recover_released_clean_managed_worktree(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "primary-dirty.txt", "dirty\n")
            result = workspace_session.write_guard(repo, session_id="recover", task_id="recover-task")
            released = workspace_session.update_binding(result["binding"]["binding_id"], "released")

            recovered = workspace_session.worktree_recover(repo, released["binding_id"])
            latest = {
                item["binding_id"]: item
                for item in workspace_session.latest_bindings()
            }

        self.assertTrue(recovered["ok"], recovered)
        self.assertEqual(recovered["action"], "recovered")
        self.assertEqual(recovered["effective_cwd"], released["effective_cwd"])
        self.assertEqual(latest[released["binding_id"]]["status"], "active")

    def test_recover_clean_stale_managed_worktree(self) -> None:
        with temp_registry() as env:
            project = env.root / "repo"
            worktree = env.root / ".codex-worktrees" / "repo" / "recover-stale"
            binding = _managed_binding(project, worktree, "bind-stale", status="active")
            inspected = _inspected(binding, cleanup_state="stale", computed_status="stale")
            recovered_records: list[dict[str, object]] = []

            with mock.patch.object(workspace_session_cleanup, "inspect_binding", return_value=inspected):
                recovered = workspace_session_cleanup.execute_recover_binding(
                    _info(project),
                    [binding],
                    env.registry,
                    "bind-stale",
                    recovered_records.append,
                )

        self.assertTrue(recovered["ok"], recovered)
        self.assertEqual(recovered["action"], "recovered")
        self.assertEqual(recovered_records[0]["status"], "active")
        self.assertNotEqual(recovered_records[0]["heartbeat_at"], OLD_HEARTBEAT)

    def test_recover_can_run_from_target_managed_worktree(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "primary-dirty.txt", "dirty\n")
            result = workspace_session.write_guard(repo, session_id="recover-cwd", task_id="recover-cwd-task")
            managed = Path(result["effective_cwd"])
            stale = dict(result["binding"], heartbeat_at=OLD_HEARTBEAT, updated_at=OLD_HEARTBEAT)
            workspace_session.append_record(stale)

            recovered = workspace_session.worktree_recover(managed, stale["binding_id"])

        self.assertTrue(recovered["ok"], recovered)
        self.assertEqual(recovered["action"], "recovered")
        self.assertEqual(Path(recovered["effective_cwd"]).resolve(), managed.resolve())

    def test_recover_dirty_stale_worktree_requires_user_review(self) -> None:
        with temp_registry() as env:
            project = env.root / "repo"
            worktree = env.root / ".codex-worktrees" / "repo" / "recover-dirty"
            binding = _managed_binding(project, worktree, "bind-dirty", status="active")
            inspected = _inspected(
                binding,
                cleanup_state="dirty_orphan",
                computed_status="stale",
                dirty_paths=["dirty.txt"],
                clean_at_base=False,
            )

            with mock.patch.object(workspace_session_cleanup, "inspect_binding", return_value=inspected):
                recovered = workspace_session_cleanup.execute_recover_binding(
                    _info(project),
                    [binding],
                    env.registry,
                    "bind-dirty",
                    lambda _: None,
                )

        self.assertFalse(recovered["ok"], recovered)
        self.assertEqual(recovered["action"], "needs_user_review")
        self.assertIn("worktree has dirty paths", recovered["recover_guard"]["errors"])

    def test_recover_pruned_binding_is_blocked(self) -> None:
        binding = {
            "binding_id": "bind-pruned",
            "status": "pruned",
            "worktree_kind": "managed",
            "effective_cwd": "H:/tmp/worktree",
        }
        inspected = {**binding, "cleanup_state": "pruned", "computed_status": "pruned"}
        with mock.patch.object(workspace_session_cleanup, "inspect_binding", return_value=inspected):
            recovered = workspace_session_cleanup.execute_recover_binding(
                _info(Path("H:/tmp/repo")),
                [binding],
                Path("H:/tmp/registry.jsonl"),
                "bind-pruned",
                lambda _: None,
            )

        self.assertFalse(recovered["ok"], recovered)
        self.assertEqual(recovered["action"], "cannot_recover_pruned")

    def test_confirm_blocks_paths_outside_managed_container(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            outside = env.root / "outside"
            outside.mkdir(parents=True)
            candidate = {
                "binding_id": "bind-outside",
                "cleanup_state": "prunable",
                "worktree_kind": "managed",
                "effective_cwd": str(outside),
                "git": {
                    "path": str(outside),
                    "exists": True,
                    "is_git_worktree": True,
                    "status_ok": True,
                    "dirty_paths": [],
                    "clean_at_base": True,
                },
            }

            guard = workspace_session_cleanup.validate_prune_candidate(_info(project_root), candidate)

        self.assertFalse(guard["ok"])
        self.assertIn("effective_cwd is outside the managed worktree container", guard["errors"])

    def test_stale_dirty_managed_worktree_requires_user_review(self) -> None:
        with temp_registry() as env:
            project = env.root / "repo"
            worktree = env.root / ".codex-worktrees" / "repo" / "stale-dirty"
            binding = _managed_binding(project, worktree, "bind-stale-dirty", status="active")
            inspected = _inspected(
                binding,
                cleanup_state="dirty_orphan",
                computed_status="stale",
                dirty_paths=["managed-dirty.txt"],
                clean_at_base=False,
            )

            with mock.patch.object(workspace_session_cleanup, "inspect_binding", return_value=inspected):
                report = workspace_session_cleanup.build_cleanup_report(_info(project), [binding], env.registry)
                plan = workspace_session_cleanup.build_prune_plan(_info(project), [binding], env.registry)

        self.assertEqual([item["binding_id"] for item in report["stale_bindings"]], [binding["binding_id"]])
        self.assertEqual([item["cleanup_state"] for item in report["dirty_orphans"]], ["dirty_orphan"])
        self.assertEqual(plan["candidate_count"], 0)
        self.assertEqual(plan["blocked"][0]["cleanup_state"], "dirty_orphan")

    def test_primary_binding_is_reported_but_never_prunable(self) -> None:
        binding = {
            "binding_id": "bind-primary",
            "status": "released",
            "worktree_kind": "primary",
            "effective_cwd": "H:/tmp/repo",
        }
        inspected = {**binding, "cleanup_state": "not_managed", "computed_status": "released"}
        with mock.patch.object(workspace_session_cleanup, "inspect_binding", return_value=inspected):
            report = workspace_session_cleanup.build_cleanup_report(
                _info(Path("H:/tmp/repo")),
                [binding],
                Path("H:/tmp/registry.jsonl"),
            )
            plan = workspace_session_cleanup.build_prune_plan(
                _info(Path("H:/tmp/repo")),
                [binding],
                Path("H:/tmp/registry.jsonl"),
            )

        self.assertEqual(report["bindings"][0]["worktree_kind"], "primary")
        self.assertEqual(report["bindings"][0]["cleanup_state"], "not_managed")
        self.assertEqual(plan["candidate_count"], 0)

    def test_failed_git_status_blocks_prune_candidate(self) -> None:
        base_head = "a" * 40
        with tempfile.TemporaryDirectory() as temp:
            worktree = Path(temp)
            binding = {
                "binding_id": "bind-status-error",
                "status": "released",
                "worktree_kind": "managed",
                "effective_cwd": str(worktree),
                "base_head": base_head,
            }

            def fake_run_git(_: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
                if args[:2] == ["rev-parse", "--is-inside-work-tree"]:
                    return subprocess.CompletedProcess(args, 0, "true\n", "")
                if args[:1] == ["status"]:
                    return subprocess.CompletedProcess(args, 1, "", "index unavailable")
                if args[:2] == ["rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(args, 0, f"{base_head}\n", "")
                return subprocess.CompletedProcess(args, 1, "", "unexpected")

            with mock.patch.object(workspace_session_cleanup, "run_git", side_effect=fake_run_git):
                inspected = workspace_session_cleanup.inspect_binding(binding)

        self.assertEqual(inspected["cleanup_state"], "needs_user_review")
        self.assertFalse(inspected["git"]["status_ok"])
        self.assertFalse(inspected["git"]["clean_at_base"])

    def test_worktree_prune_requires_dry_run_flag(self) -> None:
        with session_env() as env:
            args = type("Args", (), {"project_root": str(env.repo), "dry_run": False, "confirm": False})()
            payloads: list[dict[str, object]] = []

            def capture(payload: dict[str, object]) -> int:
                payloads.append(payload)
                return 0 if payload.get("ok", True) else 2

            original_print_json = workspace_session_cli.print_json
            workspace_session_cli.print_json = capture
            try:
                exit_code = workspace_session_cli.cmd_worktree_prune(args)
            finally:
                workspace_session_cli.print_json = original_print_json

        self.assertEqual(exit_code, 2)
        self.assertFalse(payloads[0]["ok"])

    def test_worktree_prune_rejects_conflicting_flags(self) -> None:
        with session_env() as env:
            args = type("Args", (), {"project_root": str(env.repo), "dry_run": True, "confirm": True})()
            payloads: list[dict[str, object]] = []

            def capture(payload: dict[str, object]) -> int:
                payloads.append(payload)
                return 0 if payload.get("ok", True) else 2

            with mock.patch.object(workspace_session_cli, "print_json", side_effect=capture):
                exit_code = workspace_session_cli.cmd_worktree_prune(args)

        self.assertEqual(exit_code, 2)
        self.assertFalse(payloads[0]["ok"])


def _managed_binding(project: Path, worktree: Path, binding_id: str, *, status: str) -> dict[str, object]:
    return {
        "binding_id": binding_id,
        "status": status,
        "mode": "write",
        "worktree_kind": "managed",
        "effective_cwd": str(worktree),
        "base_head": "a" * 40,
        "heartbeat_at": OLD_HEARTBEAT,
        "updated_at": OLD_HEARTBEAT,
        "project_root": str(project),
    }


def _inspected(
    binding: dict[str, object],
    *,
    cleanup_state: str,
    computed_status: str,
    dirty_paths: list[str] | None = None,
    clean_at_base: bool = True,
) -> dict[str, object]:
    git_state = {
        "path": binding["effective_cwd"],
        "exists": True,
        "is_git_worktree": True,
        "status_ok": True,
        "dirty_paths": dirty_paths or [],
        "head": binding["base_head"],
        "base_head_matches": True,
        "clean_at_base": clean_at_base,
    }
    return {**binding, "cleanup_state": cleanup_state, "computed_status": computed_status, "git": git_state}


if __name__ == "__main__":
    unittest.main()
