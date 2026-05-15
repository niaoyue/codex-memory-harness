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
from workspace_test_helpers import MemoryEnv, client_server_route_plan, multi_route_plan, route_plan


class SubagentRuntimeDecisionTests(unittest.TestCase):
    def test_single_route_records_main_agent_serial_decision(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )

        runtime = result["result"]["task_state"]["metadata"]["workspace_routing"]["subagent_runtime"]
        self.assertEqual(runtime["status"], "main_agent_serial")
        self.assertEqual(runtime["execution_model"], "main_agent_serial")
        self.assertFalse(runtime["autostart"])
        self.assertFalse(runtime["recommended"])

    def test_multi_route_records_subagent_recommendation_without_autostart(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=multi_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI and docs",
                        "working_set": ["client/Assets/Login.cs", "docs/login.md"],
                    },
                )

        runtime = result["result"]["task_state"]["metadata"]["workspace_routing"]["subagent_runtime"]
        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertEqual(runtime["status"], "recommended_not_started")
        self.assertEqual(runtime["execution_model"], "host_subagent_or_manual")
        self.assertFalse(runtime["autostart"])
        self.assertTrue(runtime["recommended"])
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertTrue(runtime["requires_user_explicit_choice"])
        self.assertEqual(runtime["main_agent_action"], "record_dispatch_plan_for_host_or_manual_use")
        self.assertIn("subagent_dispatch_plan", routing)
        self.assertEqual(runtime["planned_specialists"], 2)

    def test_explicit_subagent_request_records_host_dispatch_action(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=multi_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI and docs",
                        "working_set": ["client/Assets/Login.cs", "docs/login.md"],
                        "use_subagents": True,
                        "subagent_mode": "host",
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        dispatch_plan = routing["subagent_dispatch_plan"]
        self.assertEqual(runtime["status"], "requested_not_started")
        self.assertEqual(runtime["trigger"], "user_explicit")
        self.assertFalse(runtime["autostart"])
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["requires_user_explicit_choice"])
        self.assertEqual(runtime["main_agent_action"], "read_dispatch_plan_and_call_host_subagents")
        self.assertTrue(runtime["dispatch_plan_available"])
        self.assertEqual(runtime["host_spawn_request_count"], len(dispatch_plan["host_spawn_requests"]))
        self.assertGreater(runtime["host_spawn_request_count"], 0)

    def test_route_policy_single_route_records_host_dispatch_action(self) -> None:
        plan = route_plan()
        plan["subagent_runtime_policy"] = {
            "execution_model": "host_subagent_or_manual",
            "autostart": False,
            "reason": "Configured route policy requires host SubAgent dispatch.",
        }
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=plan):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-policy-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["status"], "recommended_not_started")
        self.assertEqual(runtime["trigger"], "route_policy")
        self.assertEqual(runtime["execution_model"], "host_subagent_or_manual")
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["requires_user_explicit_choice"])
        self.assertEqual(runtime["main_agent_action"], "read_dispatch_plan_and_call_host_subagents")
        self.assertIn("subagent_dispatch_plan", routing)
        self.assertGreater(runtime["host_spawn_request_count"], 0)

    def test_openspec_working_set_forces_host_subagent_required(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "openspec-required-task",
                        "objective": "Implement OpenSpec change contract",
                        "working_set": ["openspec/changes/require-subagent-dispatch/tasks.md"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        dispatch_plan = routing["subagent_dispatch_plan"]
        self.assertEqual(runtime["status"], "dispatch_required_not_started")
        self.assertEqual(runtime["trigger"], "openspec_required")
        self.assertEqual(runtime["execution_model"], "host_subagent_required")
        self.assertTrue(runtime["autostart"])
        self.assertTrue(runtime["dispatch_required"])
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertEqual(runtime["host_spawn_request_count"], len(dispatch_plan["host_spawn_requests"]))
        self.assertEqual(dispatch_plan["execution_model"], "host_subagent_required")
        self.assertTrue(dispatch_plan["autostart"])
        self.assertTrue(dispatch_plan["dispatch_required"])

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

    def test_main_agent_serial_route_policy_suppresses_complex_dispatch_plan(self) -> None:
        plan = route_plan()
        plan["risk_level"] = "high"
        plan["requirements_gate"] = {
            "task_intent": "system_change",
            "blocking": False,
            "missing": [],
            "open_questions": [],
        }
        plan["subagent_runtime_policy"] = {
            "execution_model": "main_agent_serial",
            "autostart": False,
            "reason": "Configured route policy requires main Agent serial execution.",
        }
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=plan):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "serial-policy-task",
                        "objective": "生成一个完整词典应用，包含查词、收藏和复习工作流",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["status"], "main_agent_serial")
        self.assertEqual(runtime["trigger"], "policy_disabled")
        self.assertEqual(runtime["execution_model"], "main_agent_serial")
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["dispatch_plan_required"])
        self.assertNotIn("subagent_dispatch_plan", routing)

    def test_complex_single_route_app_task_records_host_dispatch_action(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "dict-app-task",
                        "objective": "生成一个模拟扇贝词典的应用，包含查词、收藏、学习进度和复习页面",
                        "working_set": ["client/Assets/Login.cs"],
                        "acceptance": ["用户可以查词、收藏单词并查看学习进度"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        dispatch_plan = routing["subagent_dispatch_plan"]
        self.assertEqual(runtime["status"], "recommended_not_started")
        self.assertEqual(runtime["trigger"], "complex_task")
        self.assertEqual(runtime["execution_model"], "host_subagent_or_manual")
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["requires_user_explicit_choice"])
        self.assertEqual(runtime["main_agent_action"], "read_dispatch_plan_and_call_host_subagents")
        self.assertGreater(runtime["host_spawn_request_count"], 0)
        self.assertEqual(runtime["host_spawn_request_count"], len(dispatch_plan["host_spawn_requests"]))

    def test_blocking_requirements_gate_prevents_complex_task_dispatch(self) -> None:
        plan = route_plan()
        plan["risk_level"] = "release_blocking"
        plan["fallback_action"] = "ask_user"
        plan["requirements_gate"] = {
            "blocking": True,
            "open_questions": ["缺少发布回滚方案"],
            "missing": [{"field": "rollback_plan"}],
        }
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=plan):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "blocked-dict-app-task",
                        "objective": "生成一个模拟扇贝词典的应用",
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["status"], "requirements_blocked")
        self.assertEqual(runtime["trigger"], "requirements_gate")
        self.assertEqual(runtime["main_agent_action"], "ask_user_for_requirements")
        self.assertEqual(runtime["fallback_action"], "ask_user")
        self.assertFalse(runtime["recommended"])
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["dispatch_plan_required"])
        self.assertNotIn("subagent_dispatch_plan", routing)

    def test_complex_unknown_route_gets_fallback_dispatch_request(self) -> None:
        plan = route_plan()
        plan["mode"] = "unknown_low_confidence"
        plan["affected_projects"] = []
        plan["routes"] = []
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=plan):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "unknown-dict-app-task",
                        "objective": "生成一个模拟扇贝词典的应用",
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        dispatch_plan = routing["subagent_dispatch_plan"]
        self.assertEqual(runtime["trigger"], "complex_task")
        self.assertEqual(runtime["planned_specialists"], 1)
        self.assertGreater(runtime["host_spawn_request_count"], 0)
        self.assertEqual(dispatch_plan["host_spawn_requests"][0]["agent_type"], "worker")
        self.assertEqual(routing["bindings"][0]["project_id"], "workspace")

    def test_user_can_disable_complex_task_subagent_dispatch(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "main-agent-only-task",
                        "objective": "生成一个模拟扇贝词典的应用，但 main agent only",
                        "use_subagents": False,
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["status"], "main_agent_serial")
        self.assertEqual(runtime["trigger"], "user_disabled")
        self.assertFalse(runtime["recommended"])
        self.assertNotIn("subagent_dispatch_plan", routing)

    def test_subagent_artifact_updates_runtime_observed_status(self) -> None:
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

        runtime = result["result"]["task_state"]["metadata"]["workspace_routing"]["subagent_runtime"]
        self.assertEqual(runtime["status"], "artifact_recorded")
        self.assertEqual(runtime["actual_subagents"], 1)
        self.assertEqual(runtime["artifact_actor_ids"], ["binding-client-route"])

    def test_adaptive_after_tool_preserves_recorded_subagent_artifact_runtime(self) -> None:
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
                runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "binding_id": "binding-client-route",
                        "tool_name": "subagent",
                        "summary": "Client agent completed a checkpoint",
                        "touched_paths": ["client/Assets/Login.cs"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "edit",
                        "summary": "Main agent touched docs",
                        "touched_paths": ["docs/login.md"],
                    },
                )

        runtime = result["result"]["task_state"]["metadata"]["workspace_routing"]["subagent_runtime"]
        self.assertEqual(runtime["status"], "artifact_recorded")
        self.assertEqual(runtime["actual_subagents"], 1)
        self.assertEqual(runtime["artifact_actor_ids"], ["binding-client-route"])

    def test_adaptive_after_tool_preserves_dispatch_plan_when_runtime_recommends_host(self) -> None:
        with MemoryEnv():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[route_plan(), multi_route_plan()],
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
                        "tool_name": "edit",
                        "summary": "Touched docs path",
                        "touched_paths": ["docs/login.md"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertTrue(runtime["dispatch_plan_available"])
        self.assertGreater(runtime["host_spawn_request_count"], 0)
        self.assertIn("subagent_dispatch_plan", routing)
        self.assertIn("adaptive_subagent_dispatch_plan", routing)
        self.assertEqual(
            runtime["host_spawn_request_count"],
            len(routing["subagent_dispatch_plan"]["host_spawn_requests"]),
        )

    def test_adaptive_after_tool_replaces_stale_complex_dispatch_plan(self) -> None:
        with MemoryEnv():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[route_plan(), multi_route_plan()],
            ):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "dict-app-task",
                        "objective": "生成一个模拟扇贝词典的应用",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "dict-app-task",
                        "tool_name": "edit",
                        "summary": "Touched docs path",
                        "touched_paths": ["docs/login.md"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        top_plan = routing["subagent_dispatch_plan"]
        adaptive_plan = routing["adaptive_subagent_dispatch_plan"]
        self.assertEqual(top_plan, adaptive_plan)
        self.assertEqual(runtime["host_spawn_request_count"], len(top_plan["host_spawn_requests"]))
        self.assertGreater(len(top_plan["host_spawn_requests"]), 1)
        self.assertEqual(top_plan["host_spawn_requests"][0]["role"], "Workspace Coordinator")

if __name__ == "__main__":
    unittest.main()
