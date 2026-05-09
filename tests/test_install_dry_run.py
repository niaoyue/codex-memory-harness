from __future__ import annotations

import json
import os
import subprocess
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
import install_dry_run_targets
from install_support import AGENTS_END, AGENTS_START, PROFILE_END, PROFILE_START, agents_block, profile_paths, replace_marked_block
from profile_blocks import profile_block


class InstallDryRunTests(unittest.TestCase):
    def test_install_dry_run_does_not_call_write_functions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_home = Path(temp_dir)
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(temp_home)
            try:
                with (
                    mock.patch.object(install_codex_memory, "ensure_codex_config") as ensure_config,
                    mock.patch.object(install_codex_memory, "_ensure_hooks_config") as ensure_hooks,
                    mock.patch.object(install_codex_memory, "_ensure_mcp_config") as ensure_mcp,
                    mock.patch.object(install_codex_memory, "_ensure_home_plugin_install") as ensure_plugin,
                    mock.patch.object(install_codex_memory, "_upsert_marketplace_entry") as upsert_marketplace,
                    mock.patch.object(install_codex_memory, "ensure_agents") as ensure_agents,
                    mock.patch.object(install_codex_memory, "ensure_bundled_skills") as ensure_skills,
                    mock.patch.object(install_codex_memory, "ensure_launcher_profiles") as ensure_profiles,
                ):
                    result = install_codex_memory.build_install_dry_run_plan(
                        "auto",
                        "all",
                        "none",
                        install_agents=True,
                        update_existing=False,
                        install_skills=True,
                        mcp_python_command="python",
                        mcp_python_prefix_args=[],
                    )
            finally:
                _restore_env("CODEX_MEMORY_HOME", old_home)

        for writer in (
            ensure_config,
            ensure_hooks,
            ensure_mcp,
            ensure_plugin,
            upsert_marketplace,
            ensure_agents,
            ensure_skills,
            ensure_profiles,
        ):
            writer.assert_not_called()
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["operation"], "install")
        self.assertIn("repo_marketplace", result["targets"])
        self.assertIn("home_plugin", result["targets"])
        self.assertIn("codex_config", result["targets"])
        self.assertIn("home_agents", result["targets"])
        self.assertIn("bundled_skills", result["targets"])
        self.assertIn("planned_writes", result)

    def test_install_dry_run_still_plans_codex_config_when_home_plugin_installed_elsewhere(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            codex_home = home_root / ".codex"
            codex_home.mkdir(parents=True)
            (codex_home / "config.toml").write_text(
                "[features]\ncodex_hooks = true\n",
                encoding="utf-8",
            )
            installed_elsewhere = home_root / "plugins" / "codex-memory"
            installed_elsewhere.parent.mkdir(parents=True)
            installed_elsewhere.mkdir()
            (installed_elsewhere / ".codex-plugin").mkdir()
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(home_root)
            try:
                result = install_codex_memory.build_install_dry_run_plan(
                    "auto",
                    "home",
                    "none",
                    install_agents=True,
                    update_existing=False,
                    install_skills=True,
                    mcp_python_command="python",
                    mcp_python_prefix_args=[],
                )
            finally:
                _restore_env("CODEX_MEMORY_HOME", old_home)

        self.assertEqual(result["targets"]["home_plugin"]["status"], "installed_elsewhere")
        self.assertEqual(result["targets"]["codex_config"]["action"], "set_features.hooks")
        self.assertTrue(result["targets"]["codex_config"]["would_write"])
        self.assertEqual(result["targets"]["home_agents"]["reason"], "installed_elsewhere")

    def test_install_dry_run_cli_does_not_write_to_isolated_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["CODEX_MEMORY_HOME"] = temp_dir
            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(PLUGIN_SCRIPTS_DIR / "install_codex_memory.py"),
                    "--dry-run",
                    "--scope",
                    "home",
                    "--profile-shells",
                    "none",
                    "--skip-skills",
                    "--mcp-python-command",
                    "python",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            payload = json.loads(completed.stdout)
            home_root = Path(temp_dir)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["targets"]["home_plugin"]["status"], "would_install")
        self.assertFalse((home_root / "plugins" / "codex-memory").exists())
        self.assertFalse((home_root / ".agents" / "plugins" / "marketplace.json").exists())
        self.assertFalse((home_root / ".codex" / "AGENTS.md").exists())

    def test_install_dry_run_uses_future_linked_plugin_files_for_first_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(home_root)
            try:
                result = install_codex_memory.build_install_dry_run_plan(
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
                _restore_env("CODEX_MEMORY_HOME", old_home)

        self.assertEqual(result["targets"]["home_plugin"]["status"], "would_install")
        self.assertEqual(result["targets"]["home_hooks_config"]["action"], "no_change")
        self.assertEqual(result["targets"]["home_mcp_config"]["action"], "no_change")
        self.assertNotIn(
            {
                "target": "home_hooks_config",
                "path": str(home_root / "plugins" / "codex-memory" / "hooks.json"),
                "action": "create_file",
            },
            result["planned_writes"],
        )

    def test_install_dry_run_models_copy_mode_plugin_files_after_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(home_root)
            os.environ["CODEX_HOME"] = str(home_root / ".codex")
            try:
                result = install_codex_memory.build_install_dry_run_plan(
                    "copy",
                    "home",
                    "none",
                    install_agents=False,
                    update_existing=False,
                    install_skills=False,
                    mcp_python_command="python",
                    mcp_python_prefix_args=[],
                )
            finally:
                _restore_env("CODEX_MEMORY_HOME", old_home)
                _restore_env("CODEX_HOME", old_codex_home)

        hooks_path = home_root / "plugins" / "codex-memory" / "hooks.json"
        mcp_path = home_root / "plugins" / "codex-memory" / ".mcp.json"
        self.assertEqual(result["targets"]["home_plugin"]["status"], "would_install")
        self.assertEqual(result["targets"]["home_plugin"]["mode"], "copy")
        self.assertEqual(result["targets"]["home_hooks_config"]["path"], str(hooks_path))
        self.assertEqual(result["targets"]["home_hooks_config"]["action"], "no_change")
        self.assertEqual(result["targets"]["home_mcp_config"]["path"], str(mcp_path))
        self.assertEqual(result["targets"]["home_mcp_config"]["action"], "no_change")
        self.assertNotIn(
            {"target": "home_hooks_config", "path": str(hooks_path), "action": "create_file"},
            result["planned_writes"],
        )
        self.assertNotIn(
            {"target": "home_mcp_config", "path": str(mcp_path), "action": "create_file"},
            result["planned_writes"],
        )

    def test_install_dry_run_scope_all_models_repo_config_updates_before_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(home_root)
            os.environ["CODEX_HOME"] = str(home_root / ".codex")
            try:
                result = install_codex_memory.build_install_dry_run_plan(
                    "copy",
                    "all",
                    "none",
                    install_agents=False,
                    update_existing=False,
                    install_skills=False,
                    mcp_python_command="python",
                    mcp_python_prefix_args=[],
                    launcher_family="posix",
                )
            finally:
                _restore_env("CODEX_MEMORY_HOME", old_home)
                _restore_env("CODEX_HOME", old_codex_home)

        home_hooks_path = home_root / "plugins" / "codex-memory" / "hooks.json"
        home_mcp_path = home_root / "plugins" / "codex-memory" / ".mcp.json"
        self.assertEqual(result["targets"]["repo_hooks_config"]["action"], "update_file")
        self.assertEqual(result["targets"]["repo_mcp_config"]["action"], "update_file")
        self.assertEqual(result["targets"]["home_hooks_config"]["path"], str(home_hooks_path))
        self.assertEqual(result["targets"]["home_hooks_config"]["action"], "no_change")
        self.assertEqual(result["targets"]["home_mcp_config"]["path"], str(home_mcp_path))
        self.assertEqual(result["targets"]["home_mcp_config"]["action"], "no_change")
        self.assertNotIn(
            {"target": "home_hooks_config", "path": str(home_hooks_path), "action": "update_file"},
            result["planned_writes"],
        )
        self.assertNotIn(
            {"target": "home_mcp_config", "path": str(home_mcp_path), "action": "update_file"},
            result["planned_writes"],
        )

    def test_install_dry_run_uses_home_plugin_path_for_user_entry_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(home_root)
            os.environ["CODEX_HOME"] = str(home_root / ".codex")
            home_plugin = home_root / "plugins" / "codex-memory"
            agents_path = home_root / ".codex" / "AGENTS.md"
            agents_path.parent.mkdir(parents=True)
            agents_text, _status = replace_marked_block(
                "",
                AGENTS_START,
                AGENTS_END,
                agents_block(home_plugin),
            )
            agents_path.write_text(agents_text, encoding="utf-8")
            profile = profile_paths("pwsh")[0]
            profile.parent.mkdir(parents=True, exist_ok=True)
            profile_text, _status = replace_marked_block(
                "",
                PROFILE_START,
                PROFILE_END,
                profile_block(home_plugin),
            )
            profile.write_text(profile_text, encoding="utf-8")
            try:
                result = install_codex_memory.build_install_dry_run_plan(
                    "auto",
                    "home",
                    "pwsh",
                    install_agents=True,
                    update_existing=False,
                    install_skills=False,
                    mcp_python_command="python",
                    mcp_python_prefix_args=[],
                )
            finally:
                _restore_env("CODEX_MEMORY_HOME", old_home)
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertEqual(result["targets"]["home_plugin"]["status"], "would_install")
        self.assertEqual(result["targets"]["home_agents"]["action"], "no_change")
        self.assertEqual(result["targets"]["powershell_profiles"][0]["action"], "no_change")
        self.assertNotIn(
            {"target": "home_agents", "path": str(agents_path), "action": "updated"},
            result["planned_writes"],
        )
        self.assertNotIn(
            {"target": "powershell_profiles", "path": str(profile), "action": "updated"},
            result["planned_writes"],
        )

    def test_install_dry_run_returns_blocked_plan_for_invalid_marketplace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            marketplace = home_root / ".agents" / "plugins" / "marketplace.json"
            marketplace.parent.mkdir(parents=True)
            marketplace.write_text("{ broken", encoding="utf-8")
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(home_root)
            try:
                result = install_codex_memory.build_install_dry_run_plan(
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
                _restore_env("CODEX_MEMORY_HOME", old_home)

        self.assertEqual(result["targets"]["home_marketplace"]["status"], "parse_error")
        self.assertTrue(result["blocked"])
        self.assertFalse(result["check"]["home_marketplace"]["parse_ok"])

    def test_install_dry_run_lists_only_concrete_skill_write_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home_root = Path(temp_dir)
            old_home = os.environ.get("CODEX_MEMORY_HOME")
            os.environ["CODEX_MEMORY_HOME"] = str(home_root)
            try:
                result = install_codex_memory.build_install_dry_run_plan(
                    "auto",
                    "home",
                    "none",
                    install_agents=False,
                    update_existing=False,
                    install_skills=True,
                    mcp_python_command="python",
                    mcp_python_prefix_args=[],
                )
            finally:
                _restore_env("CODEX_MEMORY_HOME", old_home)

        skill_writes = [
            item for item in result["planned_writes"]
            if item["target"] == "bundled_skills"
        ]
        self.assertGreater(len(skill_writes), 0)
        self.assertTrue(all(item["path"] for item in skill_writes))
        self.assertNotIn(
            {"target": "bundled_skills", "path": "", "action": "install_missing_skills"},
            result["planned_writes"],
        )

    def test_install_dry_run_skips_existing_incomplete_skill_directory(self) -> None:
        status = {
            "skills": [
                {
                    "name": "partial-skill",
                    "source_exists": True,
                    "target_exists": True,
                    "target_has_skill_md": False,
                    "path": "C:/Users/test/.agents/skills/partial-skill",
                }
            ],
            "source_ref": "test",
        }

        with mock.patch.object(install_dry_run_targets, "bundled_skills_status", return_value=status):
            result = install_dry_run_targets.bundled_skills_plan(Path("plugin"))

        self.assertEqual(result["skills"][0]["action"], "skip_existing_incomplete")
        self.assertFalse(result["skills"][0]["would_write"])
        self.assertEqual(
            install_dry_run_targets.planned_writes({"bundled_skills": result}),
            [],
        )

    def test_install_dry_run_reports_missing_skill_sources_as_blocked(self) -> None:
        status = {
            "skills": [
                {
                    "name": "missing-source",
                    "source_exists": False,
                    "target_exists": False,
                    "target_has_skill_md": False,
                    "path": "C:/Users/test/.agents/skills/missing-source",
                },
                {
                    "name": "fresh-skill",
                    "source_exists": True,
                    "target_exists": False,
                    "target_has_skill_md": False,
                    "path": "C:/Users/test/.agents/skills/fresh-skill",
                }
            ],
            "source_ref": "test",
        }

        with mock.patch.object(install_dry_run_targets, "bundled_skills_status", return_value=status):
            result = install_dry_run_targets.bundled_skills_plan(Path("plugin"))

        blocked = install_dry_run_targets.target_blocks({"bundled_skills": result})
        self.assertTrue(result["blocked"])
        self.assertTrue(blocked)
        self.assertEqual(result["skills"][0]["action"], "blocked_missing_source")
        self.assertNotIn(
            {"target": "bundled_skills", "path": "", "action": "install_missing_skills"},
            install_dry_run_targets.planned_writes({"bundled_skills": result}),
        )


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
