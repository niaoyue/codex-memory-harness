from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))


class PosixWrapperBootstrapTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX launcher bootstrap smoke is not for Windows.")
    def test_posix_launcher_bootstraps_before_real_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            codex_home = temp_root / "codex-home"
            project = temp_root / "project"
            bin_dir = temp_root / "bin"
            home.mkdir()
            codex_home.mkdir()
            project.mkdir()
            bin_dir.mkdir()
            (project / "README.md").write_text("# demo\n", encoding="utf-8")
            fake_codex = bin_dir / "codex"
            fake_codex.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"scope=$CODEX_MEMORY_SCOPE\"\n"
                "printf '%s\\n' \"cwd=$CODEX_MEMORY_CWD\"\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "CODEX_MEMORY_HOME": str(home),
                    "CODEX_HOME": str(codex_home),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                }
            )
            completed = self._run(["--version"], project, env)
            commands_exists = (project / ".codex" / "harness" / "commands.json").exists()

        self.assertIn("scope=project", completed.stdout)
        self.assertIn(f"cwd={project}", completed.stdout)
        self.assertTrue(commands_exists)

    @unittest.skipIf(os.name == "nt", "POSIX launcher install smoke is not for Windows.")
    def test_posix_memory_install_keeps_posix_launcher_family(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            codex_home = temp_root / "codex-home"
            home.mkdir()
            codex_home.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "CODEX_MEMORY_HOME": str(home),
                    "CODEX_HOME": str(codex_home),
                }
            )

            completed = self._run(
                ["memory", "install", "--scope", "home", "--mode", "copy", "--skip-skills", "--skip-agents", "--profile-shells", "none"],
                PROJECT_ROOT,
                env,
            )
            updated = self._run(
                ["memory", "update", "--scope", "home", "--mode", "copy", "--skip-skills", "--skip-agents", "--profile-shells", "none"],
                PROJECT_ROOT,
                env,
            )

        self.assertIn('"launcher_family": "posix"', completed.stdout)
        self.assertIn('"launcher_family": "posix"', updated.stdout)
        self.assertFalse((home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1").exists())
        self.assertFalse((home / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1").exists())

    @unittest.skipIf(os.name == "nt", "POSIX launcher profile smoke is not for Windows.")
    def test_install_sh_accepts_posix_profile_shell_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            codex_home = temp_root / "codex-home"
            home.mkdir()
            codex_home.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "CODEX_MEMORY_HOME": str(home),
                    "CODEX_HOME": str(codex_home),
                }
            )

            completed = subprocess.run(
                [
                    "sh",
                    str(PROJECT_ROOT / "install.sh"),
                    "--scope",
                    "home",
                    "--mode",
                    "copy",
                    "--skip-skills",
                    "--skip-agents",
                    "--profile-shells",
                    "bash",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            bashrc_exists = (home / ".bashrc").exists()
            profile_exists = (home / ".profile").exists()
            zshrc_exists = (home / ".zshrc").exists()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(bashrc_exists)
        self.assertFalse(profile_exists)
        self.assertFalse(zshrc_exists)
        self.assertIn('"launcher_family": "posix"', completed.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX package wrapper smoke is not for Windows.")
    def test_installed_package_verify_preserves_repo_resolution_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            codex_home = temp_root / "codex-home"
            outside = temp_root / "outside"
            package_root = temp_root / "package"
            home.mkdir()
            codex_home.mkdir()
            outside.mkdir()
            shutil.copytree(
                PROJECT_ROOT,
                package_root,
                ignore=shutil.ignore_patterns(".git", ".codex", "dist", "__pycache__"),
            )
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "CODEX_MEMORY_HOME": str(home),
                    "CODEX_HOME": str(codex_home),
                }
            )
            installed = subprocess.run(
                [
                    "sh",
                    str(package_root / "install.sh"),
                    "--scope",
                    "home",
                    "--mode",
                    "copy",
                    "--skip-skills",
                    "--skip-agents",
                    "--profile-shells",
                    "none",
                ],
                cwd=package_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            completed = subprocess.run(
                [
                    "sh",
                    str(home / "plugins" / "codex-memory" / "scripts" / "codexm.sh"),
                    "package",
                    "verify",
                ],
                cwd=outside,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(completed.returncode, 64)
        self.assertIn("Cannot find verify_project.py", completed.stderr)
        self.assertNotIn("can't find '__main__'", completed.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX review alias smoke is not for Windows.")
    def test_posix_review_alias_bootstraps_memory_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            codex_home = temp_root / "codex-home"
            project = temp_root / "project"
            bin_dir = temp_root / "bin"
            home.mkdir()
            codex_home.mkdir()
            project.mkdir()
            bin_dir.mkdir()
            (project / "README.md").write_text("# demo\n", encoding="utf-8")
            fake_codex = bin_dir / "codex"
            fake_codex.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"scope=$CODEX_MEMORY_SCOPE\"\n"
                "printf '%s\\n' \"cwd=$CODEX_MEMORY_CWD\"\n"
                "printf 'args:'\n"
                "for arg in \"$@\"; do printf ' [%s]' \"$arg\"; done\n"
                "printf '\\n'\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "CODEX_MEMORY_HOME": str(home),
                    "CODEX_HOME": str(codex_home),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                }
            )

            completed = self._run(["xhigh", "review", "--uncommitted"], project, env)
            commands_exists = (project / ".codex" / "harness" / "commands.json").exists()

        self.assertIn("scope=project", completed.stdout)
        self.assertIn(f"cwd={project}", completed.stdout)
        self.assertIn('args: [review] [-c] [model_reasoning_effort="xhigh"] [--uncommitted]', completed.stdout)
        self.assertTrue(commands_exists)

    @unittest.skipIf(os.name == "nt", "POSIX profile fallback smoke is not for Windows.")
    def test_posix_codex_raw_drops_optional_separator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            bin_dir = temp_root / "bin"
            profile = home / ".profile"
            home.mkdir()
            bin_dir.mkdir()
            fake_codex = bin_dir / "codex"
            fake_codex.write_text(
                "#!/bin/sh\n"
                "printf 'args:'\n"
                "for arg in \"$@\"; do printf ' [%s]' \"$arg\"; done\n"
                "printf '\\n'\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            # Source the generated POSIX block directly so the test covers shell behavior, not Python import.
            import profile_blocks

            profile.write_text(
                f"PATH={bin_dir}:$PATH\n"
                + profile_blocks.posix_profile_block(PROJECT_ROOT / "plugins" / "codex-memory")
                + "\n"
                + "codex-raw -- review -c 'model_reasoning_effort=\"xhigh\"' --uncommitted\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                ["sh", str(profile)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('args: [review] [-c] [model_reasoning_effort="xhigh"] [--uncommitted]', completed.stdout)
        self.assertNotIn("args: [--]", completed.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX bash profile smoke is not for Windows.")
    def test_posix_codex_raw_works_in_non_interactive_bash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            bin_dir = temp_root / "bin"
            profile = home / ".bashrc"
            home.mkdir()
            bin_dir.mkdir()
            fake_codex = bin_dir / "codex"
            fake_codex.write_text(
                "#!/bin/sh\n"
                "printf 'args:'\n"
                "for arg in \"$@\"; do printf ' [%s]' \"$arg\"; done\n"
                "printf '\\n'\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            import profile_blocks

            profile.write_text(
                f"PATH={bin_dir}:$PATH\n"
                + profile_blocks.posix_profile_block(PROJECT_ROOT / "plugins" / "codex-memory")
                + "\n"
                + "codex-raw -- review --uncommitted\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                ["bash", str(profile)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("args: [review] [--uncommitted]", completed.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX bash profile smoke is not for Windows.")
    def test_posix_profile_does_not_define_hyphen_functions_in_posix_bash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            profile = home / ".profile"
            home.mkdir()
            import profile_blocks

            profile.write_text(
                profile_blocks.posix_profile_block(PROJECT_ROOT / "plugins" / "codex-memory")
                + "\n"
                + "echo profile-loaded\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                ["bash", "--posix", str(profile)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("profile-loaded", completed.stdout)
        self.assertNotIn("not a valid identifier", completed.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX profile alias smoke is not for Windows.")
    def test_posix_profile_block_clears_existing_codex_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            home = temp_root / "home"
            plugin_root = home / "plugins" / "codex-memory"
            launcher = plugin_root / "scripts" / "codexm.sh"
            profile = home / ".profile"
            launcher.parent.mkdir(parents=True)
            launcher.write_text(
                "#!/bin/sh\n"
                "printf 'wrapper:'\n"
                "for arg in \"$@\"; do printf ' [%s]' \"$arg\"; done\n"
                "printf '\\n'\n",
                encoding="utf-8",
            )
            launcher.chmod(0o755)
            import profile_blocks

            profile.write_text(
                "alias codex='echo old-codex'\n"
                "alias codexm='echo old-codexm'\n"
                + profile_blocks.posix_profile_block(plugin_root)
                + "\n"
                + "codex memory doctor\n"
                + "codexm memory check-install\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                ["sh", str(profile)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("wrapper: [memory] [doctor]", completed.stdout)
        self.assertIn("wrapper: [memory] [check-install]", completed.stdout)
        self.assertNotIn("old-codex", completed.stdout)

    def _run(
        self,
        args: list[str],
        cwd: Path,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["sh", str(PLUGIN_SCRIPTS_DIR / "codexm.sh"), *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed


if __name__ == "__main__":
    unittest.main()
