from __future__ import annotations

import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import install_codex_memory
import install_support
import skill_bundle


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
            self.assertIn("install.bat --update-existing", result["recommended_action"])
            self.assertTrue(home_plugin.exists())

    def test_install_script_reports_missing_python_dependency(self) -> None:
        script = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")

        self.assertIn("Resolve-PythonRuntime", script)
        self.assertIn("Get-Command $candidate.Name", script)
        self.assertIn("Python 3.11 or newer is required", script)
        self.assertIn("winget install --id Python.Python.3.12", script)
        self.assertIn("Add python.exe to PATH", script)
        self.assertIn('Name = "python3.12"', script)
        self.assertIn("& $PythonRuntime.Command", script)
        self.assertIn("[switch]$SkipSkills", script)
        self.assertIn("--skip-skills", script)

    def test_batch_install_script_checks_python_and_can_offer_winget(self) -> None:
        script = (PROJECT_ROOT / "install.bat").read_text(encoding="utf-8")

        self.assertIn("install_codex_memory.py", script)
        self.assertIn("Python 3.11 or newer is required", script)
        self.assertIn("--install-python", script)
        self.assertIn("winget install --id Python.Python.3.12", script)
        self.assertIn("--mcp-python-command", script)
        self.assertIn("--mcp-python-prefix-arg", script)
        self.assertIn('call :try_python "python3.12"', script)
        self.assertIn("-UpdateExisting", script)
        self.assertIn("--update-existing", script)
        self.assertIn("-SkipSkills", script)
        self.assertIn("--skip-skills", script)

    def test_shell_install_script_checks_python_and_can_offer_package_managers(self) -> None:
        script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("install_codex_memory.py", script)
        self.assertIn("Python 3.11 or newer is required", script)
        self.assertIn("--install-python", script)
        self.assertIn("brew install python@3.12", script)
        self.assertIn("apt-get install -y python3.12", script)
        self.assertIn("dnf install -y python3.12", script)
        self.assertIn("try_python python3.12", script)
        self.assertIn("require_powershell_launcher", script)
        self.assertIn("powershell command is available", script)
        self.assertLess(script.index('try_python py "-3"'), script.index('try_python python3 ""'))
        self.assertIn("--mcp-python-command", script)
        self.assertIn("--mcp-python-prefix-arg", script)
        self.assertIn("-SkipSkills", script)
        self.assertIn("--skip-skills", script)

    def test_check_state_reports_dependency_guidance(self) -> None:
        with (
            mock.patch.object(install_support.shutil, "which", return_value=None),
            mock.patch.object(install_codex_memory, "_repo_marketplace_path", return_value=Path("missing-repo.json")),
            mock.patch.object(install_codex_memory, "_home_marketplace_path", return_value=Path("missing-home.json")),
            mock.patch.object(install_codex_memory, "_plugin_root", return_value=Path("missing-plugin")),
            mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=Path("missing-home-plugin")),
            mock.patch.object(install_codex_memory, "home_agents_path", return_value=Path("missing-agents.md")),
            mock.patch.object(install_codex_memory, "profile_statuses", return_value=[]),
            mock.patch.object(install_codex_memory, "bundled_skills_status", return_value={"skills": []}),
        ):
            state = install_codex_memory._check_state()

        self.assertIn("dependencies", state)
        self.assertNotIn("py_launcher", state["missing_dependencies"])
        self.assertIn("python_launcher", state["missing_dependencies"])
        self.assertIn("codex_cli", state["missing_dependencies"])
        self.assertTrue(any("Python 3.11+" in item for item in state["dependency_recommendations"]))

    def test_dependency_status_accepts_python_launcher_without_py(self) -> None:
        def fake_which(command: str) -> str | None:
            paths = {
                "python": "C:/Python/python.exe",
                "codex": "C:/Tools/codex.cmd",
                "pwsh": "C:/Program Files/PowerShell/pwsh.exe",
            }
            return paths.get(command)

        with mock.patch.object(install_support.shutil, "which", side_effect=fake_which):
            status = install_support.dependency_status()

        self.assertFalse(status["py_launcher"]["ok"])
        self.assertNotIn("py_launcher", status["missing"])
        self.assertNotIn("python_launcher", status["missing"])
        self.assertNotIn("codex_cli", status["missing"])

    def test_dependency_status_accepts_versioned_python_launcher(self) -> None:
        def fake_which(command: str) -> str | None:
            paths = {
                "python3.12": "/usr/bin/python3.12",
                "codex": "/usr/local/bin/codex",
                "pwsh": "/usr/local/bin/pwsh",
            }
            return paths.get(command)

        with mock.patch.object(install_support.shutil, "which", side_effect=fake_which):
            status = install_support.dependency_status()

        self.assertNotIn("python_launcher", status["missing"])
        self.assertIn({"command": "python3.12", "path": "/usr/bin/python3.12"}, status["python"]["launchers"])

    def test_mcp_runtime_prefers_py_when_available(self) -> None:
        def fake_which(command: str) -> str | None:
            paths = {
                "py": "C:/Windows/py.exe",
                "python": "C:/Python/python.exe",
            }
            return paths.get(command)

        with (
            mock.patch.object(install_support.shutil, "which", side_effect=fake_which),
            mock.patch.object(install_support, "_python_runtime_ok", return_value=True),
        ):
            runtime = install_support.select_mcp_python_runtime()

        self.assertEqual(runtime["command"], "py")
        self.assertEqual(runtime["prefix_args"], ["-3"])

    def test_mcp_runtime_falls_back_to_python_when_py_version_is_invalid(self) -> None:
        def fake_which(command: str) -> str | None:
            paths = {
                "py": "C:/Windows/py.exe",
                "python": "C:/Python/python.exe",
            }
            return paths.get(command)

        def fake_runtime_ok(command: str, prefix_args: list[str]) -> bool:
            return command == "python" and prefix_args == []

        with (
            mock.patch.object(install_support.shutil, "which", side_effect=fake_which),
            mock.patch.object(install_support, "_python_runtime_ok", side_effect=fake_runtime_ok),
        ):
            runtime = install_support.select_mcp_python_runtime()

        self.assertEqual(runtime["command"], "python")
        self.assertEqual(runtime["prefix_args"], [])

    def test_mcp_runtime_accepts_versioned_python_command(self) -> None:
        def fake_which(command: str) -> str | None:
            return "/usr/bin/python3.12" if command == "python3.12" else None

        def fake_runtime_ok(command: str, prefix_args: list[str]) -> bool:
            return command == "python3.12" and prefix_args == []

        with (
            mock.patch.object(install_support.shutil, "which", side_effect=fake_which),
            mock.patch.object(install_support, "_python_runtime_ok", side_effect=fake_runtime_ok),
        ):
            runtime = install_support.select_mcp_python_runtime()

        self.assertEqual(runtime["command"], "python3.12")
        self.assertEqual(runtime["prefix_args"], [])

    def test_mcp_config_uses_launcher_when_py_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "codex-memory"
            plugin_root.mkdir()

            result = install_codex_memory._ensure_mcp_config(
                plugin_root,
                python_command="python",
                python_prefix_args=[],
            )
            config = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))

        server = config["mcpServers"]["codex-memory"]
        self.assertTrue(result["modified"])
        self.assertEqual(server["command"], "powershell")
        self.assertEqual(
            server["args"],
            [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "./scripts/mcp_launcher.ps1",
                "--stdio",
                "--memory-scope",
                "project",
            ],
        )
        self.assertNotEqual(server["command"], "py")
        self.assertEqual(result["python_command"], "python")
        self.assertNotIn("py -X utf8", json.dumps(config))

    def test_repo_install_preserves_source_mcp_launcher_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "plugins" / "codex-memory"
            plugin_root.mkdir(parents=True)
            mcp_path = plugin_root / ".mcp.json"
            mcp_path.write_text(
                json.dumps(install_codex_memory._mcp_config(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            before = mcp_path.read_text(encoding="utf-8")

            with (
                mock.patch.object(install_codex_memory, "_plugin_root", return_value=plugin_root),
                mock.patch.object(
                    install_codex_memory,
                    "_repo_marketplace_path",
                    return_value=temp_root / ".agents" / "plugins" / "marketplace.json",
                ),
                mock.patch.object(install_codex_memory, "_check_state", return_value={}),
            ):
                result = install_codex_memory.install(
                    "auto",
                    "repo",
                    "none",
                    install_agents=True,
                    update_existing=False,
                    install_skills=False,
                    mcp_python_command="python",
                    mcp_python_prefix_args=[],
                )

            after = mcp_path.read_text(encoding="utf-8")

        self.assertEqual(after, before)
        self.assertFalse(result["mcp_config"]["modified"])
        self.assertEqual(result["mcp_config"]["command"], "powershell")
        self.assertIn("./scripts/mcp_launcher.ps1", result["mcp_config"]["args"])

    def test_mcp_launcher_can_resolve_python_without_py_launcher(self) -> None:
        launcher = (PROJECT_ROOT / "plugins" / "codex-memory" / "scripts" / "mcp_launcher.ps1").read_text(
            encoding="utf-8",
        )

        self.assertIn('Name = "python"', launcher)
        self.assertIn('Name = "python3"', launcher)
        self.assertIn('Name = "python3.12"', launcher)
        self.assertIn("$runtime = Resolve-PythonRuntime", launcher)
        self.assertIn('$pythonArgs = @($runtime.PrefixArgs) + @("-X", "utf8", $MemoryServer)', launcher)
        self.assertNotIn("& py -X utf8", launcher)

    def test_runtime_launchers_accept_versioned_python_commands(self) -> None:
        launcher_names = ["codexm.ps1", "hook_launcher.ps1", "mcp_launcher.ps1"]
        for launcher_name in launcher_names:
            with self.subTest(launcher=launcher_name):
                launcher = (PLUGIN_SCRIPTS_DIR / launcher_name).read_text(encoding="utf-8")
                self.assertIn('Name = "python3.14"', launcher)
                self.assertIn('Name = "python3.13"', launcher)
                self.assertIn('Name = "python3.12"', launcher)
                self.assertIn('Name = "python3.11"', launcher)

    def test_install_enables_required_codex_config(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}) as ensure_config,
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_profile", return_value=[]),
            mock.patch.object(install_codex_memory, "_ensure_mcp_config", return_value={"modified": True}) as ensure_mcp_config,
            mock.patch.object(install_codex_memory, "ensure_bundled_skills", return_value={"installed": 0}) as ensure_skills,
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            result = install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
                install_skills=True,
            )

        ensure_config.assert_called_once()
        ensure_mcp_config.assert_called_once()
        ensure_skills.assert_called_once()
        self.assertTrue(result["codex_config"]["modified"])

    def test_install_passes_selected_python_runtime_to_mcp_config(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_profile", return_value=[]),
            mock.patch.object(install_codex_memory, "_ensure_mcp_config", return_value={"modified": True}) as ensure_mcp_config,
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
                install_skills=False,
                mcp_python_command="python",
                mcp_python_prefix_args=[],
            )

        ensure_mcp_config.assert_called_once()
        self.assertEqual(ensure_mcp_config.call_args.kwargs["python_command"], "python")
        self.assertEqual(ensure_mcp_config.call_args.kwargs["python_prefix_args"], [])

    def test_install_skips_codex_config_when_home_plugin_is_installed_elsewhere(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "ensure_codex_config") as ensure_config,
            mock.patch.object(
                install_codex_memory,
                "_ensure_home_plugin_install",
                return_value={"status": "installed_elsewhere"},
            ),
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            result = install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
                install_skills=True,
            )

        ensure_config.assert_not_called()
        self.assertEqual(result["codex_config"]["reason"], "installed_elsewhere")
        self.assertTrue(result["codex_config"]["skipped"])
        self.assertEqual(result["bundled_skills"]["reason"], "installed_elsewhere")

    def test_install_can_skip_bundled_skills(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_profile", return_value=[]),
            mock.patch.object(install_codex_memory, "_ensure_mcp_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "ensure_bundled_skills") as ensure_skills,
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            result = install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
                install_skills=False,
            )

        ensure_skills.assert_not_called()
        self.assertEqual(result["bundled_skills"]["reason"], "skip_skills")

    def test_bundled_skills_status_uses_vendored_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_home = Path(temp_dir)
            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_home / ".codex")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=temp_home):
                    status = skill_bundle.bundled_skills_status(PROJECT_ROOT / "plugins" / "codex-memory")
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        names = {item["name"] for item in status["skills"]}
        self.assertEqual(status["source_ref"], "af9b54f235d0d56c6b4410be54d578b0fda4ddfc")
        self.assertIn("security-threat-model", names)
        self.assertIn("gh-fix-ci", names)
        self.assertIn("harness-release-gate", names)
        self.assertIn(".agents", status["target_root"])
        self.assertIn(".codex", status["legacy_target_root"])
        self.assertEqual(status["source_missing_count"], 0)
        self.assertEqual(status["missing_count"], 7)

    def test_ensure_bundled_skills_copies_missing_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "plugin"
            source_root = plugin_root / "skills" / "openai-curated"
            for name in ("fresh-skill", "existing-skill"):
                skill_dir = source_root / name
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
            (plugin_root / "skills" / "bundled-skills.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source_ref": "test-ref",
                        "installed_by_default": True,
                        "skills": [{"name": "fresh-skill"}, {"name": "existing-skill"}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = temp_root / "home"
            existing = home / ".agents" / "skills" / "existing-skill"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("# user copy\n", encoding="utf-8")

            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_root / "codex-home")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=home):
                    result = skill_bundle.ensure_bundled_skills(plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

            self.assertEqual(result["installed"], 1)
            self.assertEqual(result["skipped_existing"], 1)
            self.assertTrue((home / ".agents" / "skills" / "fresh-skill" / "SKILL.md").exists())
            self.assertEqual((existing / "SKILL.md").read_text(encoding="utf-8"), "# user copy\n")


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
