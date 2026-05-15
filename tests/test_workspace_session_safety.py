from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_workspace_session import _binding, _info, run_git, session_env, temp_registry, write_text, workspace_session, workspace_session_lock


class WorkspaceSessionSafetyTests(unittest.TestCase):
    def test_rejected_write_path_does_not_leave_active_binding(self) -> None:
        with temp_registry() as env:
            repo = env.root / "repo"
            with (
                mock.patch.object(workspace_session, "git_root", return_value=repo),
                mock.patch.object(workspace_session, "project_info", return_value=_info(repo)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "git_text", return_value="main"),
            ):
                result = workspace_session.write_guard(
                    repo,
                    session_id="path-session",
                    task_id="path-task",
                    intended_paths=["../outside.txt"],
                )
                active = workspace_session.active_bindings(_info(repo)["project_key"])
            records = [
                item for item in workspace_session.read_records()
                if item.get("binding_id") == result["binding"]["binding_id"]
            ]

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "path_outside_effective_cwd")
        self.assertEqual(active, [])
        self.assertEqual([item["status"] for item in records], ["active", "released"])

    def test_existing_managed_worktree_must_be_clean_at_base_head(self) -> None:
        with temp_registry() as env:
            repo = env.root / "repo"
            repo.mkdir()
            base_head = "a" * 40
            managed = workspace_session.managed_worktree_path(repo, "task-dirty", "session-dirty")
            managed.mkdir(parents=True)
            branch = workspace_session.managed_branch("task-dirty", "session-dirty")

            def fake_run_git(cwd: Path, args: list[str], *, check: bool = True) -> object:
                if cwd == managed and args == ["rev-parse", "--show-toplevel"]:
                    return _completed(args, stdout=f"{managed}\n")
                if cwd == managed and args == ["branch", "--show-current"]:
                    return _completed(args, stdout=f"{branch}\n")
                if cwd == managed and args == ["rev-parse", "HEAD"]:
                    return _completed(args, stdout=f"{base_head}\n")
                return _completed(args, returncode=1, stderr="unexpected git call")

            with (
                mock.patch.object(workspace_session, "run_git", side_effect=fake_run_git),
                mock.patch.object(workspace_session, "dirty_paths", return_value=["stale.txt"]),
                self.assertRaisesRegex(RuntimeError, "not clean at the expected base head"),
            ):
                workspace_session.ensure_managed_worktree(repo, "task-dirty", "session-dirty", base_head)

    def test_existing_managed_branch_must_match_base_head(self) -> None:
        with temp_registry() as env:
            repo = env.root / "repo"
            repo.mkdir()
            task_id = "task-branch"
            session_id = "session-branch"
            base_head = "a" * 40
            branch = workspace_session.managed_branch(task_id, session_id)

            def fake_run_git(_: Path, args: list[str], *, check: bool = True) -> object:
                if args == ["show-ref", "--verify", f"refs/heads/{branch}"]:
                    return _completed(args)
                if args == ["rev-parse", branch]:
                    return _completed(args, stdout=f"{'b' * 40}\n")
                return _completed(args, returncode=1, stderr="unexpected git call")

            with (
                mock.patch.object(workspace_session, "run_git", side_effect=fake_run_git),
                self.assertRaisesRegex(RuntimeError, "branch exists but is not at the expected base head"),
            ):
                workspace_session.ensure_managed_worktree(repo, task_id, session_id, base_head)

    def test_new_managed_worktree_uses_recorded_base_head(self) -> None:
        with temp_registry() as env:
            repo = env.root / "repo"
            repo.mkdir()
            base_head = "a" * 40
            calls: list[list[str]] = []

            def fake_run_git(_: Path, args: list[str], *, check: bool = True) -> object:
                calls.append(args)
                if args[:2] == ["show-ref", "--verify"]:
                    return _completed(args, returncode=1)
                return _completed(args)

            with mock.patch.object(workspace_session, "run_git", side_effect=fake_run_git):
                path, branch = workspace_session.ensure_managed_worktree(repo, "task-base", "session-base", base_head)

        self.assertTrue(path.is_absolute())
        self.assertTrue(
            any(
                call[:4] == ["worktree", "add", "-b", branch]
                and Path(call[4]).resolve(strict=False) == path.resolve(strict=False)
                and call[5:] == [base_head]
                for call in calls
            ),
            calls,
        )

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
        with temp_registry() as env:
            repo = env.root / "repo"
            with (
                mock.patch.object(workspace_session, "git_root", return_value=repo),
                mock.patch.object(workspace_session, "project_info", return_value=_info(repo)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "git_text", return_value="main"),
            ):
                first = workspace_session.write_guard(repo, session_id="same", task_id="first-task")
                second = workspace_session.write_guard(repo, session_id="same", task_id="second-task")
                active = workspace_session.active_bindings(_info(repo)["project_key"])

        self.assertTrue(first["ok"], first)
        self.assertFalse(second["ok"], second)
        self.assertEqual(second["action"], "release_existing_write_binding_required")
        self.assertEqual([item["task_id"] for item in active], ["first-task"])

    def test_read_bind_reuses_active_write_binding_for_same_session_task(self) -> None:
        with temp_registry() as env:
            repo = env.root / "repo"
            with (
                mock.patch.object(workspace_session, "git_root", return_value=repo),
                mock.patch.object(workspace_session, "project_info", return_value=_info(repo)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "git_text", return_value="main"),
            ):
                first = workspace_session.write_guard(repo, session_id="lease", task_id="lease-task")
                read = workspace_session.bind_session(repo, session_id="lease", task_id="lease-task", mode="read")
            records_after_read = workspace_session.read_records()
            active_after_read = workspace_session.active_bindings(_info(repo)["project_key"])

        self.assertTrue(first["ok"], first)
        self.assertEqual(read["action"], "reuse_binding")
        self.assertEqual(read["binding"]["mode"], "write")
        self.assertEqual(len(records_after_read), 1)
        self.assertEqual([item["mode"] for item in active_after_read], ["write"])

    def test_dirty_primary_write_release_is_marked_dirty(self) -> None:
        with temp_registry() as env:
            existing = _binding(env.root / "repo", binding_id="bind-primary", session_id="primary", task_id="primary-task")
            workspace_session.append_record(existing)

            with mock.patch.object(workspace_session, "managed_binding_can_release", return_value=False):
                released = workspace_session.update_binding("bind-primary", "released")

        self.assertEqual(released["status"], "released_dirty")

    def test_dirty_primary_absolute_path_preserves_managed_switch_binding(self) -> None:
        with temp_registry() as env:
            repo = env.root / "repo"
            managed = env.root / "managed"
            with (
                mock.patch.object(workspace_session, "git_root", return_value=repo),
                mock.patch.object(workspace_session, "project_info", return_value=_info(repo)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=["dirty.txt"]),
                mock.patch.object(workspace_session, "ensure_managed_worktree", return_value=(managed, "branch")),
            ):
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

        self.assertEqual(after["project_key"], before["project_key"])
        self.assertTrue(first["ok"], first)

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


def _completed(args: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = "") -> object:
    return workspace_session.subprocess.CompletedProcess(args, returncode, stdout, stderr)


if __name__ == "__main__":
    unittest.main()
