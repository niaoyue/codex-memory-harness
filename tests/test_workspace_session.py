from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import workspace_session
import workspace_session_lock


class WorkspaceSessionTests(unittest.TestCase):
    def test_clean_primary_checkout_gets_write_binding(self) -> None:
        with session_env() as env:
            repo = env.repo

            result = workspace_session.write_guard(repo, session_id="session-a", task_id="task-a")

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["action"], "allow_write")
            self.assertEqual(result["binding"]["worktree_kind"], "primary")
            self.assertEqual(Path(result["effective_cwd"]).resolve(), repo.resolve())

    def test_dirty_primary_checkout_requires_managed_worktree(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "dirty.txt", "dirty\n")

            result = workspace_session.write_guard(repo, session_id="session-b", task_id="task-b")

            self.assertFalse(result["ok"], result)
            self.assertEqual(result["action"], "switch_to_effective_cwd")
            binding = result["binding"]
            self.assertEqual(binding["worktree_kind"], "managed")
            self.assertIn("dirty.txt", binding["dirty_snapshot"])
            effective = Path(result["effective_cwd"])
            self.assertTrue(effective.exists())
            self.assertNotEqual(effective.resolve(), repo.resolve())
            self.assertTrue((effective / ".git").exists() or (effective / ".git").is_file())

    def test_managed_worktree_branch_is_git_ref_safe(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "dirty.txt", "dirty\n")

            result = workspace_session.write_guard(repo, session_id="session-ref", task_id="foo..bar.lock")

            self.assertFalse(result["ok"], result)
            branch = result["binding"]["branch"]
            self.assertNotIn("..", branch)
            self.assertFalse(branch.endswith(".lock"))
            run_git(repo, ["check-ref-format", "--branch", branch])

    def test_tracked_dirty_path_keeps_first_character(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "README.md", "# Changed\n")

            with mock.patch.object(workspace_session, "ensure_managed_worktree") as ensure:
                ensure.return_value = (env.root / "managed", "codex/task-readme/abc")
                result = workspace_session.write_guard(repo, session_id="session-readme", task_id="task-readme")

            self.assertFalse(result["ok"], result)
            self.assertIn("README.md", result["binding"]["dirty_snapshot"])
            self.assertNotIn("EADME.md", result["binding"]["dirty_snapshot"])

    def test_other_active_writer_forces_managed_worktree_even_when_clean(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            existing = _binding(
                project_root,
                binding_id="bind-owner",
                session_id="session-owner",
                task_id="task-owner",
            )
            workspace_session.append_record(existing)
            with (
                mock.patch.object(workspace_session, "git_root", return_value=project_root),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "ensure_managed_worktree") as ensure,
            ):
                ensure.return_value = (env.root / "managed", "codex/task-new/abc")
                second = workspace_session.write_guard(project_root, session_id="session-new", task_id="task-new")

        self.assertFalse(second["ok"], second)
        self.assertEqual(second["binding"]["worktree_kind"], "managed")
        self.assertIn("another active write session", second["reason"])

    def test_same_session_task_reuses_binding(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            existing = _binding(project_root, binding_id="bind-same", session_id="same", task_id="same-task")
            workspace_session.append_record(existing)
            with (
                mock.patch.object(workspace_session, "git_root", return_value=project_root),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
            ):
                second = workspace_session.bind_session(project_root, session_id="same", task_id="same-task", mode="write")

        self.assertEqual(second["action"], "reuse_binding")
        self.assertEqual(second["binding"]["binding_id"], "bind-same")

    def test_stale_managed_binding_returns_to_free_primary(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            managed = env.root / "managed"
            managed.mkdir()
            existing = _binding(project_root, binding_id="bind-managed", session_id="same", task_id="same-task")
            existing["worktree_kind"] = "managed"
            existing["effective_cwd"] = str(managed)
            workspace_session.append_record(existing)
            with (
                mock.patch.object(workspace_session, "git_root", return_value=project_root),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "managed_binding_can_release", return_value=True),
                mock.patch.object(workspace_session, "git_text", return_value="main"),
            ):
                result = workspace_session.write_guard(project_root, session_id="same", task_id="same-task")
            released = [item for item in workspace_session.read_records() if item.get("binding_id") == "bind-managed"]

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["action"], "allow_write")
        self.assertEqual(result["binding"]["worktree_kind"], "primary")
        self.assertEqual(released[-1]["status"], "released")

    def test_dirty_managed_binding_is_preserved_from_primary(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            managed = env.root / "managed"
            managed.mkdir()
            existing = _binding(project_root, binding_id="bind-managed", session_id="same", task_id="same-task")
            existing["worktree_kind"] = "managed"
            existing["effective_cwd"] = str(managed)
            workspace_session.append_record(existing)
            with (
                mock.patch.object(workspace_session, "git_root", return_value=project_root),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "managed_binding_can_release", return_value=False),
            ):
                result = workspace_session.write_guard(project_root, session_id="same", task_id="same-task")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "switch_to_effective_cwd")
        self.assertEqual(result["binding"]["binding_id"], "bind-managed")

    def test_managed_binding_reuses_after_switch_to_effective_cwd(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            managed = env.root / "managed"
            managed.mkdir()
            existing = _binding(project_root, binding_id="bind-managed", session_id="same", task_id="same-task")
            existing["worktree_kind"] = "managed"
            existing["effective_cwd"] = str(managed)
            workspace_session.append_record(existing)
            with (
                mock.patch.object(workspace_session, "git_root", return_value=managed),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
            ):
                result = workspace_session.write_guard(managed, session_id="same", task_id="same-task")

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["action"], "allow_write")
        self.assertEqual(result["binding"]["binding_id"], "bind-managed")
        self.assertEqual(result["binding"]["worktree_kind"], "managed")

    def test_binding_id_includes_project_scope(self) -> None:
        first = workspace_session.binding_record(
            info={**_info(Path("repo-a")), "project_key": "project-a"},
            session_id="same",
            task_id="same-task",
            mode="write",
            effective_cwd=Path("repo-a"),
            worktree_kind="primary",
            branch="main",
            dirty_snapshot=[],
            reason="test",
        )
        second = workspace_session.binding_record(
            info={**_info(Path("repo-b")), "project_key": "project-b"},
            session_id="same",
            task_id="same-task",
            mode="write",
            effective_cwd=Path("repo-b"),
            worktree_kind="primary",
            branch="main",
            dirty_snapshot=[],
            reason="test",
        )

        self.assertNotEqual(first["binding_id"], second["binding_id"])

    def test_long_task_id_keeps_unique_digest_suffix(self) -> None:
        root = Path("repo")
        prefix = "x" * 80
        first = prefix + "a"
        second = prefix + "b"

        self.assertNotEqual(workspace_session.safe_id(first), workspace_session.safe_id(second))
        self.assertNotEqual(
            workspace_session.managed_worktree_path(root, first, "same-session"),
            workspace_session.managed_worktree_path(root, second, "same-session"),
        )
        self.assertNotEqual(
            workspace_session.managed_branch(first, "same-session"),
            workspace_session.managed_branch(second, "same-session"),
        )

    def test_normalized_task_ids_keep_distinct_identifiers(self) -> None:
        root = Path("repo")
        first = workspace_session.binding_record(
            info=_info(root), session_id="same", task_id="foo/bar", mode="write",
            effective_cwd=root, worktree_kind="primary", branch="main", dirty_snapshot=[], reason="test",
        )
        second = workspace_session.binding_record(
            info=_info(root), session_id="same", task_id="foo bar", mode="write",
            effective_cwd=root, worktree_kind="primary", branch="main", dirty_snapshot=[], reason="test",
        )

        self.assertNotEqual(first["binding_id"], second["binding_id"])
        self.assertNotEqual(
            workspace_session.managed_worktree_path(root, "foo/bar", "same"),
            workspace_session.managed_worktree_path(root, "foo bar", "same"),
        )
        self.assertNotEqual(
            workspace_session.managed_branch("foo/bar", "same"),
            workspace_session.managed_branch("foo bar", "same"),
        )

    def test_existing_managed_path_must_be_expected_git_worktree(self) -> None:
        with session_env() as env:
            repo = env.repo
            write_text(repo / "dirty.txt", "dirty\n")
            stale = workspace_session.managed_worktree_path(repo, "task-existing", "session-existing")
            stale.mkdir(parents=True)

            with self.assertRaisesRegex(RuntimeError, "not the expected worktree"):
                workspace_session.write_guard(repo, session_id="session-existing", task_id="task-existing")

    def test_dirty_managed_release_uses_released_dirty_status(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            existing = _binding(project_root, binding_id="bind-managed", session_id="same", task_id="same-task")
            existing["worktree_kind"] = "managed"
            existing["effective_cwd"] = str(env.root / "managed")
            workspace_session.append_record(existing)
            with mock.patch.object(workspace_session, "managed_binding_can_release", return_value=False):
                result = workspace_session.update_binding("bind-managed", "released")

        self.assertEqual(result["status"], "released_dirty")

    def test_heartbeat_does_not_revive_released_binding(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            existing = _binding(project_root, binding_id="bind-released", session_id="same", task_id="same-task")
            workspace_session.append_record(existing)

            released = workspace_session.update_binding("bind-released", "released")
            heartbeat = workspace_session.update_binding("bind-released", "active")
            records = [
                item for item in workspace_session.read_records()
                if item.get("binding_id") == "bind-released"
            ]
            active = workspace_session.active_bindings("project-key")

        self.assertEqual(released["status"], "released_dirty")
        self.assertEqual(heartbeat["status"], "released_dirty")
        self.assertEqual([item["status"] for item in records], ["active", "released_dirty"])
        self.assertEqual(active, [])

    def test_heartbeat_command_fails_after_release(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            existing = _binding(project_root, binding_id="bind-released", session_id="same", task_id="same-task")
            workspace_session.append_record(existing)
            workspace_session.update_binding("bind-released", "released")
            payloads: list[dict[str, object]] = []
            def capture(payload: dict[str, object]) -> int:
                payloads.append(payload)
                return 0 if payload.get("ok", True) else 2

            args = type("Args", (), {"binding_id": "bind-released"})()
            with mock.patch.object(workspace_session, "print_json", side_effect=capture):
                exit_code = workspace_session.cmd_heartbeat(args)

        self.assertEqual(exit_code, 2)
        self.assertFalse(payloads[0]["ok"])
        self.assertEqual(payloads[0]["binding"]["status"], "released_dirty")

    def test_write_guard_rejects_absolute_path_outside_effective_cwd(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            outside = env.root / "outside.txt"
            with (
                mock.patch.object(workspace_session, "git_root", return_value=project_root),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "git_text", return_value="main"),
            ):
                result = workspace_session.write_guard(
                    project_root,
                    session_id="session-c",
                    task_id="task-c",
                    intended_paths=[str(outside)],
                )

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "path_outside_effective_cwd")
        self.assertEqual(result["violations"], [str(outside)])

    def test_write_guard_rejects_relative_path_outside_effective_cwd(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            outside = str(Path("..") / "outside.txt")
            with (
                mock.patch.object(workspace_session, "git_root", return_value=project_root),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "git_text", return_value="main"),
            ):
                result = workspace_session.write_guard(
                    project_root,
                    session_id="session-rel",
                    task_id="task-rel",
                    intended_paths=[outside],
                )

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "path_outside_effective_cwd")
        self.assertEqual(result["violations"], [outside])

    def test_project_info_redacts_remote_url(self) -> None:
        with session_env() as env:
            repo = env.repo
            remote = "https://user:secret@example.internal/repo.git"
            run_git(repo, ["remote", "add", "origin", remote])

            info = workspace_session.project_info(repo)
            result = workspace_session.write_guard(repo, session_id="session-remote", task_id="task-remote")

        self.assertTrue(info["remote"].startswith("sha1:"))
        self.assertNotIn("secret", info["remote"])
        self.assertNotIn("example.internal", info["remote"])
        self.assertEqual(result["binding"]["remote"], info["remote"])

    def test_bind_session_locks_registry_allocation(self) -> None:
        with temp_registry() as env:
            project_root = env.root / "repo"
            lock = env.root / "registry.jsonl.lock"
            calls: list[str] = []

            def active(_: str) -> list[dict[str, object]]:
                calls.append("active")
                return []

            def append(_: dict[str, object]) -> None:
                calls.append("append")

            def release(path: Path) -> None:
                calls.append(f"release:{path.name}")

            with (
                mock.patch.object(workspace_session, "git_root", return_value=project_root),
                mock.patch.object(workspace_session, "project_info", return_value=_info(project_root)),
                mock.patch.object(workspace_session, "acquire_registry_lock", return_value=lock) as acquire,
                mock.patch.object(workspace_session, "active_bindings", side_effect=active),
                mock.patch.object(workspace_session, "dirty_paths", return_value=[]),
                mock.patch.object(workspace_session, "git_text", return_value="main"),
                mock.patch.object(workspace_session, "append_record", side_effect=append),
                mock.patch.object(workspace_session, "release_registry_lock", side_effect=release),
            ):
                result = workspace_session.bind_session(
                    project_root,
                    session_id="session-lock",
                    task_id="task-lock",
                    mode="write",
                )

        self.assertEqual(result["action"], "bind_primary")
        acquire.assert_called_once_with()
        self.assertEqual(calls, ["active", "append", "release:registry.jsonl.lock"])

    def test_stale_registry_lock_is_reclaimed(self) -> None:
        with temp_registry() as env:
            lock = env.registry.with_name(f"{env.registry.name}.lock")
            lock.write_text("pid=999999 created_at=old\n", encoding="utf-8")
            old = time.time() - workspace_session_lock.LOCK_STALE_SECONDS - 5
            os.utime(lock, (old, old))

            acquired = workspace_session.acquire_registry_lock()
            workspace_session.release_registry_lock(acquired)

        self.assertEqual(acquired, lock)


class session_env:
    def __enter__(self) -> "session_env":
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.registry = self.root / "registry.jsonl"
        self.old_registry = os.environ.get(workspace_session.REGISTRY_ENV)
        os.environ[workspace_session.REGISTRY_ENV] = str(self.registry)
        init_repo(self.repo)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.old_registry is None:
            os.environ.pop(workspace_session.REGISTRY_ENV, None)
        else:
            os.environ[workspace_session.REGISTRY_ENV] = self.old_registry
        self.temp_dir.cleanup()


class temp_registry:
    def __enter__(self) -> "temp_registry":
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.registry = self.root / "registry.jsonl"
        self.old_registry = os.environ.get(workspace_session.REGISTRY_ENV)
        os.environ[workspace_session.REGISTRY_ENV] = str(self.registry)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.old_registry is None:
            os.environ.pop(workspace_session.REGISTRY_ENV, None)
        else:
            os.environ[workspace_session.REGISTRY_ENV] = self.old_registry
        self.temp_dir.cleanup()


def _info(project_root: Path) -> dict[str, str]:
    return {
        "project_key": "project-key",
        "project_root": str(project_root),
        "git_common_dir": str(project_root / ".git"),
        "head": "0" * 40,
        "remote": "",
    }


def _binding(project_root: Path, *, binding_id: str, session_id: str, task_id: str) -> dict[str, object]:
    binding = workspace_session.binding_record(
        info=_info(project_root),
        session_id=session_id,
        task_id=task_id,
        mode="write",
        effective_cwd=project_root,
        worktree_kind="primary",
        branch="main",
        dirty_snapshot=[],
        reason="test",
    )
    binding["binding_id"] = binding_id
    return binding


def init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    run_git(path, ["init", "-b", "main"])
    run_git(path, ["config", "user.email", "test@example.com"])
    run_git(path, ["config", "user.name", "Test User"])
    write_text(path / "README.md", "# Test\n")
    run_git(path, ["add", "README.md"])
    run_git(path, ["commit", "-m", "initial"])


def run_git(path: Path, args: list[str]) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
