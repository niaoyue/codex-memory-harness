from __future__ import annotations

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
import mcp_config


class InstallLauncherConfigTests(unittest.TestCase):
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

    def test_mcp_config_can_use_posix_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "codex-memory"
            plugin_root.mkdir()

            result = install_codex_memory._ensure_mcp_config(
                plugin_root,
                python_command="python3",
                python_prefix_args=[],
                launcher_family="posix",
            )
            config = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))

        server = config["mcpServers"]["codex-memory"]
        self.assertEqual(server["command"], "sh")
        self.assertEqual(
            server["args"],
            [
                "./scripts/mcp_launcher.sh",
                "--stdio",
                "--memory-scope",
                "project",
            ],
        )
        self.assertEqual(result["launcher_family"], "posix")
        self.assertNotIn("powershell", json.dumps(config))

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
        launcher = (PLUGIN_SCRIPTS_DIR / "mcp_launcher.ps1").read_text(
            encoding="utf-8",
        )

        self.assertIn('Name = "python"', launcher)
        self.assertIn('Name = "python3"', launcher)
        self.assertIn('Name = "python3.12"', launcher)
        self.assertIn("$runtime = Resolve-PythonRuntime", launcher)
        self.assertIn('$pythonArgs = @($runtime.PrefixArgs) + @("-X", "utf8", $MemoryServer)', launcher)
        self.assertNotIn("& py -X utf8", launcher)

    def test_runtime_launchers_accept_versioned_python_commands(self) -> None:
        launcher_names = [
            "codexm.ps1",
            "codexm.sh",
            "hook_launcher.ps1",
            "mcp_launcher.ps1",
            "hook_launcher.sh",
            "mcp_launcher.sh",
        ]
        for launcher_name in launcher_names:
            with self.subTest(launcher=launcher_name):
                launcher = (PLUGIN_SCRIPTS_DIR / launcher_name).read_text(encoding="utf-8")
                if launcher_name.endswith(".ps1"):
                    self.assertIn('Name = "python3.14"', launcher)
                    self.assertIn('Name = "python3.13"', launcher)
                    self.assertIn('Name = "python3.12"', launcher)
                    self.assertIn('Name = "python3.11"', launcher)
                else:
                    self.assertIn("try_python python3.14", launcher)
                    self.assertIn("try_python python3.13", launcher)
                    self.assertIn("try_python python3.12", launcher)
                    self.assertIn("try_python python3.11", launcher)

    def test_mcp_config_default_stays_powershell_for_windows_installers(self) -> None:
        payload = mcp_config.mcp_config()
        server = payload["mcpServers"]["codex-memory"]

        self.assertEqual(server["command"], "powershell")
        self.assertIn("./scripts/mcp_launcher.ps1", server["args"])


if __name__ == "__main__":
    unittest.main()
