from __future__ import annotations

import os
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


class HomePluginInstallTests(unittest.TestCase):
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

    @unittest.skipIf(os.name == "nt", "POSIX auto mode uses symlinks outside Windows.")
    def test_home_plugin_auto_uses_symlink_on_posix_for_repeatable_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "current" / "codex-memory"
            home_plugin = temp_root / "home" / "plugins" / "codex-memory"
            plugin_root.mkdir(parents=True)

            with (
                mock.patch.object(install_codex_memory, "_plugin_root", return_value=plugin_root),
                mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=home_plugin),
            ):
                first = install_codex_memory._ensure_home_plugin_install(
                    "auto",
                    update_existing=False,
                )
                second = install_codex_memory._ensure_home_plugin_install(
                    "auto",
                    update_existing=False,
                )
            home_plugin_is_symlink = home_plugin.is_symlink()

        self.assertEqual(first["mode"], "symlink")
        self.assertEqual(first["status"], "ok")
        self.assertTrue(first["created"])
        self.assertEqual(second["status"], "already_installed")
        self.assertTrue(home_plugin_is_symlink)

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
            home_plugin_exists = home_plugin.exists()

        self.assertEqual(result["status"], "installed_elsewhere")
        self.assertIn("--update-existing", result["recommended_action"])
        self.assertTrue(home_plugin_exists)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics differ on Windows.")
    def test_home_plugin_install_reports_broken_symlink_as_existing_elsewhere(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "current" / "codex-memory"
            home_plugin = temp_root / "home" / "plugins" / "codex-memory"
            broken_target = temp_root / "missing"
            plugin_root.mkdir(parents=True)
            home_plugin.parent.mkdir(parents=True)
            home_plugin.symlink_to(broken_target, target_is_directory=True)

            with (
                mock.patch.object(install_codex_memory, "_plugin_root", return_value=plugin_root),
                mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=home_plugin),
            ):
                result = install_codex_memory._ensure_home_plugin_install(
                    "auto",
                    update_existing=False,
                )
                home_plugin_is_symlink = home_plugin.is_symlink()

        self.assertEqual(result["status"], "installed_elsewhere")
        self.assertEqual(result["resolved_path"], str(broken_target))
        self.assertTrue(home_plugin_is_symlink)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics differ on Windows.")
    def test_home_plugin_update_replaces_broken_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "current" / "codex-memory"
            home_plugin = temp_root / "home" / "plugins" / "codex-memory"
            plugin_root.mkdir(parents=True)
            home_plugin.parent.mkdir(parents=True)
            home_plugin.symlink_to(temp_root / "missing", target_is_directory=True)

            with (
                mock.patch.object(install_codex_memory, "_plugin_root", return_value=plugin_root),
                mock.patch.object(install_codex_memory, "_home_plugin_path", return_value=home_plugin),
            ):
                result = install_codex_memory._ensure_home_plugin_install(
                    "auto",
                    update_existing=True,
                )
                resolved = home_plugin.resolve()

        self.assertEqual(result["mode"], "symlink")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["replacement"]["mode"], "symlink")
        self.assertEqual(resolved, plugin_root)


if __name__ == "__main__":
    unittest.main()
