from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import version_manager


class VersionManagerTests(unittest.TestCase):
    def test_status_accepts_matching_versions(self) -> None:
        with temp_project("0.1.1", "0.1.1") as root:
            status = version_manager.version_status(root)

        self.assertTrue(status["ok"], status)
        self.assertEqual(status["version"], "0.1.1")

    def test_status_rejects_mismatched_versions(self) -> None:
        with temp_project("0.1.1", "0.1.2") as root:
            status = version_manager.version_status(root)
            self.assertFalse(status["ok"])
            self.assertIn("version mismatch", status["errors"][0])
            with self.assertRaises(version_manager.VersionError):
                version_manager.current_version(root)

    def test_set_updates_pyproject_and_plugin_manifest(self) -> None:
        with temp_project("0.1.1", "0.1.1") as root:
            result = version_manager.set_version(root, "0.2.0")
            status = version_manager.version_status(root)

        self.assertTrue(result["changed"])
        self.assertTrue(status["ok"])
        self.assertEqual(status["version"], "0.2.0")

    def test_bump_patch_updates_all_version_sources(self) -> None:
        with temp_project("0.1.1", "0.1.1") as root:
            result = version_manager.bump_version(root, "patch")
            status = version_manager.version_status(root)

        self.assertEqual(result["version"], "0.1.2")
        self.assertEqual(status["sources"]["pyproject"], "0.1.2")
        self.assertEqual(status["sources"]["plugin_manifest"], "0.1.2")

    def test_cli_check_returns_nonzero_for_mismatch(self) -> None:
        with temp_project("0.1.1", "0.1.2") as root:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(SCRIPTS_DIR / "version_manager.py"),
                    "--project-root",
                    str(root),
                    "check",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(payload["ok"])


class temp_project:
    def __init__(self, pyproject_version: str, plugin_version: str) -> None:
        self.pyproject_version = pyproject_version
        self.plugin_version = plugin_version

    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        (root / "plugins" / "codex-memory" / ".codex-plugin").mkdir(parents=True)
        (root / "pyproject.toml").write_text(
            "[project]\n"
            'name = "codex-memory-harness"\n'
            f'version = "{self.pyproject_version}"\n',
            encoding="utf-8",
        )
        (root / "plugins" / "codex-memory" / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "codex-memory", "version": self.plugin_version}, indent=2) + "\n",
            encoding="utf-8",
        )
        return root

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.temp_dir.cleanup()
