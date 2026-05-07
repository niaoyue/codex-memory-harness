from __future__ import annotations

from contextlib import contextmanager
import io
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
import hook_runner
import hook_config
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


class HookBridgeTests(unittest.TestCase):
    def _run_main_with_fake_runner(
        self,
        codex_event: str,
        payload: dict[str, object],
    ) -> tuple[int, list[str | None], list[tuple[str, dict[str, object]]]]:
        created_cwd = []
        calls = []
        previous = os.environ.get("CODEX_MEMORY_CWD")
        try:
            os.environ["CODEX_MEMORY_CWD"] = "E:/wrong"

            class FakeRunner:
                def __init__(self) -> None:
                    created_cwd.append(os.environ.get("CODEX_MEMORY_CWD"))

                def run_event(self, event: str, normalized_payload: dict[str, object]) -> dict[str, object]:
                    calls.append((event, normalized_payload))
                    return {"degraded": False, "event": event, "payload": normalized_payload}

            with (
                mock.patch.object(hook_bridge, "_load_stdin_payload", return_value=payload),
                mock.patch.object(hook_bridge, "HookRunner", FakeRunner),
                mock.patch.object(sys, "argv", ["hook_bridge.py", "--codex-event", codex_event]),
            ):
                exit_code = hook_bridge.main()
        finally:
            if previous is None:
                os.environ.pop("CODEX_MEMORY_CWD", None)
            else:
                os.environ["CODEX_MEMORY_CWD"] = previous

        return exit_code, created_cwd, calls

    def test_maps_stop_to_before_response_without_completing_task(self) -> None:
        event, payload = hook_bridge._normalize_payload(
            "Stop",
            {"task_id": "task-one", "summary": "ready", "summary_markdown": "# Done"},
        )

        self.assertNotEqual(event, "on_task_complete")
        self.assertEqual(event, "before_response")
        self.assertEqual(payload["task_id"], "task-one")
        self.assertEqual(payload["summary"], "ready")
        self.assertEqual(payload["summary_markdown"], "# Done")
        self.assertTrue(payload["writeback"])

    def test_maps_explicit_task_complete_to_completion_event(self) -> None:
        for codex_event in ("TaskComplete", "OnTaskComplete", "codex-memory-complete"):
            with self.subTest(codex_event=codex_event):
                event, payload = hook_bridge._normalize_payload(
                    codex_event,
                    {"task_id": "task-one", "summary": "ready", "summary_markdown": "# Done"},
                )

                self.assertEqual(event, "on_task_complete")
                self.assertEqual(payload["task_id"], "task-one")
                self.assertEqual(payload["summary"], "ready")
                self.assertEqual(payload["summary_markdown"], "# Done")

    def test_stop_uses_summary_as_completion_markdown_fallback(self) -> None:
        event, payload = hook_bridge._normalize_payload(
            "Stop",
            {"task_id": "task-one", "summary": "# Ready"},
        )

        self.assertEqual(event, "before_response")
        self.assertEqual(payload["summary_markdown"], "# Ready")
        self.assertTrue(payload["writeback"])

    def test_stop_uses_message_as_completion_markdown_fallback(self) -> None:
        event, payload = hook_bridge._normalize_payload(
            "Stop",
            {"task_id": "task-one", "message": "# Done"},
        )

        self.assertEqual(event, "before_response")
        self.assertEqual(payload["summary"], "# Done")
        self.assertEqual(payload["summary_markdown"], "# Done")
        self.assertTrue(payload["writeback"])

    def test_post_tool_preserves_cwd_fields(self) -> None:
        event, payload = hook_bridge._normalize_payload(
            "PostToolUse",
            {"task_id": "task-one", "summary": "ran", "workingDirectory": "E:/repo"},
        )

        self.assertEqual(event, "after_tool")
        self.assertEqual(payload["cwd"], "E:/repo")
        self.assertEqual(payload["workingDirectory"], "E:/repo")

    def test_stop_preserves_cwd_fields(self) -> None:
        event, payload = hook_bridge._normalize_payload(
            "Stop",
            {"task_id": "task-one", "message": "# Done", "working_directory": "E:/repo"},
        )

        self.assertEqual(event, "before_response")
        self.assertEqual(payload["cwd"], "E:/repo")
        self.assertEqual(payload["working_directory"], "E:/repo")

    def test_main_dispatches_stop_to_before_response(self) -> None:
        calls = []

        class FakeRunner:
            def run_event(self, event: str, normalized_payload: dict[str, object]) -> dict[str, object]:
                calls.append((event, normalized_payload))
                return {"degraded": False, "event": event}

        with (
            mock.patch.object(hook_bridge, "_load_stdin_payload", return_value={"task_id": "task-one", "message": "# Done"}),
            mock.patch.object(hook_bridge, "HookRunner", FakeRunner),
            mock.patch.object(sys, "argv", ["hook_bridge.py", "--codex-event", "Stop"]),
        ):
            exit_code = hook_bridge.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0][0], "before_response")
        self.assertEqual(calls[0][1]["summary_markdown"], "# Done")
        self.assertTrue(calls[0][1]["writeback"])

    def test_main_dispatches_explicit_task_complete_to_completion_event(self) -> None:
        calls = []

        class FakeRunner:
            def run_event(self, event: str, normalized_payload: dict[str, object]) -> dict[str, object]:
                calls.append((event, normalized_payload))
                return {"degraded": False, "event": event}

        with (
            mock.patch.object(hook_bridge, "_load_stdin_payload", return_value={"task_id": "task-one", "message": "# Done"}),
            mock.patch.object(hook_bridge, "HookRunner", FakeRunner),
            mock.patch.object(sys, "argv", ["hook_bridge.py", "--codex-event", "TaskComplete"]),
        ):
            exit_code = hook_bridge.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0][0], "on_task_complete")
        self.assertEqual(calls[0][1]["summary_markdown"], "# Done")

    def test_plugin_hooks_cover_recommended_official_events(self) -> None:
        hooks = json.loads(
            (PROJECT_ROOT / "plugins" / "codex-memory" / "hooks.json").read_text(
                encoding="utf-8",
            )
        )
        events = set(hooks["hooks"].keys())

        self.assertIn("UserPromptSubmit", events)
        self.assertIn("PostToolUse", events)
        self.assertIn("Stop", events)

    def test_plugin_hooks_route_through_utf8_safe_launcher(self) -> None:
        hooks = json.loads(
            (PROJECT_ROOT / "plugins" / "codex-memory" / "hooks.json").read_text(
                encoding="utf-8",
            )
        )
        commands: list[str] = []
        for event_hooks in hooks["hooks"].values():
            for item in event_hooks:
                for hook in item["hooks"]:
                    commands.append(hook["command"])

        self.assertTrue(commands)
        for command in commands:
            self.assertIn("hook_launcher.", command)
            self.assertIn("--codex-event", command)
            self.assertNotIn("codexm.ps1", command)
            self.assertNotIn("py -X utf8", command)

    def test_hook_config_can_generate_posix_launchers(self) -> None:
        hooks = hook_config.hooks_config("posix")
        commands: list[str] = []
        for event_hooks in hooks["hooks"].values():
            for item in event_hooks:
                for hook in item["hooks"]:
                    commands.append(hook["command"])

        self.assertTrue(commands)
        for command in commands:
            self.assertIn("sh ./scripts/hook_launcher.sh --codex-event", command)
            self.assertNotIn("powershell", command)
            self.assertNotIn("py -X utf8", command)

    def test_hook_launcher_is_ascii_only_for_windows_powershell_51(self) -> None:
        script = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts" / "hook_launcher.ps1"
        text = script.read_text(encoding="utf-8")

        text.encode("ascii")
        self.assertIn("hook_bridge.py", text)
        self.assertNotIn("here-string", text.lower())

    def test_posix_hook_launcher_is_ascii_only(self) -> None:
        script = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts" / "hook_launcher.sh"
        text = script.read_text(encoding="utf-8")

        text.encode("ascii")
        self.assertIn("hook_bridge.py", text)
        self.assertIn("try_python python3.12", text)

    def test_main_applies_payload_cwd_before_creating_runner(self) -> None:
        with tempfile.TemporaryDirectory() as project_dir:
            exit_code, created_cwd, calls = self._run_main_with_fake_runner(
                "UserPromptSubmit",
                {"prompt": "Fix client login", "cwd": project_dir},
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(created_cwd, [project_dir])
        self.assertEqual(calls[0][0], "before_task")

    def test_main_applies_post_tool_cwd_before_creating_runner(self) -> None:
        with tempfile.TemporaryDirectory() as project_dir:
            exit_code, created_cwd, calls = self._run_main_with_fake_runner(
                "PostToolUse",
                {"task_id": "task-one", "tool_name": "shell", "summary": "ran", "cwd": project_dir},
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(created_cwd, [project_dir])
        self.assertEqual(calls[0][0], "after_tool")

    def test_main_applies_stop_cwd_before_creating_runner(self) -> None:
        with tempfile.TemporaryDirectory() as project_dir:
            exit_code, created_cwd, calls = self._run_main_with_fake_runner(
                "Stop",
                {"task_id": "task-one", "message": "# Done", "workingDirectory": project_dir},
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(created_cwd, [project_dir])
        self.assertEqual(calls[0][0], "before_response")

    def test_stop_writeback_preserves_open_task_status(self) -> None:
        with _project_memory_env():
            store = memory_store.MemoryStore()
            runner = hook_bridge.HookRunner(memory_store=store)
            runner.run_event("before_task", {"task_id": "task-one", "objective": "Keep working"})
            event, payload = hook_bridge._normalize_payload(
                "Stop",
                {"task_id": "task-one", "summary": "# Response checkpoint"},
            )

            result = runner.run_event(event, payload)
            state = store.get_task_state("task-one")
            summary = store.get_task_summary("task-one")

        self.assertEqual(event, "before_response")
        self.assertEqual(state["status"], "open")
        self.assertEqual(summary["summary_markdown"], "# Response checkpoint")
        self.assertFalse(result["result"]["writeback"]["task_completed"])
        self.assertIn("distillation_result", result["result"]["writeback"])

    def test_mcp_config_uses_python_resolving_launcher(self) -> None:
        config = json.loads(
            (PROJECT_ROOT / "plugins" / "codex-memory" / ".mcp.json").read_text(
                encoding="utf-8",
            )
        )
        server = config["mcpServers"]["codex-memory"]

        self.assertIn(server["command"], {"powershell", "sh"})
        self.assertTrue(
            "./scripts/mcp_launcher.ps1" in server["args"]
            or "./scripts/mcp_launcher.sh" in server["args"]
        )
        self.assertNotEqual(server["command"], "py")

    def test_mcp_launcher_is_ascii_only_for_windows_powershell_51(self) -> None:
        script = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts" / "mcp_launcher.ps1"
        text = script.read_text(encoding="utf-8")

        text.encode("ascii")
        self.assertIn("memory_server.py", text)

    def test_posix_mcp_launcher_is_ascii_only(self) -> None:
        script = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts" / "mcp_launcher.sh"
        text = script.read_text(encoding="utf-8")

        text.encode("ascii")
        self.assertIn("memory_server.py", text)
        self.assertIn("try_python python3.12", text)

    def test_hook_runner_reports_missing_payload_file_as_degraded_json(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        with tempfile.TemporaryDirectory() as project_dir:
            output = io.StringIO()
            try:
                with (
                    mock.patch("sys.stdout", output),
                    mock.patch.object(
                        sys,
                        "argv",
                        [
                            "hook_runner.py",
                            "--event",
                            "before_response",
                            "--memory-scope",
                            "project",
                            "--memory-cwd",
                            project_dir,
                            "--payload-file",
                            str(Path(project_dir) / "missing.json"),
                        ],
                    ),
                ):
                    exit_code = hook_runner.main()
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertFalse(result["ok"])
        self.assertTrue(result["degraded"])
        self.assertIn("FileNotFoundError", result["reason"])

def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
