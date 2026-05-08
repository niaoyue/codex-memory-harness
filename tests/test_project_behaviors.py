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
                manifest = json.loads(archive.read("PACKAGE_MANIFEST.json").decode("utf-8"))

        self.assertNotIn(".codex/harness/commands.json", names)
        self.assertNotIn(".codex/harness/project_profile.json", names)
        self.assertFalse(any(name.startswith(".codex/") for name in names))
        self.assertIn(".github/workflows/verify.yml", names)
        self.assertFalse(any(name.startswith("dist/") for name in names))
        self.assertFalse(any("__pycache__/" in name for name in names))
        self.assertFalse(any(name.endswith(".pyc") for name in names))
        self.assertFalse(any(name.endswith("memory.db") for name in names))
        self.assertFalse(any(name.endswith("events.jsonl") for name in names))
        self.assertIn("templates/project/.codex/harness/commands.json", names)
        self.assertIn("templates/project/.codex/shared/README.md", names)
        self.assertIn("templates/project/.codex/agents/workspace-coordinator.toml", names)
        self.assertIn("templates/project/.codex/agents/xhigh-review-runner.toml", names)
        self.assertIn("install.bat", manifest["install"])
        self.assertIn("install.sh", manifest["install"])
        self.assertIn("--skip-skills", manifest["install"])
        self.assertIn("plugins/codex-memory/skills/bundled-skills.json", names)
        self.assertIn("plugins/codex-memory/skills/local/harness-release-gate/SKILL.md", names)
        self.assertIn("plugins/codex-memory/skills/openai-curated/security-threat-model/SKILL.md", names)
        self.assertIn("plugins/codex-memory/skills/openai-curated/gh-fix-ci/scripts/inspect_pr_checks.py", names)


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
            argv_text = " ".join(spec["argv"])
            if os.name == "nt":
                self.assertIn("codexm.ps1", argv_text)
            else:
                self.assertIn("codexm.sh", argv_text)

    def test_workspace_routing_project_id_is_ascii_for_non_ascii_project_names(self) -> None:
        config = codex_bootstrap._workspace_routing_config(Path("\u5ba2\u6237\u9879\u76ee"))
        project_id = config["projects"][0]["id"]

        self.assertRegex(project_id, r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
        self.assertTrue(all(ord(ch) < 128 for ch in project_id))
        self.assertRegex(project_id, r"^workspace_meta-project-[0-9a-f]{8}$")

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
            agents_dir = project_root / ".codex" / "agents"
            self.assertTrue((agents_dir / "workspace-coordinator.toml").exists())
            self.assertTrue((agents_dir / "implementation-specialist.toml").exists())
            self.assertTrue((agents_dir / "route-review-specialist.toml").exists())
            self.assertTrue((agents_dir / "xhigh-review-runner.toml").exists())
            self.assertTrue(any(item["path"] == str(shared_dir) for item in actions))
            harness_dir = project_root / ".codex" / "harness"
            profile = json.loads((harness_dir / "project_profile.json").read_text(encoding="utf-8"))
            workspace_routing = json.loads((harness_dir / "workspace-routing.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["subagent_runtime_policy"]["execution_model"], "host_subagent_or_manual")
            self.assertEqual(workspace_routing["subagent_runtime_policy"]["execution_model"], "host_subagent_or_manual")
            self.assertEqual(workspace_routing["projects"][0]["domain"], "workspace_meta")

    def test_init_project_adds_missing_subagent_runtime_policy_to_existing_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            harness_dir = project_root / ".codex" / "harness"
            harness_dir.mkdir(parents=True)
            (harness_dir / "project_profile.json").write_text('{"version": 1}\n', encoding="utf-8")
            actions = codex_bootstrap.init_project(project_root, PROJECT_ROOT / "plugins" / "codex-memory")

            profile = json.loads((harness_dir / "project_profile.json").read_text(encoding="utf-8"))

        self.assertEqual(profile["subagent_runtime_policy"]["execution_model"], "host_subagent_or_manual")
        self.assertTrue(any(item["action"] == "add_subagent_runtime_policy" for item in actions))

    def test_init_project_keeps_existing_nested_subagent_runtime_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            harness_dir = project_root / ".codex" / "harness"
            harness_dir.mkdir(parents=True)
            nested_policy = {
                "execution_model": "main_agent_serial",
                "reason": "Nested profile disables SubAgent runtime.",
            }
            (harness_dir / "project_profile.json").write_text(
                json.dumps({"version": 1, "harness": {"subagent_runtime_policy": nested_policy}}, ensure_ascii=False),
                encoding="utf-8",
            )
            actions = codex_bootstrap.init_project(project_root, PROJECT_ROOT / "plugins" / "codex-memory")

            profile = json.loads((harness_dir / "project_profile.json").read_text(encoding="utf-8"))

        self.assertNotIn("subagent_runtime_policy", profile)
        self.assertEqual(profile["harness"]["subagent_runtime_policy"], nested_policy)
        self.assertTrue(any(item["action"] == "keep_existing_subagent_runtime_policy" for item in actions))

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
        self.assertTrue(any("install.bat --update-existing" in item for item in result["recommendations"]))

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
