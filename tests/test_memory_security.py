from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import init_storage
import memory_store
import sensitive_scan


class SensitiveScanTests(unittest.TestCase):
    def test_sanitizer_redacts_sensitive_keys_and_tokens(self) -> None:
        result = sensitive_scan.sanitize_for_persistence(
            {
                "summary": "Authorization: Bearer sampletokenvalue12345",
                "metadata": {"api_key": "sampletokenvalue12345"},
            }
        )

        self.assertFalse(result.blocked)
        self.assertIn("[REDACTED]", str(result.value))
        self.assertGreater(result.report()["finding_count"], 0)

    def test_sanitizer_redacts_credential_fields_and_assignments(self) -> None:
        result = sensitive_scan.sanitize_for_persistence(
            {
                "credentials": "plain login material",
                "nested": {"credential": "plain credential material"},
                "summary": "credentials=plain assignment material",
            }
        )

        payload = str(result.value)
        self.assertFalse(result.blocked)
        self.assertNotIn("plain login material", payload)
        self.assertNotIn("plain credential material", payload)
        self.assertNotIn("plain assignment material", payload)
        self.assertGreaterEqual(result.report()["finding_count"], 3)

    def test_memory_store_redacts_summary_before_persisting(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".codex").mkdir()
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = temp_dir
                store = memory_store.MemoryStore()
                summary = store.write_task_summary(
                    "secret-summary",
                    "token=sampletokenvalue12345",
                )
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

        self.assertNotIn("sampletokenvalue12345", summary["summary_markdown"])
        self.assertIn("[REDACTED]", summary["summary_markdown"])

    def test_memory_store_redacts_task_id_before_persisting_keys(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        secret = "sampletokenvalue12345"
        raw_task_id = f"token={secret}"
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".codex").mkdir()
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = temp_dir
                store = memory_store.MemoryStore()
                store.upsert_task_state(raw_task_id, {"objective": "x"})
                summary = store.write_task_summary(raw_task_id, "safe summary")
                decision = store.write_repo_decision("safe title", "safe details", task_id=raw_task_id)
                paths = init_storage.resolve_storage_paths(scope="project", cwd=temp_dir)
                conn = sqlite3.connect(paths.db_path)
                try:
                    task_ids = [row[0] for row in conn.execute("SELECT task_id FROM task_state").fetchall()]
                    summary_ids = [
                        row[0] for row in conn.execute("SELECT task_id FROM task_summary").fetchall()
                    ]
                    decision_ids = [
                        row[0] for row in conn.execute("SELECT task_id FROM repo_decision").fetchall()
                    ]
                    current = conn.execute(
                        "SELECT value_json FROM plugin_meta WHERE key = 'current_task_id'"
                    ).fetchone()[0]
                finally:
                    conn.close()
                event_log = paths.event_log_path.read_text(encoding="utf-8")
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

        self.assertEqual(task_ids, ["token=[REDACTED]"])
        self.assertEqual(summary_ids, ["token=[REDACTED]"])
        self.assertEqual(decision_ids, ["token=[REDACTED]"])
        self.assertEqual(summary["task_id"], "token=[REDACTED]")
        self.assertEqual(decision["task_id"], "token=[REDACTED]")
        self.assertNotIn(secret, current)
        self.assertNotIn(secret, summary["file_path"])
        self.assertNotIn(secret, event_log)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
