from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import init_storage
import memory_retention


class MemoryRetentionTests(unittest.TestCase):
    def test_dry_run_reports_target_without_changing_data(self) -> None:
        with isolated_memory() as paths:
            seed_task(paths, "target-task")
            seed_task(paths, "other-task")

            result = memory_retention.dry_run_task("target-task", cwd=paths.storage_dir.parent.parent)

            self.assertTrue(result["would_change"])
            self.assertEqual(result["counts"]["db_rows"]["task_state"], 1)
            self.assertEqual(result["counts"]["db_rows"]["task_summary"], 1)
            self.assertEqual(result["counts"]["db_rows"]["repo_decision"], 1)
            self.assertEqual(result["counts"]["db_rows"]["distilled_asset"], 1)
            self.assertEqual(result["counts"]["history_records"]["events.jsonl"], 1)
            self.assertEqual(count_task_rows(paths.db_path, "target-task"), 4)
            self.assertEqual(count_history_records(paths.storage_dir, "target-task"), 1)
            self.assertFalse((paths.storage_dir / "archives").exists())

    def test_confirm_archives_and_removes_only_target_task(self) -> None:
        with isolated_memory() as paths:
            seed_task(paths, "target-task")
            seed_task(paths, "other-task")

            result = memory_retention.confirm_task("target-task", cwd=paths.storage_dir.parent.parent)

            self.assertTrue(result["changed"])
            archive_path = Path(result["archive_path"])
            self.assertTrue(archive_path.exists())
            archive = json.loads(archive_path.read_text(encoding="utf-8"))
            self.assertEqual(archive["task_id"], "target-task")
            self.assertEqual(archive["counts"]["db_rows"]["task_state"], 1)
            self.assertEqual(archive["counts"]["history_records"]["events.jsonl"], 1)
            self.assertEqual(count_task_rows(paths.db_path, "target-task"), 0)
            self.assertEqual(count_history_records(paths.storage_dir, "target-task"), 0)
            self.assertEqual(count_task_rows(paths.db_path, "other-task"), 4)
            self.assertEqual(count_history_records(paths.storage_dir, "other-task"), 1)


def isolated_memory():
    return _IsolatedMemory()


class _IsolatedMemory:
    def __enter__(self):
        self.old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        self.old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / ".codex").mkdir()
        os.environ["CODEX_MEMORY_SCOPE"] = "project"
        os.environ["CODEX_MEMORY_CWD"] = str(self.root)
        init_storage.ensure_storage_layout(scope="project", cwd=self.root)
        return init_storage.resolve_storage_paths(scope="project", cwd=self.root)

    def __exit__(self, exc_type, exc, tb):
        _restore_env("CODEX_MEMORY_SCOPE", self.old_scope)
        _restore_env("CODEX_MEMORY_CWD", self.old_cwd)
        self.temp_dir.cleanup()


def seed_task(paths: init_storage.StoragePaths, task_id: str) -> None:
    with closing(sqlite3.connect(paths.db_path)) as conn:
        conn.execute(
            "INSERT INTO task_state (task_id, payload_json, updated_at) VALUES (?, ?, ?)",
            (task_id, json.dumps({"task_id": task_id}), "now"),
        )
        conn.execute(
            """
            INSERT INTO task_summary (task_id, summary_markdown, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, "# Summary", "now", "now"),
        )
        conn.execute(
            "INSERT INTO repo_decision (task_id, title, details, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "Decision", "Details", "now"),
        )
        conn.execute(
            """
            INSERT INTO distilled_asset (
                task_id, asset_type, title, summary_text, file_path, tags_json, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, "summary", "Asset", "Text", "asset.md", "[]", "{}", "now"),
        )
        conn.commit()

    history_dir = paths.storage_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / "events.jsonl"
    with history_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"event_type": "task_state.upserted", "task_id": task_id},
                ensure_ascii=False,
            )
            + "\n"
        )


def count_task_rows(db_path: Path, task_id: str) -> int:
    with closing(sqlite3.connect(db_path)) as conn:
        return sum(
            conn.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (task_id,)).fetchone()[0]
            for table in memory_retention.DB_TABLES
        )


def count_history_records(storage_dir: Path, task_id: str) -> int:
    history_path = storage_dir / "history" / "events.jsonl"
    records = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return sum(1 for item in records if item.get("task_id") == task_id)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
