from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import install_codex_memory
import install_status
import install_support
import profile_install


class InstallerTests(unittest.TestCase):
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
        self.assertIn("apt-get install -y python3.11", script)
        self.assertIn("dnf install -y python3.12", script)
        self.assertIn("try_python python3.12", script)
        self.assertIn("require_launcher_family", script)
        self.assertIn("CODEX_MEMORY_LAUNCHER_FAMILY", script)
        self.assertIn("--launcher-family", script)
        self.assertIn("--launcher-family=*", script)
        self.assertIn("-LauncherFamily", script)
        self.assertIn("posix", script)
        self.assertIn("MINGW*|MSYS*|CYGWIN*", script)
        self.assertNotIn("currently supports POSIX shells only when the powershell command is available", script)
        self.assertLess(script.index('try_python py "-3"'), script.index('try_python python3 ""'))
        self.assertIn("--mcp-python-command", script)
        self.assertIn("--mcp-python-prefix-arg", script)
        self.assertIn("-SkipSkills", script)
        self.assertIn("--skip-skills", script)

    def test_install_writes_posix_profile_for_posix_launcher_family(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(profile_install, "ensure_profile", return_value=[]) as ensure_profile,
            mock.patch.object(profile_install, "ensure_posix_profile", return_value=[{"status": "updated"}]) as ensure_posix_profile,
            mock.patch.object(install_codex_memory, "_ensure_hooks_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_ensure_mcp_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            result = install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
                install_skills=False,
                mcp_python_command="python3",
                mcp_python_prefix_args=[],
                launcher_family="posix",
            )

        ensure_profile.assert_not_called()
        ensure_posix_profile.assert_called_once()
        self.assertEqual(ensure_posix_profile.call_args.args[1], "none")
        self.assertEqual(result["powershell_profiles"]["reason"], "launcher_family_posix")
        self.assertEqual(result["posix_profiles"], [{"status": "updated"}])

    def test_install_skips_posix_profile_for_powershell_launcher_family(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(profile_install, "ensure_profile", return_value=[]),
            mock.patch.object(profile_install, "ensure_posix_profile") as ensure_posix_profile,
            mock.patch.object(install_codex_memory, "_ensure_hooks_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_ensure_mcp_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            result = install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
                install_skills=False,
                launcher_family="powershell",
            )

        ensure_posix_profile.assert_not_called()
        self.assertEqual(result["posix_profiles"]["reason"], "launcher_family_not_posix")

    @unittest.skipIf(shutil.which("powershell"), "This check requires powershell to be absent.")
    @unittest.skipUnless(shutil.which("sh"), "POSIX shell is required for install.sh validation.")
    def test_shell_install_script_rejects_explicit_powershell_launcher_without_powershell(self) -> None:
        completed = subprocess.run(
            [
                shutil.which("sh") or "sh",
                str(PROJECT_ROOT / "install.sh"),
                "--check",
                "--launcher-family",
                "powershell",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 125)
        self.assertIn("powershell command on PATH", completed.stderr)

    def test_check_state_reports_dependency_guidance(self) -> None:
        with (
            mock.patch.object(install_support.shutil, "which", return_value=None),
            mock.patch.object(install_codex_memory, "_repo_marketplace_path", return_value=Path("missing-repo.json")),
            mock.patch.object(install_codex_memory, "_home_marketplace_path", return_value=Path("missing-home.json")),
            mock.patch.object(install_codex_memory, "_plugin_root", return_value=Path("missing-plugin")),
            mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=Path("missing-home-plugin")),
            mock.patch.object(install_status, "home_agents_path", return_value=Path("missing-agents.md")),
            mock.patch.object(install_status, "profile_statuses", return_value=[]),
            mock.patch.object(install_status, "posix_profile_statuses", return_value=[{"has_launcher": False}]),
            mock.patch.object(install_status, "bundled_skills_status", return_value={"skills": []}),
        ):
            state = install_codex_memory._check_state()

        self.assertIn("dependencies", state)
        self.assertNotIn("py_launcher", state["missing_dependencies"])
        self.assertIn("python_launcher", state["missing_dependencies"])
        self.assertIn("codex_cli", state["missing_dependencies"])
        self.assertNotIn("powershell", state["missing_dependencies"])
        self.assertEqual(state["posix_profiles"], [{"has_launcher": False}])
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
        self.assertNotIn("powershell", status["missing"])

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

    def test_install_enables_required_codex_config(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}) as ensure_config,
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_launcher_profiles", return_value={"powershell_profiles": [], "posix_profiles": []}),
            mock.patch.object(install_codex_memory, "_ensure_hooks_config", return_value={"modified": True}) as ensure_hooks_config,
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
        ensure_hooks_config.assert_called_once()
        ensure_mcp_config.assert_called_once()
        ensure_skills.assert_called_once()
        self.assertTrue(result["codex_config"]["modified"])

    def test_install_passes_selected_python_runtime_to_mcp_config(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_launcher_profiles", return_value={"powershell_profiles": [], "posix_profiles": []}),
            mock.patch.object(install_codex_memory, "_ensure_hooks_config", return_value={"modified": True}) as ensure_hooks_config,
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
        ensure_hooks_config.assert_called_once()
        self.assertEqual(ensure_mcp_config.call_args.kwargs["python_command"], "python")
        self.assertEqual(ensure_mcp_config.call_args.kwargs["python_prefix_args"], [])
        self.assertEqual(ensure_mcp_config.call_args.kwargs["launcher_family"], "powershell")

    def test_install_passes_posix_launcher_family_to_configs(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_launcher_profiles", return_value={"powershell_profiles": [], "posix_profiles": []}),
            mock.patch.object(install_codex_memory, "_ensure_hooks_config", return_value={"modified": True}) as ensure_hooks_config,
            mock.patch.object(install_codex_memory, "_ensure_mcp_config", return_value={"modified": True}) as ensure_mcp_config,
            mock.patch.object(install_codex_memory, "_check_state", return_value={}),
        ):
            result = install_codex_memory.install(
                "auto",
                "home",
                "none",
                install_agents=True,
                update_existing=False,
                install_skills=False,
                mcp_python_command="python3",
                mcp_python_prefix_args=[],
                launcher_family="posix",
            )

        ensure_hooks_config.assert_called_once()
        ensure_mcp_config.assert_called_once()
        self.assertEqual(ensure_hooks_config.call_args.kwargs["launcher_family"], "posix")
        self.assertEqual(ensure_mcp_config.call_args.kwargs["launcher_family"], "posix")
        self.assertEqual(result["launcher_family"], "posix")

    def test_install_still_repairs_codex_config_when_home_plugin_is_installed_elsewhere(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}) as ensure_config,
            mock.patch.object(install_codex_memory, "_ensure_hooks_config") as ensure_hooks_config,
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

        ensure_config.assert_called_once()
        ensure_hooks_config.assert_not_called()
        self.assertTrue(result["codex_config"]["modified"])
        self.assertEqual(result["bundled_skills"]["reason"], "installed_elsewhere")

    def test_install_can_skip_bundled_skills(self) -> None:
        with (
            mock.patch.object(install_codex_memory, "_ensure_home_plugin_install", return_value={"status": "already_installed"}),
            mock.patch.object(install_codex_memory, "ensure_codex_config", return_value={"modified": True}),
            mock.patch.object(install_codex_memory, "_upsert_marketplace_entry", return_value={"updated": True}),
            mock.patch.object(install_codex_memory, "ensure_agents", return_value={"status": "updated"}),
            mock.patch.object(install_codex_memory, "ensure_launcher_profiles", return_value={"powershell_profiles": [], "posix_profiles": []}),
            mock.patch.object(install_codex_memory, "_ensure_hooks_config", return_value={"modified": True}),
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

def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
