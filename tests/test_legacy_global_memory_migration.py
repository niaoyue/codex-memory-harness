from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import legacy_global_memory_migration


class LegacyGlobalMemoryMigrationTests(unittest.TestCase):
    def test_dry_run_reports_manifest_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir) / "codex-home"
            official = codex_home / "memories"
            official.mkdir(parents=True)
            (official / "memory.db").write_bytes(b"legacy-db")
            summaries = official / "summaries"
            summaries.mkdir()
            (summaries / "task.md").write_text("# Summary\n", encoding="utf-8")

            plan = legacy_global_memory_migration.migrate(codex_home, confirm=False)

        self.assertTrue(plan["ok"])
        self.assertTrue(plan["dry_run"])
        self.assertIn("migration-manifests", plan["manifest_path"])
        entries = {item["marker"]: item for item in plan["entries"]}
        self.assertEqual(entries["memory.db"]["action"], "copy_then_archive_source")
        self.assertTrue(entries["memory.db"]["source_checksum"].startswith("sha256:"))
        self.assertEqual(entries["summaries"]["action"], "copy_then_archive_source")
        self.assertTrue(entries["summaries"]["source_checksum"].startswith("sha256-dir:"))
        self.assertIn("Rollback is manual", plan["rollback"])
        self.assertFalse((codex_home / "codex-memory-harness" / "memories").exists())

    def test_confirm_copies_and_archives_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir) / "codex-home"
            official = codex_home / "memories"
            official.mkdir(parents=True)
            (official / "memory.db").write_bytes(b"legacy-db")
            (official / "events.jsonl").write_text("{}\n", encoding="utf-8")

            result = legacy_global_memory_migration.migrate(codex_home, confirm=True)
            target = codex_home / "codex-memory-harness" / "memories"

            self.assertTrue(result["ok"], result)
            self.assertFalse((official / "memory.db").exists())
            self.assertEqual((target / "memory.db").read_bytes(), b"legacy-db")
            self.assertTrue(Path(result["manifest_path"]).exists())
            archived = [item.get("source_archived_to", "") for item in result["entries"]]
            self.assertTrue(any(item.endswith("memory.db") for item in archived))
            self.assertTrue(any((target / "legacy-official-backups").rglob("events.jsonl")))

    def test_archives_source_when_target_checksum_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir) / "codex-home"
            official = codex_home / "memories"
            target = codex_home / "codex-memory-harness" / "memories"
            official.mkdir(parents=True)
            target.mkdir(parents=True)
            (official / "memory.db").write_bytes(b"legacy-db")
            (target / "memory.db").write_bytes(b"new-db")

            result = legacy_global_memory_migration.migrate(codex_home, confirm=True)
            backup_root = target / "legacy-official-backups"
            source_exists = (official / "memory.db").exists()
            target_bytes = (target / "memory.db").read_bytes()
            backup_has_memory = any(path.name == "memory.db" for path in backup_root.rglob("memory.db"))

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(source_exists)
        self.assertEqual(target_bytes, b"new-db")
        self.assertTrue(backup_has_memory)
        entries = {item["marker"]: item for item in result["entries"]}
        self.assertEqual(entries["memory.db"]["action"], "archive_conflicting_source")
        self.assertIn("different checksum", entries["memory.db"]["conflict_reason"])

    def test_blocks_directory_markers_that_contain_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir) / "codex-home"
            summaries = codex_home / "memories" / "summaries"
            summaries.mkdir(parents=True)
            (summaries / "task.md").write_text("# Summary\n", encoding="utf-8")
            try:
                (summaries / "linked.md").symlink_to(summaries / "task.md")
            except OSError as exc:  # pragma: no cover - symlink privileges vary on Windows
                self.skipTest(f"symlink creation unavailable: {exc}")

            plan = legacy_global_memory_migration.migrate(codex_home, confirm=False)

        self.assertFalse(plan["ok"])
        entries = {item["marker"]: item for item in plan["entries"]}
        self.assertTrue(entries["summaries"]["blocked"])
        self.assertIn("contains symlink", entries["summaries"]["blocked_reason"])


if __name__ == "__main__":
    unittest.main()
