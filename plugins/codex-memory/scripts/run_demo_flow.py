from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from hook_runner import HookRunner
import init_storage


def _line_mentions_task(line: str, task_id: str) -> bool:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return task_id in line
    return _payload_mentions_task(payload, task_id)


def _payload_mentions_task(payload: object, task_id: str) -> bool:
    if isinstance(payload, dict):
        return any(_payload_mentions_task(value, task_id) for value in payload.values())
    if isinstance(payload, list):
        return any(_payload_mentions_task(value, task_id) for value in payload)
    return payload == task_id


def _cleanup_task(task_id: str) -> None:
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
        kept = [line for line in lines if not _line_mentions_task(line, task_id)]
        paths.event_log_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def main() -> int:
    init_storage.ensure_storage_layout()
    task_id = "step-6-demo"
    _cleanup_task(task_id)

    runner = HookRunner()
    events = {
        "before_task": runner.run_event(
            "before_task",
            {
                "task_id": task_id,
                "user_request": "为 Codex Memory 插件打通 hooks 自动触发",
                "constraints": ["只做阶段5", "失败时必须降级"],
                "working_set": [
                    "plugins/codex-memory/scripts/hook_runner.py",
                    "plugins/codex-memory/scripts/run_demo_flow.py",
                ],
                "next_step": "模拟工具执行并更新状态",
                "max_total_chars": 1200,
            },
        ),
        "after_tool": runner.run_event(
            "after_tool",
            {
                "task_id": task_id,
                "tool_name": "shell_command",
                "summary": "验证 scripts 目录下的 hooks 骨架文件存在",
                "touched_paths": [
                    "plugins/codex-memory/scripts/hook_runner.py",
                    "plugins/codex-memory/hooks.json",
                ],
                "next_step": "构建响应前上下文",
            },
        ),
        "before_response": runner.run_event(
            "before_response",
            {
                "task_id": task_id,
                "max_total_chars": 1000,
            },
        ),
        "on_task_complete": runner.run_event(
            "on_task_complete",
            {
                "task_id": task_id,
                "summary_markdown": "# Step 6 Demo\n\n- 已触发 before_task\n- 已触发 after_tool\n- 已触发 before_response\n- 已触发 on_task_complete\n",
                "max_total_chars": 1200,
            },
        ),
    }

    distilled_files = sorted(str(path) for path in init_storage.resolve_storage_paths().distilled_dir.glob(f"{task_id}*.md"))
    output = {
        "events": events,
        "distilled_files": distilled_files,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    _cleanup_task(task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
