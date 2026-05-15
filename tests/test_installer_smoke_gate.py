from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import install_codex_memory
import install_support
import verify_project


class InstallerSmokeGateTests(unittest.TestCase):
    def test_home_root_can_be_overridden_for_isolated_install_smoke(self) -> None:
        old_home = os.environ.get("CODEX_MEMORY_HOME")
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.environ["CODEX_MEMORY_HOME"] = temp_dir

                self.assertEqual(install_support.home_root(), Path(temp_dir))
                self.assertEqual(
                    install_codex_memory._home_marketplace_path(),
                    Path(temp_dir) / ".agents" / "plugins" / "marketplace.json",
                )
            finally:
                _restore_env("CODEX_MEMORY_HOME", old_home)

    def test_project_verifier_runs_real_batch_install_from_release_package(self) -> None:
        verifier = (PROJECT_ROOT / "scripts" / "verify_project.py").read_text(encoding="utf-8")

        self.assertIn("run_installer_smoke_test", verifier)
        self.assertIn('"cmd", "/c", "install.bat"', verifier)
        self.assertIn('"cmd", "/c", "uninstall.bat"', verifier)
        self.assertIn("CODEX_MEMORY_HOME", verifier)
        self.assertIn("CODEX_MEMORY_CWD", verifier)
        self.assertIn("PYTHONDONTWRITEBYTECODE", verifier)
        self.assertIn("BEHAVIOR_TEST_TIMEOUT_SECONDS", verifier)
        self.assertIn("compile(source", verifier)
        self.assertNotIn("py_compile", verifier)
        self.assertIn("harness-release-gate", verifier)
        self.assertIn("version_check", verifier)

    def test_installer_smoke_reports_release_build_failure(self) -> None:
        with (
            mock.patch.object(verify_project.os, "name", "nt"),
            mock.patch.object(verify_project.build_release, "build", side_effect=RuntimeError("version mismatch")),
        ):
            result = verify_project.run_installer_smoke_test()

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("version mismatch", result["failures"][0])


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
