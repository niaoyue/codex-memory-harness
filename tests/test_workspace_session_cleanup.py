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

from test_workspace_session import session_env, write_text, workspace_session
import workspace_session_cli
import workspace_session_cleanup


OLD_HEARTBEAT = "2000-01-01T00:00:00+00:00"


class WorkspaceSessionCleanupTests(unittest.TestCase):
    def test_released_clean_managed_worktree_is_prunable_in_dry_run(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "primary-dirty.txt", "dirty\n")
            result = workspace_session.write_guard(repo, session_id="cleanup", task_id="cleanup-task")
            managed = Path(result["effective_cwd"])

            released = workspace_session.update_binding(result["binding"]["binding_id"], "released")
            report = workspace_session.worktree_status(repo)
            plan = workspace_session.worktree_prune_plan(repo)
            managed_exists_after_plan = managed.exists()

        self.assertEqual(released["status"], "released")
        self.assertEqual([item["binding_id"] for item in report["prunable"]], [released["binding_id"]])
        self.assertEqual(plan["candidate_count"], 1)
        self.assertEqual(plan["candidates"][0]["cleanup_state"], "prunable")
        self.assertTrue(managed_exists_after_plan, "dry-run cleanup must not delete the worktree")

    def test_stale_dirty_managed_worktree_requires_user_review(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "primary-dirty.txt", "dirty\n")
            result = workspace_session.write_guard(repo, session_id="stale", task_id="stale-task")
            managed = Path(result["effective_cwd"])
            write_text(managed / "managed-dirty.txt", "dirty\n")
            stale = dict(result["binding"], heartbeat_at=OLD_HEARTBEAT, updated_at=OLD_HEARTBEAT)
            workspace_session.append_record(stale)

            report = workspace_session.worktree_status(repo)
            plan = workspace_session.worktree_prune_plan(repo)

        self.assertEqual([item["binding_id"] for item in report["stale_bindings"]], [stale["binding_id"]])
        self.assertEqual([item["cleanup_state"] for item in report["dirty_orphans"]], ["dirty_orphan"])
        self.assertEqual(plan["candidate_count"], 0)
        self.assertEqual(plan["blocked"][0]["cleanup_state"], "dirty_orphan")

    def test_primary_binding_is_reported_but_never_prunable(self) -> None:
        with session_env() as env:
            repo = env.repo
            result = workspace_session.write_guard(repo, session_id="primary", task_id="primary-task")
            workspace_session.update_binding(result["binding"]["binding_id"], "released")

            report = workspace_session.worktree_status(repo)
            plan = workspace_session.worktree_prune_plan(repo)

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
            args = type("Args", (), {"project_root": str(env.repo), "dry_run": False})()
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


if __name__ == "__main__":
    unittest.main()
