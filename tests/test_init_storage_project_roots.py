from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import init_storage


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


class InitStorageProjectRootTests(unittest.TestCase):
    def test_project_scope_at_user_home_falls_back_to_harness_global_storage(self) -> None:
        old_codex_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                real_home = Path.home().resolve()
                home = Path(temp_dir) / "home"
                codex_home = home / ".codex"
                codex_home.mkdir(parents=True)
                os.environ["CODEX_HOME"] = str(codex_home)
                blocked = {home.resolve(), codex_home.resolve(), real_home, (real_home / ".codex").resolve()}
                real_is_official = init_storage._is_official_codex_path_candidate

                with mock.patch.object(init_storage.Path, "home", return_value=home), mock.patch.object(init_storage, "_is_official_codex_path_candidate", side_effect=lambda candidate: candidate.resolve() in blocked or real_is_official(candidate)):
                    paths = init_storage.resolve_storage_paths(scope="project", cwd=home)

            self.assertEqual(paths.scope, "global")
            self.assertIsNone(paths.project_root)
            self.assertEqual(paths.storage_dir.resolve(), (codex_home / "codex-memory-harness" / "memories").resolve())
        finally:
            _restore_env("CODEX_HOME", old_codex_home)

    def test_project_scope_at_codex_home_does_not_create_official_memories(self) -> None:
        old_codex_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                real_home = Path.home().resolve()
                home = Path(temp_dir) / "home"
                codex_home = home / ".codex"
                codex_home.mkdir(parents=True)
                os.environ["CODEX_HOME"] = str(codex_home)
                blocked = {home.resolve(), codex_home.resolve(), real_home, (real_home / ".codex").resolve()}
                real_is_official = init_storage._is_official_codex_path_candidate

                with mock.patch.object(init_storage.Path, "home", return_value=home), mock.patch.object(init_storage, "_is_official_codex_path_candidate", side_effect=lambda candidate: candidate.resolve() in blocked or real_is_official(candidate)):
                    layout = init_storage.ensure_storage_layout(scope="project", cwd=codex_home)
                official_memory_created = (codex_home / "memories" / "memory.db").exists()
                harness_memory_created = (codex_home / "codex-memory-harness" / "memories" / "memory.db").exists()

            self.assertEqual(layout["scope"], "global")
            self.assertFalse(official_memory_created)
            self.assertTrue(harness_memory_created)
        finally:
            _restore_env("CODEX_HOME", old_codex_home)

    def test_user_home_project_root_override_falls_back_to_harness_global_storage(self) -> None:
        old_codex_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                home = Path(temp_dir) / "home"
                codex_home = home / ".codex"
                codex_home.mkdir(parents=True)
                os.environ["CODEX_HOME"] = str(codex_home)
                real_home = Path.home().resolve()
                blocked = {home.resolve(), codex_home.resolve(), real_home, (real_home / ".codex").resolve()}
                real_is_official = init_storage._is_official_codex_path_candidate

                with mock.patch.object(init_storage.Path, "home", return_value=home), mock.patch.object(init_storage, "_is_official_codex_path_candidate", side_effect=lambda candidate: candidate.resolve() in blocked or real_is_official(candidate)):
                    paths = init_storage.resolve_storage_paths(
                        scope="project",
                        cwd=home,
                        project_root_override=home,
                    )

            self.assertEqual(paths.scope, "global")
            self.assertIsNone(paths.project_root)
        finally:
            _restore_env("CODEX_HOME", old_codex_home)

    def test_codex_home_project_root_override_does_not_create_official_memories(self) -> None:
        old_codex_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                home = Path(temp_dir) / "home"
                codex_home = home / ".codex"
                codex_home.mkdir(parents=True)
                os.environ["CODEX_HOME"] = str(codex_home)
                real_home = Path.home().resolve()
                blocked = {home.resolve(), codex_home.resolve(), real_home, (real_home / ".codex").resolve()}
                real_is_official = init_storage._is_official_codex_path_candidate

                with mock.patch.object(init_storage.Path, "home", return_value=home), mock.patch.object(init_storage, "_is_official_codex_path_candidate", side_effect=lambda candidate: candidate.resolve() in blocked or real_is_official(candidate)):
                    layout = init_storage.ensure_storage_layout(
                        scope="project",
                        cwd=codex_home,
                        project_root_override=codex_home,
                    )
                official_memory_created = (codex_home / "memories" / "memory.db").exists()

            self.assertEqual(layout["scope"], "global")
            self.assertFalse(official_memory_created)
        finally:
            _restore_env("CODEX_HOME", old_codex_home)

    def test_codex_home_descendant_marker_falls_back_to_harness_global_storage(self) -> None:
        old_codex_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                home = Path(temp_dir) / "home"
                codex_home = home / ".codex"
                official_memories = codex_home / "memories"
                official_memories.mkdir(parents=True)
                (official_memories / "README.md").write_text("# official memory runtime\n", encoding="utf-8")
                os.environ["CODEX_HOME"] = str(codex_home)
                real_home = Path.home().resolve()
                blocked = {home.resolve(), codex_home.resolve(), real_home, (real_home / ".codex").resolve()}
                real_is_official = init_storage._is_official_codex_path_candidate

                with mock.patch.object(init_storage.Path, "home", return_value=home), mock.patch.object(init_storage, "_is_official_codex_path_candidate", side_effect=lambda candidate: candidate.resolve() in blocked or real_is_official(candidate)):
                    layout = init_storage.ensure_storage_layout(scope="project", cwd=official_memories)
                nested_project_memory_created = (official_memories / ".codex" / "memories" / "memory.db").exists()
                harness_memory_created = (codex_home / "codex-memory-harness" / "memories" / "memory.db").exists()

            self.assertEqual(layout["scope"], "global")
            self.assertFalse(nested_project_memory_created)
            self.assertTrue(harness_memory_created)
        finally:
            _restore_env("CODEX_HOME", old_codex_home)


if __name__ == "__main__":
    unittest.main()
