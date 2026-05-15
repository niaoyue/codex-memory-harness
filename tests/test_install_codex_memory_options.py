from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import install_codex_memory


class InstallOptionsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
