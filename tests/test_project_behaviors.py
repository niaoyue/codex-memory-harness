from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
import gc
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

for path in (SCRIPTS_DIR, PLUGIN_SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import build_release
import codex_bootstrap
import init_storage
import install_support
import install_codex_memory
import memory_store
import retrieval_store
import run_demo_flow
import shared_memory
import verification_runner


class BuildReleaseTests(unittest.TestCase):
    def test_release_excludes_runtime_codex_and_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            package_path = build_release.build(Path(output_dir))
            with zipfile.ZipFile(package_path) as archive:
                names = archive.namelist()

        self.assertNotIn(".codex/harness/commands.json", names)
        self.assertNotIn(".codex/harness/project_profile.json", names)
        self.assertFalse(any(name.startswith(".codex/") for name in names))
        self.assertFalse(any(name.startswith("dist/") for name in names))
        self.assertFalse(any("__pycache__/" in name for name in names))
        self.assertFalse(any(name.endswith(".pyc") for name in names))
        self.assertFalse(any(name.endswith("memory.db") for name in names))
        self.assertFalse(any(name.endswith("events.jsonl") for name in names))
        self.assertIn("templates/project/.codex/harness/commands.json", names)
        self.assertIn("templates/project/.codex/shared/README.md", names)


class InstallerTests(unittest.TestCase):
    def test_remove_home_plugin_can_remove_current_entry_when_uninstalling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_plugin = Path(temp_dir) / "codex-memory"
            home_plugin.mkdir()
            (home_plugin / "marker.txt").write_text("installed", encoding="utf-8")

            with mock.patch.object(install_codex_memory, "_plugin_root", return_value=home_plugin):
                kept = install_codex_memory._remove_existing_home_plugin(home_plugin)
                self.assertFalse(kept["removed"])
                self.assertEqual(kept["reason"], "already_current")
                self.assertTrue(home_plugin.exists())

                removed = install_codex_memory._remove_existing_home_plugin(
                    home_plugin,
                    remove_current=True,
                )

            self.assertTrue(removed["removed"])
            self.assertEqual(removed["mode"], "backup")
            self.assertFalse(home_plugin.exists())
            self.assertTrue(Path(str(removed["backup_path"])).exists())

    def test_home_plugin_install_reports_current_as_already_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_plugin = Path(temp_dir) / "codex-memory"
            home_plugin.mkdir()

            with (
                mock.patch.object(install_codex_memory, "_plugin_root", return_value=home_plugin),
                mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=home_plugin),
            ):
                result = install_codex_memory._ensure_home_plugin_install(
                    "auto",
                    update_existing=False,
                )

        self.assertEqual(result["status"], "already_installed")
        self.assertFalse(result["created"])

    def test_home_plugin_install_does_not_replace_other_install_without_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "current" / "codex-memory"
            home_plugin = temp_root / "home" / "codex-memory"
            plugin_root.mkdir(parents=True)
            home_plugin.mkdir(parents=True)

            with (
                mock.patch.object(install_codex_memory, "_plugin_root", return_value=plugin_root),
                mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=home_plugin),
            ):
                result = install_codex_memory._ensure_home_plugin_install(
                    "auto",
                    update_existing=False,
                )

            self.assertEqual(result["status"], "installed_elsewhere")
            self.assertIn("-UpdateExisting", result["recommended_action"])
            self.assertTrue(home_plugin.exists())


class LauncherEntrypointTests(unittest.TestCase):
    def test_project_template_prefers_codex_entrypoints(self) -> None:
        template = json.loads(
            (PROJECT_ROOT / "templates" / "project" / ".codex" / "harness" / "commands.json").read_text(
                encoding="utf-8",
            )
        )

        commands = template["commands"]
        self.assertEqual(commands["memory_check"]["command"], "codex memory check-install")
        self.assertEqual(commands["bootstrap_doctor"]["command"], "codex memory doctor")
        self.assertNotIn("py -X utf8", json.dumps(template))

    def test_generated_profile_routes_doctor_through_memory_subcommand(self) -> None:
        block = install_support.profile_block(Path("C:/Users/Test/plugins/codex-memory"))

        self.assertIn("function codex", block)
        self.assertIn("function codexm", block)
        self.assertIn("memory doctor", block)

    def test_generated_agents_prefers_codex_memory_commands(self) -> None:
        block = install_support.agents_block(Path("C:/Users/Test/plugins/codex-memory"))

        self.assertIn("codex memory doctor", block)
        self.assertIn("codex memory init", block)
        self.assertIn("codex harness verify run --profile primary", block)
        self.assertIn("codex package verify", block)
        self.assertIn("codex memory hook before_task", block)
        self.assertNotIn("codex_bootstrap.py --cwd", block)
        self.assertNotIn("hook_runner.py --event", block)

    def test_launcher_declares_memory_command_dispatcher(self) -> None:
        launcher = (PLUGIN_SCRIPTS_DIR / "codexm.ps1").read_text(encoding="utf-8")

        self.assertIn("function Invoke-MemoryCommand", launcher)
        self.assertIn("function Invoke-HarnessCommand", launcher)
        self.assertIn("function Invoke-PackageCommand", launcher)
        self.assertIn('"verify"', launcher)
        self.assertIn('"harness"', launcher)
        self.assertIn('"hook"', launcher)

    def test_launcher_respects_disable_wrapper_before_memory_dispatch(self) -> None:
        launcher = (PLUGIN_SCRIPTS_DIR / "codexm.ps1").read_text(encoding="utf-8")

        disable_check = 'if ($env:CODEX_MEMORY_DISABLE_WRAPPER -eq "1")'
        memory_dispatch = 'if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "memory")'
        self.assertLess(launcher.index(disable_check), launcher.index(memory_dispatch))
        self.assertIn("project_shared_exists", launcher)
        self.assertIn("project_shared_index_exists", launcher)


