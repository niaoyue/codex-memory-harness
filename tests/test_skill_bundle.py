from __future__ import annotations

import json
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

import skill_bundle


class SkillBundleTests(unittest.TestCase):
    def test_bundled_skills_status_uses_vendored_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_home = Path(temp_dir)
            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_home / ".codex")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=temp_home):
                    status = skill_bundle.bundled_skills_status(PROJECT_ROOT / "plugins" / "codex-memory")
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        names = {item["name"] for item in status["skills"]}
        manifest = skill_bundle.load_manifest(PROJECT_ROOT / "plugins" / "codex-memory")
        expected_count = len(manifest["skills"])
        self.assertEqual(status["source_ref"], "af9b54f235d0d56c6b4410be54d578b0fda4ddfc")
        self.assertTrue(status["overwrite_existing"])
        self.assertIn("security-threat-model", names)
        self.assertIn("gh-fix-ci", names)
        self.assertIn("grill-me", names)
        self.assertIn("design-an-interface", names)
        self.assertIn("tdd", names)
        self.assertIn("harness-release-gate", names)
        self.assertIn(".agents", status["target_root"])
        self.assertIn(".codex", status["legacy_target_root"])
        self.assertEqual(status["source_missing_count"], 0)
        self.assertEqual(status["missing_count"], expected_count)
        self.assertEqual(status["manifest_unique_skill_count"], expected_count)
        self.assertEqual(status["manifest_duplicate_count"], 0)

    def test_ensure_bundled_skills_copies_missing_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "plugin"
            source_root = plugin_root / "skills" / "openai-curated"
            for name in ("fresh-skill", "existing-skill"):
                skill_dir = source_root / name
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
            (plugin_root / "skills" / "bundled-skills.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source_ref": "test-ref",
                        "installed_by_default": True,
                        "skills": [
                            {"name": "fresh-skill"},
                            {"name": "existing-skill"},
                            {"name": "fresh-skill"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = temp_root / "home"
            existing = home / ".agents" / "skills" / "existing-skill"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("# user copy\n", encoding="utf-8")

            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_root / "codex-home")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=home):
                    result = skill_bundle.ensure_bundled_skills(plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

            self.assertEqual(result["installed"], 1)
            self.assertEqual(result["skipped_existing"], 1)
            self.assertEqual(result["deduped_existing"], 1)
            self.assertEqual(result["manifest_duplicate_count"], 1)
            self.assertEqual(len(result["skills"]), 2)
            self.assertTrue((home / ".agents" / "skills" / "fresh-skill" / "SKILL.md").exists())
            self.assertEqual((existing / "SKILL.md").read_text(encoding="utf-8"), "# user copy\n")

    def test_ensure_bundled_skills_updates_existing_when_manifest_allows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "plugin"
            source = plugin_root / "skills" / "local" / "harness-release-gate"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("# packaged gate\n", encoding="utf-8")
            (plugin_root / "skills" / "bundled-skills.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "overwrite_existing": True,
                        "skills": [
                            {
                                "name": "harness-release-gate",
                                "source_group": "local",
                                "path": "local/harness-release-gate",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = temp_root / "home"
            existing = home / ".agents" / "skills" / "harness-release-gate"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("# old gate\n", encoding="utf-8")

            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_root / "codex-home")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=home):
                    result = skill_bundle.ensure_bundled_skills(plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

            backup_root = home / ".agents" / "skills" / ".codex-memory-backups"
            backups = list(backup_root.glob("harness-release-gate.backup-*"))

            self.assertEqual(result["installed"], 0)
            self.assertEqual(result["updated"], 1)
            self.assertEqual(result["skills"][0]["status"], "updated")
            self.assertEqual((existing / "SKILL.md").read_text(encoding="utf-8"), "# packaged gate\n")
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "SKILL.md").read_text(encoding="utf-8"), "# old gate\n")

    def test_ensure_bundled_skills_retires_legacy_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "plugin"
            source = plugin_root / "skills" / "local" / "git-safe-commit"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("# packaged commit skill\n", encoding="utf-8")
            (plugin_root / "skills" / "bundled-skills.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "overwrite_existing": True,
                        "skills": [
                            {
                                "name": "git-safe-commit",
                                "source_group": "local",
                                "path": "local/git-safe-commit",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = temp_root / "home"
            existing = home / ".agents" / "skills" / "git-safe-commit"
            legacy = temp_root / "codex-home" / "skills" / "git-safe-commit"
            existing.mkdir(parents=True)
            legacy.mkdir(parents=True)
            (existing / "SKILL.md").write_text("# packaged commit skill\n", encoding="utf-8")
            (legacy / "SKILL.md").write_text("# legacy duplicate\n", encoding="utf-8")

            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_root / "codex-home")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=home):
                    result = skill_bundle.ensure_bundled_skills(plugin_root)
                    status = skill_bundle.bundled_skills_status(plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

            backups = list((temp_root / "codex-home" / "skills" / ".codex-memory-backups").glob("git-safe-commit.backup-*"))

            self.assertEqual(result["retired_legacy_duplicates"], 1)
            self.assertEqual(result["retired_system_duplicates"], 0)
            self.assertFalse(legacy.exists())
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "SKILL.md").read_text(encoding="utf-8"), "# legacy duplicate\n")
            self.assertEqual(status["legacy_duplicate_count"], 0)
            self.assertEqual(status["duplicate_count"], 0)

    def test_ensure_bundled_skills_prefers_system_builtin_and_retires_user_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "plugin"
            source = plugin_root / "skills" / "local" / "imagegen"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("# packaged image skill\n", encoding="utf-8")
            (plugin_root / "skills" / "bundled-skills.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "overwrite_existing": True,
                        "skills": [
                            {
                                "name": "imagegen",
                                "source_group": "local",
                                "path": "local/imagegen",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = temp_root / "home"
            user_copy = home / ".agents" / "skills" / "imagegen"
            system_copy = temp_root / "codex-home" / "skills" / ".system" / "imagegen"
            user_copy.mkdir(parents=True)
            system_copy.mkdir(parents=True)
            (user_copy / "SKILL.md").write_text("# user duplicate\n", encoding="utf-8")
            (system_copy / "SKILL.md").write_text("# built-in image skill\n", encoding="utf-8")

            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_root / "codex-home")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=home):
                    before = skill_bundle.bundled_skills_status(plugin_root)
                    result = skill_bundle.ensure_bundled_skills(plugin_root)
                    after = skill_bundle.bundled_skills_status(plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

            backups = list((home / ".agents" / "skills" / ".codex-memory-backups").glob("imagegen.backup-*"))

            self.assertEqual(before["system_duplicate_count"], 1)
            self.assertEqual(result["installed"], 0)
            self.assertEqual(result["retired_system_duplicates"], 1)
            self.assertEqual(result["skills"][0]["status"], "system_builtin")
            self.assertFalse(user_copy.exists())
            self.assertTrue((system_copy / "SKILL.md").exists())
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "SKILL.md").read_text(encoding="utf-8"), "# user duplicate\n")
            self.assertEqual(after["available_count"], 1)
            self.assertEqual(after["missing_count"], 0)
            self.assertEqual(after["system_duplicate_count"], 0)
            self.assertEqual(after["duplicate_count"], 0)

    def test_bundled_skills_status_marks_legacy_only_for_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            plugin_root = temp_root / "plugin"
            source = plugin_root / "skills" / "local" / "git-safe-commit"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("# packaged commit skill\n", encoding="utf-8")
            (plugin_root / "skills" / "bundled-skills.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "overwrite_existing": True,
                        "skills": [
                            {
                                "name": "git-safe-commit",
                                "source_group": "local",
                                "path": "local/git-safe-commit",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = temp_root / "home"
            legacy = temp_root / "codex-home" / "skills" / "git-safe-commit"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").write_text("# legacy only\n", encoding="utf-8")

            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(temp_root / "codex-home")
            try:
                with mock.patch.object(skill_bundle, "home_root", return_value=home):
                    status = skill_bundle.bundled_skills_status(plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

            skill = status["skills"][0]
            self.assertFalse(skill["available"])
            self.assertFalse(skill["legacy_duplicate"])
            self.assertTrue(skill["legacy_retirement_required"])
            self.assertEqual(status["missing_count"], 1)
            self.assertEqual(status["legacy_duplicate_count"], 0)

    def test_bundled_skills_status_dedupes_existing_skill_drift(self) -> None:
        status = _status_for_existing_skill(
            source_skill="# packaged candidate commit flow\n",
            target_skill="# stale uncommitted review flow\n",
            source_script="print('packaged')\n",
        )

        skill = status["skills"][0]
        self.assertEqual(status["stale_count"], 1)
        self.assertEqual(status["deduped_existing_count"], 1)
        self.assertEqual(status["content_differs_count"], 1)
        self.assertTrue(skill["stale_existing"])
        self.assertTrue(skill["deduped_existing"])
        self.assertTrue(skill["content_differs_from_source"])
        self.assertFalse(skill["target_matches_source"])
        self.assertNotEqual(skill["source_digest"], skill["target_digest"])

    def test_bundled_skills_status_dedupes_script_drift_when_skill_md_matches(self) -> None:
        status = _status_for_existing_skill(
            source_skill="# same skill text\n",
            target_skill="# same skill text\n",
            source_script="print('packaged')\n",
            target_script="print('old')\n",
        )

        skill = status["skills"][0]
        self.assertEqual(status["stale_count"], 1)
        self.assertEqual(status["deduped_existing_count"], 1)
        self.assertEqual(status["content_differs_count"], 1)
        self.assertTrue(skill["stale_existing"])
        self.assertTrue(skill["deduped_existing"])
        self.assertTrue(skill["content_differs_from_source"])
        self.assertFalse(skill["target_matches_source"])


def _status_for_existing_skill(
    *,
    source_skill: str,
    target_skill: str,
    source_script: str,
    target_script: str | None = None,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        plugin_root = temp_root / "plugin"
        source = plugin_root / "skills" / "local" / "scripted-skill"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(source_skill, encoding="utf-8")
        (source / "scripts").mkdir()
        (source / "scripts" / "tool.py").write_text(source_script, encoding="utf-8")
        (plugin_root / "skills" / "bundled-skills.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "skills": [
                        {
                            "name": "scripted-skill",
                            "source_group": "local",
                            "path": "local/scripted-skill",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        home = temp_root / "home"
        target = home / ".agents" / "skills" / "scripted-skill"
        (target / "scripts").mkdir(parents=True)
        (target / "SKILL.md").write_text(target_skill, encoding="utf-8")
        if target_script is not None:
            (target / "scripts" / "tool.py").write_text(target_script, encoding="utf-8")

        old_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(temp_root / "codex-home")
        try:
            with mock.patch.object(skill_bundle, "home_root", return_value=home):
                return skill_bundle.bundled_skills_status(plugin_root)
        finally:
            _restore_env("CODEX_HOME", old_codex_home)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
