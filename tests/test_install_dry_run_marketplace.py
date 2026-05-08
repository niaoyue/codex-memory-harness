from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import install_codex_memory
import install_marketplace


class InstallDryRunMarketplaceTests(unittest.TestCase):
    def test_install_dry_run_blocks_invalid_marketplace_plugins_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "marketplace.json"
            for payload in ({"plugins": {}}, {"plugins": ["codex-memory"]}):
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")

                    result = install_marketplace.marketplace_plan(
                        path,
                        default_name="local-user-plugins",
                        default_display_name="Local User Plugins",
                        source_path="./plugins/codex-memory",
                    )

                    self.assertTrue(result["blocked"])
                    self.assertEqual(result["status"], "invalid_plugins")

    def test_install_dry_run_blocks_invalid_marketplace_interface_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "marketplace.json"
            path.write_text(
                json.dumps({"interface": "Local User Plugins", "plugins": []}),
                encoding="utf-8",
            )

            result = install_marketplace.marketplace_plan(
                path,
                default_name="local-user-plugins",
                default_display_name="Local User Plugins",
                source_path="./plugins/codex-memory",
            )

        self.assertTrue(result["blocked"])
        self.assertEqual(result["status"], "invalid_interface")

    def test_install_dry_run_allows_missing_marketplace_plugins_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "marketplace.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "local-user-plugins",
                        "interface": {"displayName": "Local User Plugins"},
                    }
                ),
                encoding="utf-8",
            )

            result = install_marketplace.marketplace_plan(
                path,
                default_name="local-user-plugins",
                default_display_name="Local User Plugins",
                source_path="./plugins/codex-memory",
            )

        self.assertEqual(result["status"], "entry_missing")
        self.assertEqual(result["action"], "add_entry")
        self.assertTrue(result["would_write"])

    def test_install_dry_run_blocks_non_object_marketplace_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "marketplace.json"
            path.write_text(json.dumps([]), encoding="utf-8")

            result = install_marketplace.marketplace_plan(
                path,
                default_name="local-user-plugins",
                default_display_name="Local User Plugins",
                source_path="./plugins/codex-memory",
            )

        self.assertTrue(result["blocked"])
        self.assertEqual(result["status"], "invalid_root")

    def test_install_dry_run_status_tolerates_invalid_marketplace_plugins_shape(self) -> None:
        result = _dry_run_with_home_marketplace({"plugins": ["codex-memory"]})

        self.assertEqual(result["targets"]["home_marketplace"]["status"], "invalid_plugins")
        self.assertFalse(result["check"]["home_marketplace"]["parse_ok"])

    def test_install_dry_run_status_tolerates_invalid_marketplace_interface_shape(self) -> None:
        result = _dry_run_with_home_marketplace({"interface": "Local User Plugins", "plugins": []})

        self.assertEqual(result["targets"]["home_marketplace"]["status"], "invalid_interface")
        self.assertFalse(result["check"]["home_marketplace"]["parse_ok"])


def _dry_run_with_home_marketplace(payload: object) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        home_root = Path(temp_dir)
        marketplace = home_root / ".agents" / "plugins" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(json.dumps(payload), encoding="utf-8")
        old_home = os.environ.get("CODEX_MEMORY_HOME")
        os.environ["CODEX_MEMORY_HOME"] = str(home_root)
        try:
            return install_codex_memory.build_install_dry_run_plan(
                "auto",
                "home",
                "none",
                install_agents=False,
                update_existing=False,
                install_skills=False,
                mcp_python_command="python",
                mcp_python_prefix_args=[],
            )
        finally:
            if old_home is None:
                os.environ.pop("CODEX_MEMORY_HOME", None)
            else:
                os.environ["CODEX_MEMORY_HOME"] = old_home


if __name__ == "__main__":
    raise SystemExit(unittest.main())
