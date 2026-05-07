from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import profile_blocks
import profile_install


class ProfileInstallTests(unittest.TestCase):
    def test_uninstall_profile_shells_none_preserves_posix_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            home = Path(temp_dir)
            profile = home / ".profile"
            original = profile_blocks.posix_profile_block(Path("/tmp/codex-memory"))
            profile.write_text(original, encoding="utf-8")
            try:
                os.environ["CODEX_MEMORY_HOME"] = str(home)
                result = profile_install.remove_launcher_profiles("none")
                after = profile.read_text(encoding="utf-8")
            finally:
                if old_home is None:
                    os.environ.pop("CODEX_MEMORY_HOME", None)
                else:
                    os.environ["CODEX_MEMORY_HOME"] = old_home

        self.assertEqual(after, original)
        self.assertEqual(result["powershell_profiles"], [])
        self.assertEqual(result["posix_profiles"], [])

    def test_uninstall_posix_selector_only_removes_matching_posix_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            home = Path(temp_dir)
            bashrc = home / ".bashrc"
            profile = home / ".profile"
            zshrc = home / ".zshrc"
            pwsh = home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
            posix_block = profile_blocks.posix_profile_block(Path("/tmp/codex-memory"))
            powershell_block = profile_blocks.profile_block(Path("/tmp/codex-memory"))
            bashrc.write_text(posix_block, encoding="utf-8")
            profile.write_text(posix_block, encoding="utf-8")
            zshrc.write_text(posix_block, encoding="utf-8")
            pwsh.parent.mkdir(parents=True)
            pwsh.write_text(powershell_block, encoding="utf-8")
            try:
                os.environ["CODEX_MEMORY_HOME"] = str(home)
                result = profile_install.remove_launcher_profiles("bash", "posix")
                bash_after = bashrc.read_text(encoding="utf-8")
                profile_after = profile.read_text(encoding="utf-8")
                zsh_after = zshrc.read_text(encoding="utf-8")
                pwsh_after = pwsh.read_text(encoding="utf-8")
            finally:
                if old_home is None:
                    os.environ.pop("CODEX_MEMORY_HOME", None)
                else:
                    os.environ["CODEX_MEMORY_HOME"] = old_home

        self.assertEqual(bash_after, "")
        self.assertEqual(profile_after, posix_block)
        self.assertEqual(zsh_after, posix_block)
        self.assertEqual(pwsh_after, powershell_block)
        self.assertEqual(result["powershell_profiles"], [])
        self.assertEqual(len(result["posix_profiles"]), 1)

    def test_uninstall_powershell_selector_does_not_remove_posix_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            home = Path(temp_dir)
            profile = home / ".profile"
            pwsh = home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
            posix_block = profile_blocks.posix_profile_block(Path("/tmp/codex-memory"))
            powershell_block = profile_blocks.profile_block(Path("/tmp/codex-memory"))
            profile.write_text(posix_block, encoding="utf-8")
            pwsh.parent.mkdir(parents=True)
            pwsh.write_text(powershell_block, encoding="utf-8")
            try:
                os.environ["CODEX_MEMORY_HOME"] = str(home)
                result = profile_install.remove_launcher_profiles("pwsh", "posix")
                profile_after = profile.read_text(encoding="utf-8")
                pwsh_after = pwsh.read_text(encoding="utf-8")
            finally:
                if old_home is None:
                    os.environ.pop("CODEX_MEMORY_HOME", None)
                else:
                    os.environ["CODEX_MEMORY_HOME"] = old_home

        self.assertEqual(profile_after, posix_block)
        self.assertEqual(pwsh_after, "")
        self.assertEqual(len(result["powershell_profiles"]), 1)
        self.assertEqual(result["posix_profiles"], [])


if __name__ == "__main__":
    unittest.main()
