from __future__ import annotations

from contextlib import contextmanager
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

import hook_bridge
import memory_store


@contextmanager
def _project_memory_env():
    with tempfile.TemporaryDirectory() as project_dir:
        previous_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        previous_cwd = os.environ.get("CODEX_MEMORY_CWD")
        try:
            os.environ["CODEX_MEMORY_SCOPE"] = "project"
            os.environ["CODEX_MEMORY_CWD"] = project_dir
            yield project_dir
        finally:
            _restore_env("CODEX_MEMORY_SCOPE", previous_scope)
            _restore_env("CODEX_MEMORY_CWD", previous_cwd)


class HookBridgeTaskMappingTests(unittest.TestCase):
    def test_maps_user_prompt_to_before_task(self) -> None:
        event, payload = hook_bridge._normalize_payload(
            "UserPromptSubmit",
            {"prompt": "Fix client login", "cwd": "E:/repo"},
        )

        self.assertEqual(event, "before_task")
        self.assertTrue(payload["task_id"].startswith("prompt-"))
        self.assertEqual(payload["objective"], "Fix client login")
        self.assertEqual(payload["user_request"], "Fix client login")
        self.assertEqual(payload["cwd"], "E:/repo")

    def test_user_prompt_generates_unique_task_ids_for_same_session_without_turn_id(self) -> None:
        first_event, first_payload = hook_bridge._normalize_payload(
            "UserPromptSubmit",
            {"session_id": "session-one", "prompt": "First prompt"},
        )
        second_event, second_payload = hook_bridge._normalize_payload(
            "UserPromptSubmit",
            {"session_id": "session-one", "prompt": "Second prompt"},
        )

        self.assertEqual(first_event, "before_task")
        self.assertEqual(second_event, "before_task")
        self.assertTrue(first_payload["task_id"].startswith("prompt-"))
        self.assertTrue(second_payload["task_id"].startswith("prompt-"))
        self.assertNotEqual(first_payload["task_id"], second_payload["task_id"])

    def test_user_prompt_preserves_explicit_task_id_aliases(self) -> None:
        for key, task_id in (("task_id", "task-explicit"), ("taskId", "task-explicit-alias")):
            with self.subTest(key=key):
                event, payload = hook_bridge._normalize_payload(
                    "UserPromptSubmit",
                    {key: task_id, "prompt": "Fix client login"},
                )
                self.assertEqual(event, "before_task")
                self.assertEqual(payload["task_id"], task_id)

    def test_native_followup_hooks_use_current_session_task_id_without_turn_id(self) -> None:
        with _project_memory_env():
            prompt_event, prompt_payload = hook_bridge._normalize_payload(
                "UserPromptSubmit",
                {"session_id": "session-one", "prompt": "Fix client login"},
                persist_hook_task=True,
            )
            tool_event, tool_payload = hook_bridge._normalize_payload(
                "PostToolUse",
                {"session_id": "session-one", "summary": "ran shell"},
                persist_hook_task=True,
            )
            stop_event, stop_payload = hook_bridge._normalize_payload(
                "Stop",
                {"session_id": "session-one", "summary": "# Done"},
                persist_hook_task=True,
            )

        self.assertEqual(prompt_event, "before_task")
        self.assertEqual(tool_event, "after_tool")
        self.assertEqual(stop_event, "before_response")
        self.assertEqual(prompt_payload["task_id"], tool_payload["task_id"])
        self.assertEqual(prompt_payload["task_id"], stop_payload["task_id"])
        self.assertTrue(prompt_payload["task_id"].startswith("prompt-"))

    def test_turn_scoped_prompt_updates_current_session_mapping(self) -> None:
        with _project_memory_env() as project_dir:
            prompt_event, prompt_payload = hook_bridge._normalize_payload(
                "UserPromptSubmit",
                {"cwd": project_dir, "session_id": "session-one", "turn_id": "turn-one", "prompt": "Fix client login"},
                persist_hook_task=True,
            )
            tool_event, tool_payload = hook_bridge._normalize_payload(
                "PostToolUse",
                {"cwd": project_dir, "session_id": "session-one", "summary": "ran shell"},
                persist_hook_task=True,
            )
            stop_event, stop_payload = hook_bridge._normalize_payload(
                "Stop",
                {"cwd": project_dir, "session_id": "session-one", "summary": "# Done"},
                persist_hook_task=True,
            )

        self.assertEqual(prompt_event, "before_task")
        self.assertEqual(tool_event, "after_tool")
        self.assertEqual(stop_event, "before_response")
        self.assertEqual(prompt_payload["task_id"], tool_payload["task_id"])
        self.assertEqual(prompt_payload["task_id"], stop_payload["task_id"])
        self.assertTrue(prompt_payload["task_id"].startswith("prompt-"))

    def test_native_hook_events_fall_back_to_stable_session_task_id_without_persisted_prompt(self) -> None:
        tool_event, tool_payload = hook_bridge._normalize_payload(
            "PostToolUse",
            {"session_id": "session-one", "summary": "ran shell"},
        )
        stop_event, stop_payload = hook_bridge._normalize_payload(
            "Stop",
            {"session_id": "session-one", "summary": "# Done"},
        )

        self.assertEqual(tool_event, "after_tool")
        self.assertEqual(stop_event, "before_response")
        self.assertEqual(tool_payload["task_id"], stop_payload["task_id"])
        self.assertTrue(tool_payload["task_id"].startswith("hook-"))

    def test_native_hook_event_without_task_or_session_gets_isolated_task_id(self) -> None:
        event, payload = hook_bridge._normalize_payload(
            "Stop",
            {"summary": "# Done"},
        )

        self.assertEqual(event, "before_response")
        self.assertTrue(payload["task_id"].startswith("hook-stop-"))

    def test_persisted_hook_session_mapping_survives_interleaved_current_task_changes(self) -> None:
        with _project_memory_env():
            store = memory_store.MemoryStore()
            runner = hook_bridge.HookRunner(memory_store=store)
            event, payload = hook_bridge._normalize_payload(
                "UserPromptSubmit",
                {"session_id": "session-one", "prompt": "First prompt"},
                persist_hook_task=True,
            )
            runner.run_event(event, payload)
            runner.run_event("before_task", {"task_id": "task-two", "objective": "Second prompt"})
            stop_event, stop_payload = hook_bridge._normalize_payload(
                "Stop",
                {"session_id": "session-one", "summary": "# First response"},
                persist_hook_task=True,
            )
            runner.run_event(stop_event, stop_payload)
            first_summary = store.get_task_summary(payload["task_id"])
            second_summary = store.get_task_summary("task-two")

        self.assertEqual(first_summary["summary_markdown"], "# First response")
        self.assertIsNone(second_summary)

    def test_explicit_task_id_updates_turn_and_current_session_mappings(self) -> None:
        with _project_memory_env() as project_dir:
            prompt_event, prompt_payload = hook_bridge._normalize_payload(
                "UserPromptSubmit",
                {
                    "cwd": project_dir,
                    "task_id": "task-explicit",
                    "session_id": "session-one",
                    "turn_id": "turn-one",
                    "prompt": "First prompt",
                },
                persist_hook_task=True,
            )
            tool_event, tool_payload = hook_bridge._normalize_payload(
                "PostToolUse",
                {"cwd": project_dir, "session_id": "session-one", "turn_id": "turn-one", "summary": "ran shell"},
                persist_hook_task=True,
            )
            stop_event, stop_payload = hook_bridge._normalize_payload(
                "Stop",
                {"cwd": project_dir, "session_id": "session-one", "summary": "# Done"},
                persist_hook_task=True,
            )

        self.assertEqual(prompt_event, "before_task")
        self.assertEqual(tool_event, "after_tool")
        self.assertEqual(stop_event, "before_response")
        self.assertEqual(prompt_payload["task_id"], "task-explicit")
        self.assertEqual(tool_payload["task_id"], "task-explicit")
        self.assertEqual(stop_payload["task_id"], "task-explicit")

    def test_remembered_hook_task_id_is_sanitized_before_persistence(self) -> None:
        with _project_memory_env() as project_dir:
            secret_task_id = "token=SECRET123456789"
            hook_bridge._normalize_payload(
                "UserPromptSubmit",
                {
                    "cwd": project_dir,
                    "task_id": secret_task_id,
                    "session_id": "session-one",
                    "prompt": "Secret task id",
                },
                persist_hook_task=True,
            )
            recalled = hook_bridge._recall_hook_task(f"session_id:session-one|cwd:{project_dir}")

        self.assertEqual(recalled, "token=[REDACTED]")
        self.assertNotIn("SECRET123456789", recalled)

    def test_hook_task_sqlite_connections_are_closed(self) -> None:
        connections = []

        class FakeCursor:
            def fetchone(self) -> tuple[str] | None:
                return (json.dumps({"task_id": "task-from-db"}),)

        class FakeConnection:
            def __init__(self) -> None:
                self.closed = False

            def __enter__(self) -> "FakeConnection":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def execute(self, *args: object) -> FakeCursor:
                return FakeCursor()

            def close(self) -> None:
                self.closed = True

        def fake_connect(db_path: str) -> FakeConnection:
            connection = FakeConnection()
            connections.append(connection)
            return connection

        with (
            mock.patch("init_storage.ensure_storage_layout", return_value={"db_path": "memory.db"}),
            mock.patch.object(hook_bridge.sqlite3, "connect", side_effect=fake_connect),
        ):
            hook_bridge._remember_hook_task("session:one", "task-one")
            recalled = hook_bridge._recall_hook_task("session:one")

        self.assertEqual(recalled, "task-from-db")
        self.assertEqual(len(connections), 2)
        self.assertTrue(all(connection.closed for connection in connections))


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
