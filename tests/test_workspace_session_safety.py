from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_workspace_session import run_git, session_env, temp_registry, write_text, workspace_session, workspace_session_lock


class WorkspaceSessionSafetyTests(unittest.TestCase):
    def test_rejected_write_path_does_not_leave_active_binding(self) -> None:
        with session_env() as env:
            repo = env.repo
            result = workspace_session.write_guard(
                repo,
                session_id="path-session",
                task_id="path-task",
                intended_paths=["../outside.txt"],
            )
            info = workspace_session.project_info(repo)
            active = workspace_session.active_bindings(info["project_key"])
            records = [
                item for item in workspace_session.read_records()
                if item.get("binding_id") == result["binding"]["binding_id"]
            ]

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "path_outside_effective_cwd")
        self.assertEqual(active, [])
        self.assertEqual([item["status"] for item in records], ["active", "released"])

    def test_existing_managed_worktree_must_be_clean_at_base_head(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "dirty.txt", "dirty\n")
            result = workspace_session.write_guard(repo, session_id="session-dirty", task_id="task-dirty")
            managed = Path(result["effective_cwd"])
            write_text(managed / "stale.txt", "stale\n")
            base_head = workspace_session.project_info(repo)["head"]

            with self.assertRaisesRegex(RuntimeError, "not clean at the expected base head"):
                workspace_session.ensure_managed_worktree(repo, "task-dirty", "session-dirty", base_head)

    def test_existing_managed_branch_must_match_base_head(self) -> None:
        with session_env() as env:
            repo = env.repo
            task_id = "task-branch"
            session_id = "session-branch"
            base_head = workspace_session.project_info(repo)["head"]
            branch = workspace_session.managed_branch(task_id, session_id)
            run_git(repo, ["checkout", "-b", branch])
            write_text(repo / "branch.txt", "branch\n")
            run_git(repo, ["add", "branch.txt"])
            run_git(repo, ["commit", "-m", "branch change"])
            run_git(repo, ["checkout", "main"])

            with self.assertRaisesRegex(RuntimeError, "branch exists but is not at the expected base head"):
                workspace_session.ensure_managed_worktree(repo, task_id, session_id, base_head)

    def test_new_managed_worktree_uses_recorded_base_head(self) -> None:
        with session_env() as env:
            repo = env.repo
            base_head = workspace_session.project_info(repo)["head"]
            write_text(repo / "later.txt", "later\n")
            run_git(repo, ["add", "later.txt"])
            run_git(repo, ["commit", "-m", "advance main"])

            path, _ = workspace_session.ensure_managed_worktree(repo, "task-base", "session-base", base_head)
            managed_head = workspace_session.git_text(path, ["rev-parse", "HEAD"])

        self.assertEqual(managed_head, base_head)

    def test_managed_worktree_from_managed_checkout_uses_primary_anchor(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "dirty.txt", "dirty\n")
            first = workspace_session.write_guard(repo, session_id="first", task_id="first-task")
            first_managed = Path(first["effective_cwd"])

            second = workspace_session.write_guard(first_managed, session_id="second", task_id="second-task")
            second_managed = Path(second["effective_cwd"])

        self.assertFalse(second["ok"], second)
        self.assertEqual(second["action"], "switch_to_effective_cwd")
        self.assertEqual(second_managed.parent, first_managed.parent)
        self.assertNotEqual(second_managed.parent, first_managed / ".codex-worktrees" / first_managed.name)

    def test_same_session_must_release_old_write_binding_before_new_task(self) -> None:
        with session_env() as env:
            repo = env.repo
            first = workspace_session.write_guard(repo, session_id="same", task_id="first-task")
            second = workspace_session.write_guard(repo, session_id="same", task_id="second-task")
            active = workspace_session.active_bindings(workspace_session.project_info(repo)["project_key"])

        self.assertTrue(first["ok"], first)
        self.assertFalse(second["ok"], second)
        self.assertEqual(second["action"], "release_existing_write_binding_required")
        self.assertEqual([item["task_id"] for item in active], ["first-task"])

    def test_read_bind_reuses_active_write_binding_for_same_session_task(self) -> None:
        with session_env() as env:
            repo = env.repo
            first = workspace_session.write_guard(repo, session_id="lease", task_id="lease-task")
            read = workspace_session.bind_session(repo, session_id="lease", task_id="lease-task", mode="read")
            info = workspace_session.project_info(repo)
            records_after_read = workspace_session.read_records()
            active_after_read = workspace_session.active_bindings(info["project_key"])

            second = workspace_session.write_guard(repo, session_id="second", task_id="second-task")

        self.assertTrue(first["ok"], first)
        self.assertEqual(read["action"], "reuse_binding")
        self.assertEqual(read["binding"]["mode"], "write")
        self.assertEqual(len(records_after_read), 1)
        self.assertEqual([item["mode"] for item in active_after_read], ["write"])
        self.assertFalse(second["ok"], second)
        self.assertEqual(second["binding"]["worktree_kind"], "managed")

    def test_dirty_primary_write_release_is_marked_dirty(self) -> None:
        with session_env() as env:
            repo = env.repo
            result = workspace_session.write_guard(repo, session_id="primary", task_id="primary-task")
            write_text(repo / "dirty.txt", "dirty\n")

            released = workspace_session.update_binding(result["binding"]["binding_id"], "released")

        self.assertEqual(released["status"], "released_dirty")

    def test_dirty_primary_absolute_path_preserves_managed_switch_binding(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "dirty.txt", "dirty\n")
            result = workspace_session.write_guard(
                repo,
                session_id="absolute",
                task_id="absolute-task",
                intended_paths=[str(repo / "README.md")],
            )
            active = workspace_session.active_bindings(workspace_session.project_info(repo)["project_key"])

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "switch_to_effective_cwd")
        self.assertEqual([item["binding_id"] for item in active], [result["binding"]["binding_id"]])

    def test_project_key_stays_stable_when_remote_changes(self) -> None:
        with session_env() as env:
            repo = env.repo
            before = workspace_session.project_info(repo)
            first = workspace_session.write_guard(repo, session_id="first", task_id="first-task")
            run_git(repo, ["remote", "add", "origin", "https://example.invalid/repo.git"])
            after = workspace_session.project_info(repo)

            second = workspace_session.write_guard(repo, session_id="second", task_id="second-task")

        self.assertEqual(after["project_key"], before["project_key"])
        self.assertTrue(first["ok"], first)
        self.assertFalse(second["ok"], second)
        self.assertEqual(second["binding"]["worktree_kind"], "managed")

    def test_stale_lock_with_live_owner_is_not_reclaimed_by_age_only(self) -> None:
        with temp_registry() as env:
            lock = env.registry.with_name(f"{env.registry.name}.lock")
            lock.write_text(f"pid={os.getpid()} created_at=old\n", encoding="utf-8")
            old = time.time() - workspace_session_lock.LOCK_STALE_SECONDS - 5
            os.utime(lock, (old, old))

            reclaimed = workspace_session_lock.reclaim_stale_lock(lock)

        self.assertFalse(reclaimed)

    def test_stale_lock_reclaim_uses_single_reclaimer_guard(self) -> None:
        with temp_registry() as env:
            lock = env.registry.with_name(f"{env.registry.name}.lock")
            guard = workspace_session_lock.reclaim_guard_path(lock)
            lock.write_text("pid=0 token=old created_at=old\n", encoding="utf-8")
            guard.write_text("pid=0 token=other\n", encoding="utf-8")
            old = time.time() - workspace_session_lock.LOCK_STALE_SECONDS - 5
            os.utime(lock, (old, old))

            reclaimed = workspace_session_lock.reclaim_stale_lock(lock)
            lock_still_exists = lock.exists()

            guard.unlink()

        self.assertFalse(reclaimed)
        self.assertTrue(lock_still_exists)

    def test_stale_lock_reclaim_releases_guard_after_unlink(self) -> None:
        with temp_registry() as env:
            lock = env.registry.with_name(f"{env.registry.name}.lock")
            guard = workspace_session_lock.reclaim_guard_path(lock)
            lock.write_text("pid=0 token=old created_at=old\n", encoding="utf-8")
            old = time.time() - workspace_session_lock.LOCK_STALE_SECONDS - 5
            os.utime(lock, (old, old))

            reclaimed = workspace_session_lock.reclaim_stale_lock(lock)
            lock_still_exists = lock.exists()
            guard_still_exists = guard.exists()

        self.assertTrue(reclaimed)
        self.assertFalse(lock_still_exists)
        self.assertFalse(guard_still_exists)

    def test_stale_former_owner_does_not_release_new_owner_lock(self) -> None:
        with temp_registry() as env:
            lock = workspace_session_lock.acquire_registry_lock(env.registry, "old")
            lock.write_text(f"pid={os.getpid()} token=new-owner created_at=new\n", encoding="utf-8")

            workspace_session_lock.release_registry_lock(lock)

            still_locked = lock.exists()
            lock.unlink()

        self.assertTrue(still_locked)


if __name__ == "__main__":
    unittest.main()
