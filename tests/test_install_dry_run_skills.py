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
import install_dry_run_targets


class InstallDryRunSkillPlanTests(unittest.TestCase):
    def test_lists_only_concrete_skill_write_paths(self) -> None:
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

    def test_skips_existing_incomplete_skill_directory(self) -> None:
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

    def test_reports_missing_skill_sources_as_blocked(self) -> None:
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
                },
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

    def test_dedupes_existing_skill_without_blocking(self) -> None:
        status = {
            "skills": [
                {
                    "name": "harness-release-gate",
                    "source_exists": True,
                    "target_exists": True,
                    "target_has_skill_md": True,
                    "stale_existing": True,
                    "deduped_existing": True,
                    "content_differs_from_source": True,
                    "path": "C:/Users/test/.agents/skills/harness-release-gate",
                }
            ],
            "source_ref": "test",
            "overwrite_existing": False,
        }

        with mock.patch.object(install_dry_run_targets, "bundled_skills_status", return_value=status):
            result = install_dry_run_targets.bundled_skills_plan(Path("plugin"))

        self.assertFalse(result["blocked"])
        self.assertEqual(result["stale_existing_count"], 1)
        self.assertEqual(result["deduped_existing_count"], 1)
        self.assertEqual(result["skills"][0]["action"], "already_exists_deduped")
        self.assertFalse(result["skills"][0]["would_write"])
        self.assertIn("keep the existing user skill", result["skills"][0]["reason"])

    def test_updates_existing_bundled_skill_when_enabled(self) -> None:
        status = {
            "skills": [
                {
                    "name": "harness-release-gate",
                    "source_exists": True,
                    "target_exists": True,
                    "target_has_skill_md": True,
                    "target_matches_source": False,
                    "stale_existing": True,
                    "path": "C:/Users/test/.agents/skills/harness-release-gate",
                }
            ],
            "source_ref": "test",
            "overwrite_existing": True,
        }

        with mock.patch.object(install_dry_run_targets, "bundled_skills_status", return_value=status):
            result = install_dry_run_targets.bundled_skills_plan(Path("plugin"))

        self.assertEqual(result["skills"][0]["action"], "update_existing")
        self.assertTrue(result["skills"][0]["would_write"])
        self.assertEqual(result["planned_update_count"], 1)
        self.assertEqual(
            install_dry_run_targets.planned_writes({"bundled_skills": result}),
            [
                {
                    "target": "bundled_skills",
                    "path": "C:/Users/test/.agents/skills/harness-release-gate",
                    "action": "update_existing",
                }
            ],
        )

    def test_plans_system_duplicate_retirement(self) -> None:
        status = {
            "skills": [
                {
                    "name": "imagegen",
                    "source_exists": True,
                    "target_exists": True,
                    "target_has_skill_md": True,
                    "system_target_has_skill_md": True,
                    "system_duplicate": True,
                    "path": "C:/Users/test/.agents/skills/imagegen",
                }
            ],
            "source_ref": "test",
            "overwrite_existing": True,
        }

        with mock.patch.object(install_dry_run_targets, "bundled_skills_status", return_value=status):
            result = install_dry_run_targets.bundled_skills_plan(Path("plugin"))

        self.assertEqual(result["skills"][0]["action"], "retire_system_duplicate")
        self.assertTrue(result["skills"][0]["would_write"])
        self.assertEqual(result["planned_duplicate_retire_count"], 1)
        self.assertIn("built-in system skill", result["skills"][0]["reason"])

    def test_plans_legacy_duplicate_retirement(self) -> None:
        status = {
            "skills": [
                {
                    "name": "git-safe-commit",
                    "source_exists": True,
                    "target_exists": True,
                    "target_has_skill_md": True,
                    "legacy_duplicate": True,
                    "path": "C:/Users/test/.agents/skills/git-safe-commit",
                    "legacy_path": "C:/Users/test/.codex/skills/git-safe-commit",
                }
            ],
            "source_ref": "test",
            "overwrite_existing": True,
        }

        with mock.patch.object(install_dry_run_targets, "bundled_skills_status", return_value=status):
            result = install_dry_run_targets.bundled_skills_plan(Path("plugin"))

        self.assertEqual(result["skills"][0]["action"], "retire_legacy_duplicate")
        self.assertTrue(result["skills"][0]["would_write"])
        self.assertEqual(result["planned_duplicate_retire_count"], 1)
        self.assertIn("legacy CODEX_HOME/skills", result["skills"][0]["reason"])


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
