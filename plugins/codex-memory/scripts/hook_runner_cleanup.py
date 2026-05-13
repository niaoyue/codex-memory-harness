from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import init_storage


def cleanup_demo_task(task_id: str) -> None:
    init_storage.ensure_storage_layout()
    paths = init_storage.resolve_storage_paths()
    with closing(sqlite3.connect(paths.db_path)) as conn:
        conn.execute("DELETE FROM task_state WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM repo_decision WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task_summary WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM distilled_asset WHERE task_id = ?", (task_id,))
        conn.execute(
            "DELETE FROM plugin_meta WHERE key = ? AND value_json = ?",
            ("current_task_id", json.dumps(task_id, ensure_ascii=False)),
        )
        conn.commit()
    summary_file = paths.summary_dir / f"{task_id}.md"
    if summary_file.exists():
        summary_file.unlink()
    for file_path in paths.distilled_dir.glob(f"{task_id}*.md"):
        file_path.unlink()
    if paths.event_log_path.exists():
        lines = paths.event_log_path.read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if task_id not in line]
        paths.event_log_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
