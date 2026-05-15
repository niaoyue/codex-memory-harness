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

import hook_runner
import memory_store
import workspace_lifecycle
from workspace_test_helpers import MemoryEnv, multi_route_plan, route_plan


class RequiredSubagentDispatchReviewTests(unittest.TestCase):
    def test_before_response_blocks_unrun_required_dispatch(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "openspec-required-task",
                        "objective": "Implement OpenSpec change contract",
                        "working_set": ["openspec/changes/require-subagent-dispatch/tasks.md"],
                    },
                )
                result = runner.run_event("before_response", {"task_id": "openspec-required-task"})

        review = result["result"]["workspace_routing_review"]
        self.assertFalse(review["ok"])
        self.assertEqual(review["gaps"][0]["type"], "required_subagent_dispatch")
        self.assertTrue(review["gaps"][0]["blocking"])
        self.assertEqual(review["subagent_runtime"]["status"], "dispatch_required_not_started")

    def test_before_response_blocks_partial_required_dispatch(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=multi_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                before = _start_required_task(runner, "openspec-required-partial")
                first_request = _host_requests(before)[0]
                runner.run_event(
                    "after_tool",
                    {
                        "task_id": "openspec-required-partial",
                        "tool_name": "subagent",
                        "summary": "Only one required dispatch item completed.",
                        "dispatch_id": first_request["dispatch_id"],
                        "binding_id": first_request["binding_id"],
                        "subagent_id": first_request["subagent_id"],
                        "touched_paths": [],
                    },
                )
                result = runner.run_event("before_response", {"task_id": "openspec-required-partial"})

        review = result["result"]["workspace_routing_review"]
        self.assertFalse(review["ok"])
        required_gap = next(gap for gap in review["gaps"] if gap["type"] == "required_subagent_dispatch")
        self.assertGreater(len(required_gap["missing_dispatch_requests"]), 0)

    def test_before_response_allows_all_required_dispatch_artifacts(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=multi_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                before = _start_required_task(runner, "openspec-required-complete")
                for request in _host_requests(before):
                    runner.run_event(
                        "after_tool",
                        {
                            "task_id": "openspec-required-complete",
                            "tool_name": "subagent",
                            "summary": f"Completed {request['dispatch_id']}",
                            "dispatch_id": request["dispatch_id"],
                            "binding_id": request["binding_id"],
                            "subagent_id": request["subagent_id"],
                            "touched_paths": [],
                        },
                    )
                result = runner.run_event("before_response", {"task_id": "openspec-required-complete"})

        review = result["result"]["workspace_routing_review"]
        self.assertTrue(review["ok"])
        self.assertNotIn("required_subagent_dispatch", [gap["type"] for gap in review["gaps"]])

    def test_same_actor_checkpoint_does_not_satisfy_multiple_dispatches(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=multi_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                before = _start_required_task(runner, "openspec-required-same-actor")
                requests = _host_requests(before)
                summarize = next(request for request in requests if request["dispatch_id"].endswith("-summarize"))
                for request in requests:
                    if request["dispatch_id"] == summarize["dispatch_id"]:
                        continue
                    runner.run_event(
                        "after_tool",
                        {
                            "task_id": "openspec-required-same-actor",
                            "tool_name": "subagent",
                            "summary": f"Completed {request['dispatch_id']}",
                            "dispatch_id": request["dispatch_id"],
                            "binding_id": request["binding_id"],
                            "subagent_id": request["subagent_id"],
                            "touched_paths": [],
                        },
                    )
                result = runner.run_event("before_response", {"task_id": "openspec-required-same-actor"})

        review = result["result"]["workspace_routing_review"]
        self.assertFalse(review["ok"])
        required_gap = next(gap for gap in review["gaps"] if gap["type"] == "required_subagent_dispatch")
        self.assertEqual(required_gap["missing_dispatch_requests"], [summarize["dispatch_id"]])

    def test_openspec_required_dispatch_ignores_user_disable(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "openspec-user-disabled-task",
                        "objective": "Implement OpenSpec change contract without subagent",
                        "working_set": ["openspec/changes/require-subagent-dispatch/tasks.md"],
                        "use_subagents": False,
                    },
                )

        runtime = result["result"]["task_state"]["metadata"]["workspace_routing"]["subagent_runtime"]
        self.assertEqual(runtime["status"], "dispatch_required_not_started")
        self.assertEqual(runtime["trigger"], "openspec_required")
        self.assertEqual(runtime["execution_model"], "host_subagent_required")
        self.assertTrue(runtime["dispatch_required"])
        self.assertTrue(runtime["host_dispatch_allowed"])


def _start_required_task(runner: hook_runner.HookRunner, task_id: str) -> dict[str, object]:
    return runner.run_event(
        "before_task",
        {
            "task_id": task_id,
            "objective": "Implement OpenSpec change contract",
            "working_set": ["openspec/changes/require-subagent-dispatch/tasks.md"],
        },
    )


def _host_requests(result: dict[str, object]) -> list[dict[str, object]]:
    return result["result"]["task_state"]["metadata"]["workspace_routing"]["subagent_dispatch_plan"]["host_spawn_requests"]


if __name__ == "__main__":
    unittest.main()
