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

    def test_install_script_reports_missing_python_dependency(self) -> None:
        script = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")

        self.assertIn("Resolve-PythonRuntime", script)
        self.assertIn("Get-Command $candidate.Name", script)
        self.assertIn("Python 3.11 or newer is required", script)
        self.assertIn("winget install Python.Python.3.12", script)
        self.assertIn("Add python.exe to PATH", script)
        self.assertIn("& $PythonRuntime.Command", script)

    def test_check_state_reports_dependency_guidance(self) -> None:
        with (
            mock.patch.object(install_support.shutil, "which", return_value=None),
            mock.patch.object(install_codex_memory, "_repo_marketplace_path", return_value=Path("missing-repo.json")),
            mock.patch.object(install_codex_memory, "_home_marketplace_path", return_value=Path("missing-home.json")),
            mock.patch.object(install_codex_memory, "_plugin_root", return_value=Path("missing-plugin")),
            mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=Path("missing-home-plugin")),
            mock.patch.object(install_codex_memory, "home_agents_path", return_value=Path("missing-agents.md")),
            mock.patch.object(install_codex_memory, "profile_statuses", return_value=[]),
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
        self.assertIn("$runtime = Resolve-PythonRuntime", launcher)
        self.assertIn('$pythonArgs = @($runtime.PrefixArgs) + @("-X", "utf8", $MemoryServer)', launcher)
        self.assertNotIn("& py -X utf8", launcher)

    def test_install_enables_required_codex_config(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}) as ensure_config,
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_profile", return_value=[]),
            mock.patch.object(install_codex_memory, "_ensure_mcp_config", return_value={"modified": True}) as ensure_mcp_config,
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            result = install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
            )

        ensure_config.assert_called_once()
        ensure_mcp_config.assert_called_once()
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
            )

        ensure_config.assert_not_called()
        self.assertEqual(result["codex_config"]["reason"], "installed_elsewhere")
        self.assertTrue(result["codex_config"]["skipped"])


if __name__ == "__main__":
    unittest.main()
