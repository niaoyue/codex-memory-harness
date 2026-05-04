from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import subagent_runtime_planner
import subagent_scheduler
import hook_runner
import memory_store
import workspace_lifecycle
import workspace_subagents


class SubagentRuntimePlannerTests(unittest.TestCase):
    def test_feature_story_single_route_is_autonomously_dispatchable(self) -> None:
        plan = _route_plan(intent="feature_story")
        bindings = workspace_subagents.create_bindings(plan)

        runtime = subagent_runtime_planner.runtime_decision(plan, bindings, {"objective": "Add review history"})

        self.assertEqual(runtime["trigger"], "autonomous_task_analysis")
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertEqual(runtime["main_agent_action"], "read_dispatch_plan_and_call_host_subagents")
        self.assertEqual(runtime["decision_factors"]["task_intent"], "feature_story")
        self.assertIn("route_specialist", runtime["dispatch_roles"])
        self.assertIn("route_reviewer", runtime["dispatch_roles"])

    def test_small_low_complexity_single_route_stays_on_main_agent(self) -> None:
        plan = _route_plan(intent="small_change")
        bindings = workspace_subagents.create_bindings(plan)

        runtime = subagent_runtime_planner.runtime_decision(plan, bindings, {"objective": "Fix button copy"})

        self.assertEqual(runtime["trigger"], "serial_default")
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertEqual(runtime["execution_model"], "main_agent_serial")
        self.assertEqual(runtime["dispatch_roles"], [])

    def test_policy_enabled_false_keeps_complex_task_on_main_agent(self) -> None:
        plan = _route_plan(intent="feature_story", risk="high")
        plan["subagent_runtime_policy"] = {
            "enabled": False,
            "execution_model": "host_subagent_or_manual",
            "reason": "Project requires main Agent serial execution.",
        }
        bindings = workspace_subagents.create_bindings(plan)

        runtime = subagent_runtime_planner.runtime_decision(
            plan,
            bindings,
            {"objective": "生成一个完整词典应用，包含查词、收藏和复习工作流"},
        )

        self.assertEqual(runtime["status"], "main_agent_serial")
        self.assertEqual(runtime["trigger"], "policy_disabled")
        self.assertEqual(runtime["execution_model"], "main_agent_serial")
        self.assertFalse(runtime["recommended"])
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["dispatch_plan_required"])
        self.assertEqual(runtime["dispatch_roles"], [])
        self.assertTrue(runtime["decision_factors"]["policy_disabled"])

    def test_policy_main_agent_serial_keeps_high_risk_task_on_main_agent(self) -> None:
        plan = _route_plan(intent="system_change", risk="high")
        plan["subagent_runtime_policy"] = {
            "execution_model": "main_agent_serial",
            "reason": "Run this project on the main Agent only.",
        }
        bindings = workspace_subagents.create_bindings(plan)

        runtime = subagent_runtime_planner.runtime_decision(plan, bindings, {"objective": "Implement release migration"})

        self.assertEqual(runtime["status"], "main_agent_serial")
        self.assertEqual(runtime["trigger"], "policy_disabled")
        self.assertEqual(runtime["execution_model"], "main_agent_serial")
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["dispatch_plan_required"])
        self.assertEqual(runtime["main_agent_action"], "execute_on_main_agent")

    def test_policy_host_subagent_or_manual_still_allows_dispatch(self) -> None:
        plan = _route_plan(intent="small_change")
        plan["subagent_runtime_policy"] = {
            "execution_model": "host_subagent_or_manual",
            "reason": "Configured policy allows host SubAgent dispatch.",
        }
        bindings = workspace_subagents.create_bindings(plan)

        runtime = subagent_runtime_planner.runtime_decision(plan, bindings, {"objective": "Fix button copy"})

        self.assertEqual(runtime["trigger"], "route_policy")
        self.assertEqual(runtime["execution_model"], "host_subagent_or_manual")
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertTrue(runtime["dispatch_plan_required"])
        self.assertEqual(runtime["main_agent_action"], "read_dispatch_plan_and_call_host_subagents")

    def test_route_reviewer_is_added_for_autonomous_feature_story(self) -> None:
        plan = _route_plan(intent="system_change", task_type="contract", risk="high")
        bindings = workspace_subagents.create_bindings(plan)
        runtime = subagent_runtime_planner.runtime_decision(plan, bindings, {"objective": "Update API contract"})

        dispatch_plan = subagent_scheduler.build_dispatch_plan(plan, bindings, runtime)

        roles = [item["role"] for item in dispatch_plan["host_spawn_requests"]]
        self.assertIn("Route Review Specialist", roles)
        reviewer = next(item for item in dispatch_plan["items"] if item["role"] == "Route Review Specialist")
        self.assertTrue(reviewer["dependencies"])
        self.assertIn("Do not edit files", reviewer["prompt"])

    def test_lifecycle_feature_story_single_route_generates_reviewer_request(self) -> None:
        plan = _route_plan(intent="feature_story")
        with _memory_env():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=plan):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "feature-story-task",
                        "objective": "Add dictionary review history",
                        "working_set": ["src/App.tsx"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        roles = [item["role"] for item in routing["subagent_dispatch_plan"]["host_spawn_requests"]]
        self.assertEqual(runtime["trigger"], "autonomous_task_analysis")
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertEqual(runtime["main_agent_action"], "read_dispatch_plan_and_call_host_subagents")
        self.assertIn("Route Review Specialist", roles)


def _route_plan(
    *,
    intent: str,
    task_type: str = "implementation",
    risk: str = "medium",
) -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "planner-task",
        "route_plan_id": "route-planner-task",
        "mode": "single_project",
        "affected_projects": ["admin-web"],
        "routes": [
            {
                "route_id": "admin-route",
                "project_id": "admin-web",
                "domain": "backoffice_web",
                "cwd": ".",
                "task_type": task_type,
                "assigned_scope": ["src/App.tsx"],
                "rules": ["workspace/base", "backoffice/base", "web/base"],
                "verification_profile_ids": ["primary"],
                "confidence": 0.9,
            }
        ],
        "task_type": task_type,
        "risk_level": risk,
        "requirements_gate": {
            "version": 1,
            "task_intent": intent,
            "status": "passed",
            "blocking": False,
            "requirement_sources": ["user_request"],
            "missing": [],
            "open_questions": [],
            "assumptions_policy": "test",
            "technical_decision_policy": "test",
        },
        "confidence": 0.9,
        "reasons": ["test"],
        "verification_plan": [],
    }


class _memory_env:
    def __enter__(self) -> str:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = workspace_lifecycle.os.environ.get("CODEX_MEMORY_CWD")
        self.old_scope = workspace_lifecycle.os.environ.get("CODEX_MEMORY_SCOPE")
        workspace_lifecycle.os.environ["CODEX_MEMORY_CWD"] = self.temp_dir.name
        workspace_lifecycle.os.environ["CODEX_MEMORY_SCOPE"] = "project"
        Path(self.temp_dir.name, ".codex").mkdir()
        return self.temp_dir.name

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _restore_env("CODEX_MEMORY_CWD", self.old_cwd)
        _restore_env("CODEX_MEMORY_SCOPE", self.old_scope)
        self.temp_dir.cleanup()


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        workspace_lifecycle.os.environ.pop(name, None)
    else:
        workspace_lifecycle.os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
