from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import hook_runner  # noqa: E402
import memory_store  # noqa: E402
import workspace_session  # noqa: E402
from workspace_test_helpers import MemoryEnv  # noqa: E402


class WorkspaceBeforeFirstWriteTests(unittest.TestCase):
    def test_before_first_write_calls_workspace_write_guard(self) -> None:
        with MemoryEnv() as temp_dir:
            runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
            route_plan = {"requirements_gate": {"blocking": False}}
            requirements_gate = {"blocking": False}
            guard_result = {
                "ok": True,
                "action": "allow_write",
                "effective_cwd": temp_dir,
                "binding": {"binding_id": "binding-one"},
            }
            with mock.patch.object(workspace_session, "write_guard", return_value=guard_result) as write_guard:
                result = runner.run_event(
                    "before_first_write",
                    {
                        "task_id": "route-task",
                        "session_id": "session-one",
                        "project_root": temp_dir,
                        "intended_paths": ["docs/a.md"],
                        "route_plan": route_plan,
                        "requirements_gate": requirements_gate,
                    },
                )

        self.assertEqual(result["event"], "before_first_write")
        self.assertTrue(result["result"]["write_allowed"])
        self.assertEqual(result["result"]["write_guard"]["action"], "allow_write")
        self.assertEqual(result["result"]["route_plan_source"], "payload")
        self.assertEqual(result["result"]["requirements_gate_source"], "payload")
        write_guard.assert_called_once()
        _, kwargs = write_guard.call_args
        self.assertEqual(kwargs["session_id"], "session-one")
        self.assertEqual(kwargs["task_id"], "route-task")
        self.assertEqual(kwargs["intended_paths"], ["docs/a.md"])
        self.assertIs(kwargs["route_plan"], route_plan)
        self.assertIs(kwargs["requirements_gate"], requirements_gate)

    def test_before_first_write_blocks_missing_identity_without_allocating_binding(self) -> None:
        with MemoryEnv() as temp_dir:
            runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
            with mock.patch.object(workspace_session, "write_guard") as write_guard:
                result = runner.run_event(
                    "before_first_write",
                    {
                        "task_id": "route-task",
                        "project_root": temp_dir,
                        "intended_paths": ["docs/a.md"],
                    },
                )

        self.assertFalse(result["result"]["write_allowed"])
        self.assertEqual(result["result"]["write_guard"]["action"], "missing_write_guard_identity")
        self.assertEqual(result["result"]["write_guard"]["missing"], ["session_id"])
        write_guard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
