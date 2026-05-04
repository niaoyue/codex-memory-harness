from __future__ import annotations

import os
import sys
import tempfile
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
from workspace_test_helpers import (
    MemoryEnv,
    client_server_route_plan,
    multi_route_plan,
    restore_env,
    root_and_docs_route_plan,
    route_plan,
    routing_mocks,
)
import memory_store
import workspace_lifecycle


class WorkspaceHookIntegrationTests(unittest.TestCase):
    def test_before_task_records_route_plan_and_bindings_in_metadata(self) -> None:
        with MemoryEnv() as temp_dir:
            with routing_mocks():
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )

            metadata = result["result"]["task_state"]["metadata"]

        self.assertIn("workspace_routing", metadata)
        self.assertEqual(metadata["workspace_routing"]["route_plan"]["mode"], "single_project")
        self.assertEqual(metadata["workspace_routing"]["bindings"][0]["project_id"], "client-unity")
        self.assertFalse(Path(temp_dir).exists())

    def test_explicit_subagent_lifecycle_keeps_dispatch_plan_across_after_tool(self) -> None:
        with MemoryEnv():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[route_plan(), multi_route_plan()],
            ):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                before = runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI and docs with subagents",
                        "working_set": ["client/Assets/Login.cs"],
                        "use_subagents": True,
                    },
                )
                after = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "edit",
                        "summary": "Touched docs path",
                        "touched_paths": ["docs/login.md"],
                    },
                )

        before_routing = before["result"]["task_state"]["metadata"]["workspace_routing"]
        after_routing = after["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertIn("subagent_dispatch_plan", before_routing)
        self.assertIn("subagent_dispatch_plan", after_routing)
        self.assertIn("adaptive_subagent_dispatch_plan", after_routing)
        self.assertEqual(
            after_routing["subagent_runtime"]["host_spawn_request_count"],
            len(after_routing["subagent_dispatch_plan"]["host_spawn_requests"]),
        )

    def test_before_task_returns_sanitized_task_id(self) -> None:
        secret = "sampletokenvalue12345"
        with MemoryEnv():
            runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
            result = runner.run_event(
                "before_task",
                {
                    "task_id": f"token={secret}",
                    "objective": "Safe objective",
                    "working_set": ["client/Assets/Login.cs"],
                },
            )

        payload = str(result)
        self.assertEqual(result["task_id"], "token=[REDACTED]")
        self.assertEqual(result["result"]["context_pack"]["task_id"], "token=[REDACTED]")
        self.assertNotIn(secret, payload)

    def test_after_tool_records_scope_guard_violations(self) -> None:
        with MemoryEnv():
            with routing_mocks():
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "edit",
                        "summary": "Touched server path",
                        "touched_paths": ["server/api/login.proto"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertFalse(routing["scope_guard"][0]["ok"])
        self.assertEqual(routing["scope_guard"][0]["violations"][0]["path"], "server/api/login.proto")

    def test_before_response_reports_workspace_routing_degradation(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", side_effect=RuntimeError("boom")):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )
                result = runner.run_event("before_response", {"task_id": "route-task"})

        review = result["result"]["workspace_routing_review"]
        self.assertTrue(review["ok"])
        self.assertEqual(review["gaps"][0]["type"], "workspace_routing")

    def test_routing_review_reports_failed_verification_aggregation(self) -> None:
        review = workspace_lifecycle.routing_review(
            {
                "metadata": {
                    "workspace_routing": {
                        "route_plan": {"verification_plan": [{"project_id": "client-unity"}]},
                        "verification_aggregation": {"overall_status": "blocked"},
                    }
                }
            }
        )

        self.assertFalse(review["ok"])
        self.assertEqual(review["gaps"][0]["type"], "verification")
        self.assertTrue(review["gaps"][0]["blocking"])

    def test_routing_review_reports_adaptive_routing_degradation(self) -> None:
        review = workspace_lifecycle.routing_review(
            {
                "metadata": {
                    "workspace_routing": {
                        "route_plan": {"mode": "single_project"},
                        "adaptive_degraded": {"degraded": True, "reason": "RuntimeError: boom"},
                    }
                }
            }
        )

        self.assertTrue(review["ok"])
        self.assertEqual(review["gaps"][0]["type"], "workspace_routing")
        self.assertEqual(review["gaps"][0]["reason"], "RuntimeError: boom")

    def test_after_tool_scope_guard_routes_paths_to_matching_specialist(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=multi_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI and docs",
                        "working_set": ["client/Assets/Login.cs", "docs/login.md"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "edit",
                        "summary": "Touched client path",
                        "touched_paths": ["client/Assets/Login.cs"],
                    },
                )

        scope_guard = result["result"]["task_state"]["metadata"]["workspace_routing"]["scope_guard"]
        self.assertEqual(len(scope_guard), 1)
        self.assertTrue(scope_guard[0]["ok"])
        self.assertEqual(scope_guard[0]["project_id"], "client-unity")

    def test_multi_scope_guard_normalizes_absolute_touched_paths_before_matching(self) -> None:
        bindings = workspace_lifecycle.create_bindings(multi_route_plan())
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            absolute_path = root / "client" / "Assets" / "Login.cs"

            scope_guard = workspace_lifecycle.safe_scope_guard(
                bindings,
                [str(absolute_path)],
                project_root=root,
            )

        self.assertEqual(len(scope_guard), 1)
        self.assertTrue(scope_guard[0]["ok"], scope_guard[0]["violations"])
        self.assertEqual(scope_guard[0]["project_id"], "client-unity")
        self.assertEqual(scope_guard[0]["allowed_paths"], ["client/Assets/Login.cs"])

    def test_scope_guard_prefers_most_specific_child_scope(self) -> None:
        bindings = workspace_lifecycle.create_bindings(root_and_docs_route_plan())

        scope_guard = workspace_lifecycle.safe_scope_guard(bindings, ["docs/guide.md"])

        self.assertEqual(len(scope_guard), 1)
        self.assertTrue(scope_guard[0]["ok"], scope_guard[0]["violations"])
        self.assertEqual(scope_guard[0]["project_id"], "design-docs")

    def test_after_tool_checks_scope_against_original_bindings_before_adaptive_reroute(self) -> None:
        with MemoryEnv():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[route_plan(), client_server_route_plan()],
            ):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "binding_id": "binding-client-route",
                        "project_id": "client-unity",
                        "tool_name": "edit",
                        "summary": "Touched server path",
                        "touched_paths": ["server/api/login.proto"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertIn("adaptive_route_plan", routing)
        self.assertFalse(routing["scope_guard"][0]["ok"])
        self.assertEqual(routing["scope_guard"][0]["violations"][0]["path"], "server/api/login.proto")

    def test_after_tool_uses_signaled_route_bindings_for_scope_guard(self) -> None:
        old_disable = os.environ.get("CODEX_WORKSPACE_ROUTING_DISABLE")
        with MemoryEnv():
            try:
                os.environ["CODEX_WORKSPACE_ROUTING_DISABLE"] = "1"
                store = memory_store.MemoryStore()
                runner = hook_runner.HookRunner(memory_store=store)
                store.upsert_task_state(
                    "route-task",
                    {
                        "objective": "Switch route",
                        "metadata": {
                            "workspace_routing": {
                                "bindings": [
                                    {
                                        "binding_mode": "specialist",
                                        "binding_id": "binding-docs-route",
                                        "subagent_id": "agent-docs-route",
                                        "project_id": "design-docs",
                                        "assigned_scope": ["docs"],
                                    }
                                ]
                            }
                        },
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "binding_id": "binding-client-route",
                        "signals": {"route_plan": route_plan()},
                        "touched_paths": ["client/Assets/Login.cs"],
                    },
                )
            finally:
                restore_env("CODEX_WORKSPACE_ROUTING_DISABLE", old_disable)

        scope_guard = result["result"]["task_state"]["metadata"]["workspace_routing"]["scope_guard"]
        self.assertTrue(scope_guard[0]["ok"], scope_guard[0]["violations"])
        self.assertEqual(scope_guard[0]["binding_id"], "binding-client-route")

    def test_after_tool_uses_adaptive_bindings_when_previous_bindings_are_empty(self) -> None:
        with MemoryEnv():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                return_value=route_plan(),
            ):
                store = memory_store.MemoryStore()
                runner = hook_runner.HookRunner(memory_store=store)
                store.upsert_task_state(
                    "route-task",
                    {
                        "objective": "Start unscoped",
                        "metadata": {"workspace_routing": {"bindings": []}},
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "touched_paths": ["client/Assets/Login.cs"],
                    },
                )

        scope_guard = result["result"]["task_state"]["metadata"]["workspace_routing"]["scope_guard"]
        self.assertTrue(scope_guard[0]["ok"], scope_guard[0]["violations"])
        self.assertEqual(scope_guard[0]["project_id"], "client-unity")

    def test_after_tool_uses_reported_binding_for_scope_guard(self) -> None:
        with MemoryEnv():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                return_value=client_server_route_plan(),
            ):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Update client server protocol",
                        "working_set": ["client/Assets/Login.cs", "server/api/login.proto"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "binding_id": "binding-client-route",
                        "project_id": "client-unity",
                        "tool_name": "subagent",
                        "summary": "Client agent touched server path",
                        "touched_paths": ["server/api/login.proto"],
                    },
                )

        scope_guard = result["result"]["task_state"]["metadata"]["workspace_routing"]["scope_guard"]
        self.assertFalse(scope_guard[0]["ok"])
        self.assertEqual(scope_guard[0]["binding_id"], "binding-client-route")
        self.assertEqual(scope_guard[0]["violations"][0]["path"], "server/api/login.proto")

    def test_after_tool_uses_adaptive_bindings_for_unbound_checkpoint(self) -> None:
        stale_plan = route_plan()
        expanded_plan = route_plan()
        expanded_plan["routes"][0]["assigned_scope"] = ["client/Assets", "tests"]
        with MemoryEnv():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[stale_plan, expanded_plan],
            ):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {"task_id": "route-task", "objective": "Fix client UI", "working_set": ["client/Assets/Login.cs"]},
                )
                result = runner.run_event(
                    "after_tool",
                    {"task_id": "route-task", "tool_name": "edit", "touched_paths": ["tests/test_workspace_router.py"]},
                )

        scope_guard = result["result"]["task_state"]["metadata"]["workspace_routing"]["scope_guard"]
        self.assertTrue(scope_guard[0]["ok"], scope_guard[0]["violations"])

if __name__ == "__main__":
    unittest.main()