class DemoCleanupTests(unittest.TestCase):
    def test_demo_cleanup_preserves_unrelated_events(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        with tempfile.TemporaryDirectory() as temp_dir:
            task_id = f"demo-task-{os.getpid()}"
            Path(temp_dir, ".codex").mkdir()
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = temp_dir
                paths = init_storage.resolve_storage_paths(scope="project", cwd=temp_dir)
                init_storage.ensure_storage_layout(scope="project", cwd=temp_dir)
                conn = sqlite3.connect(paths.db_path)
                try:
                    conn.execute(
                        "INSERT INTO task_state (task_id, payload_json, updated_at) VALUES (?, ?, ?)",
                        (task_id, "{}", "now"),
                    )
                    conn.commit()
                finally:
                    conn.close()
                events = [
                    {"event_type": "task_state.upserted", "payload": {"task_id": task_id}},
                    {"event_type": "task_state.upserted", "payload": {"task_id": "other-task"}},
                ]
                paths.event_log_path.write_text(
                    "\n".join(json.dumps(item) for item in events) + "\n",
                    encoding="utf-8",
                )

                run_demo_flow._cleanup_task(task_id)

                remaining = paths.event_log_path.read_text(encoding="utf-8").splitlines()
                gc.collect()
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

        self.assertEqual(len(remaining), 1)
        self.assertIn("other-task", remaining[0])


class RetrievalStoreTests(unittest.TestCase):
    def test_fulltext_search_treats_glob_patterns_as_literals(self) -> None:
        calls: list[list[str]] = []

        class EmptyRgResult:
            stdout = ""
            stderr = ""
            returncode = 1

        def fake_run(args: list[str]) -> EmptyRgResult:
            calls.append(args)
            return EmptyRgResult()

        with mock.patch.object(retrieval_store, "_run_rg", side_effect=fake_run):
            items = retrieval_store.RetrievalEngine().search_fulltext("*.md")

        self.assertEqual(items, [])
        self.assertIn("-F", calls[0])
        self.assertIn("*.md", calls[0])


class SharedMemoryTests(unittest.TestCase):
    def test_promote_task_summary_writes_reviewable_shared_entry(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = str(project_root)
                store = memory_store.MemoryStore()
                store.write_task_summary("task-one", "# Stable Fact\n\nNo secrets.")

                promoted = shared_memory.promote_task(
                    project_root,
                    "task-one",
                    kind="fact",
                    title="Stable Fact",
                )
                validation = shared_memory.validate_shared(project_root)
                self.assertTrue(Path(promoted["path"]).exists())
                self.assertTrue(validation["ok"])
                self.assertEqual(len(validation["entries"]), 1)
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

class VerificationRunnerTests(unittest.TestCase):
    def test_safe_command_checks_actual_argv_even_with_display_command(self) -> None:
        spec = verification_runner.CommandSpec(
            name="danger",
            command="codex package verify",
            argv=["pwsh", "-NoProfile", "-Command", "git reset --hard"],
        )

        with self.assertRaises(ValueError):
            verification_runner.assert_safe_command(spec)

    def test_run_command_uses_argv_without_shell_by_default(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_run(command: object, **kwargs: object) -> object:
            calls.append({"command": command, **kwargs})
            return _Completed()

        spec = verification_runner.CommandSpec(
            name="sample",
            command='py -X utf8 -c "print(123)"',
        )
        with mock.patch.object(verification_runner.subprocess, "run", side_effect=fake_run):
            result = verification_runner.run_command(spec, PROJECT_ROOT, 100)

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0]["shell"], False)
        self.assertEqual(calls[0]["command"], ["py", "-X", "utf8", "-c", "print(123)"])

    def test_run_command_uses_configured_relative_cwd_inside_project(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_run(command: object, **kwargs: object) -> object:
            calls.append({"command": command, **kwargs})
            return _Completed()

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            work_dir = project_root / "client"
            work_dir.mkdir()
            spec = verification_runner.CommandSpec(
                name="sample",
                command='py -X utf8 -c "print(123)"',
                cwd="client",
            )
            with mock.patch.object(verification_runner.subprocess, "run", side_effect=fake_run):
                result = verification_runner.run_command(spec, project_root, 100)

        self.assertTrue(result["ok"])
        self.assertEqual(Path(str(calls[0]["cwd"])).name, "client")

    def test_run_command_rejects_cwd_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = verification_runner.CommandSpec(
                name="sample",
                command='py -X utf8 -c "print(123)"',
                cwd="..",
            )

            with self.assertRaises(ValueError):
                verification_runner.run_command(spec, Path(temp_dir), 100)


class BootstrapTests(unittest.TestCase):
    def test_project_command_config_uses_codex_style_entrypoints(self) -> None:
        config = codex_bootstrap._command_config(
            PROJECT_ROOT / "plugins" / "codex-memory",
            PROJECT_ROOT,
        )
        commands = config["commands"]

        self.assertEqual(commands["memory_check"]["command"], "codex memory check-install")
        self.assertEqual(commands["bootstrap_doctor"]["command"], "codex memory doctor")
        for spec in commands.values():
            self.assertNotIn("py -X utf8", spec["command"])
            self.assertIn("codexm.ps1", " ".join(spec["argv"]))

    def test_init_project_creates_shared_memory_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            actions = codex_bootstrap.init_project(
                project_root,
                PROJECT_ROOT / "plugins" / "codex-memory",
            )

            shared_dir = project_root / ".codex" / "shared"
            self.assertTrue((shared_dir / "README.md").exists())
            self.assertTrue((shared_dir / "index.json").exists())
            for name in ("decisions", "facts", "workflows", "routes"):
                self.assertTrue((shared_dir / name / ".gitkeep").exists())
            self.assertTrue(any(item["path"] == str(shared_dir) for item in actions))

    def test_doctor_is_not_ready_when_home_plugin_points_elsewhere(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "project"
            project_root.mkdir()
            (project_root / "AGENTS.md").write_text("# Project\n", encoding="utf-8")
            (project_root / ".codex" / "memories").mkdir(parents=True)
            harness_dir = project_root / ".codex" / "harness"
            harness_dir.mkdir(parents=True)
            (harness_dir / "commands.json").write_text("{}", encoding="utf-8")
            (harness_dir / "project_profile.json").write_text("{}", encoding="utf-8")

            stale_plugin = temp_root / "old-plugin"
            stale_plugin.mkdir()
            global_memory = temp_root / "global-memory"
            global_memory.mkdir()
            home_agents = temp_root / "AGENTS.md"
            home_agents.write_text("Codex Memory codex_bootstrap.py\n", encoding="utf-8")
            home_marketplace = temp_root / "marketplace.json"
            home_marketplace.write_text(
                json.dumps({"plugins": [{"name": "codex-memory"}]}),
                encoding="utf-8",
            )

            patches = [
                mock.patch.object(codex_bootstrap, "HOME_PLUGIN", stale_plugin),
                mock.patch.object(codex_bootstrap, "GLOBAL_MEMORY", global_memory),
                mock.patch.object(codex_bootstrap, "HOME_AGENTS", home_agents),
                mock.patch.object(codex_bootstrap, "HOME_MARKETPLACE", home_marketplace),
            ]
            with patches[0], patches[1], patches[2], patches[3]:
                result = codex_bootstrap.inspect_state(project_root, init=False)

        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["home_plugin_points_to_current"])
        self.assertTrue(any("UpdateExisting" in item for item in result["recommendations"]))

    def test_doctor_accepts_codex_memory_cli_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "project"
            project_root.mkdir()
            (project_root / ".codex" / "memories").mkdir(parents=True)
            harness_dir = project_root / ".codex" / "harness"
            harness_dir.mkdir(parents=True)
            (harness_dir / "commands.json").write_text("{}", encoding="utf-8")
            (harness_dir / "project_profile.json").write_text("{}", encoding="utf-8")

            home_agents = temp_root / "AGENTS.md"
            home_agents.write_text("Codex Memory\ncodex memory doctor\n", encoding="utf-8")
            home_marketplace = temp_root / "marketplace.json"
            home_marketplace.write_text(
                json.dumps({"plugins": [{"name": "codex-memory"}]}),
                encoding="utf-8",
            )
            global_memory = temp_root / "global-memory"
            global_memory.mkdir()
            plugin_root = codex_bootstrap._plugin_root()

            patches = [
                mock.patch.object(codex_bootstrap, "HOME_PLUGIN", plugin_root),
                mock.patch.object(codex_bootstrap, "GLOBAL_MEMORY", global_memory),
                mock.patch.object(codex_bootstrap, "HOME_AGENTS", home_agents),
                mock.patch.object(codex_bootstrap, "HOME_MARKETPLACE", home_marketplace),
            ]
            with patches[0], patches[1], patches[2], patches[3]:
                result = codex_bootstrap.inspect_state(project_root, init=False)

        self.assertTrue(result["checks"]["home_agents_mentions_cli_entrypoints"])
        self.assertFalse(
            any("codex memory doctor/init" in item for item in result["recommendations"])
        )


class _Completed:
    returncode = 0
    stdout = "ok"
    stderr = ""


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
