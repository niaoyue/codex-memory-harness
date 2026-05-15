from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import subagent_scheduler
import workspace_subagents


class SubagentSchedulerTests(unittest.TestCase):
    def test_dispatch_plan_orders_coordinator_and_specialists(self) -> None:
        route_plan = _route_plan()
        bindings = workspace_subagents.create_bindings(route_plan)

        plan = subagent_scheduler.build_dispatch_plan(route_plan, bindings)

        self.assertFalse(plan["autostart"])
        self.assertEqual(plan["execution_model"], "host_subagent_or_manual")
        self.assertEqual(len(plan["host_spawn_requests"]), len(plan["items"]))
        self.assertEqual(plan["items"][0]["phase"], "prepare")
        self.assertEqual(plan["items"][-1]["phase"], "summarize")
        specialist = [item for item in plan["items"] if item.get("binding_mode") == "specialist"][0]
        specialist_spawn = [
            item for item in plan["host_spawn_requests"] if item["dispatch_id"] == specialist["dispatch_id"]
        ][0]
        self.assertIn("dispatch-binding-coordinator-prepare", specialist["dependencies"])
        self.assertEqual(specialist_spawn["agent_type"], "worker")
        self.assertTrue(specialist_spawn["fork_context"])
        self.assertTrue(specialist_spawn["scope_guard_required"])
        self.assertEqual(specialist_spawn["wait_policy"], "progress_output_observation")
        self.assertEqual(specialist_spawn["idle_policy"], "progress_signal_observation_only")
        self.assertTrue(specialist_spawn["no_fixed_total_timeout"])
        self.assertEqual(specialist_spawn["total_timeout_policy"], "none")
        self.assertEqual(specialist_spawn["observation_window_policy"], "poll_only_never_interrupt")
        self.assertEqual(specialist_spawn["checkpoint_schema"], "subagent_artifact.v1")
        self.assertEqual(specialist_spawn["assigned_scope"], ["client/Assets"])
        self.assertIn("binding-client-route", specialist_spawn["binding_id"])
        self.assertIn("Do not edit outside assigned_scope", specialist["prompt"])
        self.assertIn("Host wait windows are observation polls only", specialist["prompt"])
        self.assertIn("do not revert edits made by others", specialist["prompt"])

    def test_every_host_spawn_request_disables_fixed_total_timeout(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())

        plan = subagent_scheduler.build_dispatch_plan(_route_plan(), bindings)

        self.assertGreater(len(plan["host_spawn_requests"]), 0)
        for request in plan["host_spawn_requests"]:
            self.assertTrue(request["no_fixed_total_timeout"])
            self.assertEqual(request["wait_policy"], "progress_output_observation")
            self.assertEqual(request["total_timeout_policy"], "none")
            self.assertEqual(request["observation_window_policy"], "poll_only_never_interrupt")

    def test_required_runtime_marks_dispatch_plan_required_and_autostart(self) -> None:
        route_plan = _route_plan()
        bindings = workspace_subagents.create_bindings(route_plan)
        runtime = {
            "execution_model": "host_subagent_required",
            "autostart": True,
            "dispatch_required": True,
            "required_dispatch_reason": "OpenSpec path requires host SubAgent dispatch.",
        }

        plan = subagent_scheduler.build_dispatch_plan(route_plan, bindings, runtime)

        self.assertEqual(plan["execution_model"], "host_subagent_required")
        self.assertTrue(plan["autostart"])
        self.assertTrue(plan["dispatch_required"])
        self.assertEqual(plan["required_dispatch_reason"], runtime["required_dispatch_reason"])
        self.assertTrue(plan["dispatch_plan_patch"]["dispatch_required"])

    def test_scheduler_loads_standard_route_command_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            route_file = root / "route-output.json"
            route_file.write_text(json.dumps({"ok": True, "route_plan": _route_plan()}), encoding="utf-8")
            args = argparse.Namespace(
                route_file=str(route_file),
                task_file=None,
                task_id=None,
                objective=None,
                working_set=[],
                changed=False,
            )

            route_plan = workspace_subagents.load_or_build_route_plan(root, args)
            bindings = workspace_subagents.create_bindings(route_plan)
            plan = subagent_scheduler.build_dispatch_plan(route_plan, bindings)

        self.assertGreater(len(plan["items"]), 0)

    def test_specialists_depend_on_emitted_coordinator_even_without_route_flag(self) -> None:
        route_plan = _route_plan()
        route_plan.pop("coordinator_required")
        bindings = workspace_subagents.create_bindings(route_plan)

        plan = subagent_scheduler.build_dispatch_plan(route_plan, bindings)

        specialist_dependencies = [
            item["dependencies"]
            for item in plan["items"]
            if item.get("binding_mode") == "specialist"
        ]
        self.assertTrue(specialist_dependencies)
        self.assertTrue(all("dispatch-binding-coordinator-prepare" in item for item in specialist_dependencies))

    def test_main_passes_runtime_decision_into_standalone_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            route_file = root / "route-output.json"
            route_file.write_text(json.dumps({"ok": True, "route_plan": _route_plan(intent="system_change")}), encoding="utf-8")
            original_argv = sys.argv
            try:
                sys.argv = [
                    "subagent_scheduler.py",
                    "--project-root",
                    str(root),
                    "--route-file",
                    str(route_file),
                ]
                original_stdout = sys.stdout
                sys.stdout = _StringWriter()
                try:
                    exit_code = subagent_scheduler.main()
                finally:
                    output = sys.stdout.value
                    sys.stdout = original_stdout
            finally:
                sys.argv = original_argv

        result = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertTrue(result["subagent_runtime"]["review_subagent_required"])
        roles = [item["role"] for item in result["dispatch_plan"]["host_spawn_requests"]]
        self.assertIn("Route Review Specialist", roles)

    def test_scheduler_records_blocker_plan_and_blocks_overlapping_parallel_writes(self) -> None:
        route_plan = _route_plan()
        route_plan["routes"][1]["assigned_scope"] = ["client/Assets/UI"]
        bindings = workspace_subagents.create_bindings(route_plan)

        plan = subagent_scheduler.build_dispatch_plan(route_plan, bindings)

        blocker_plan = plan["subagent_blocker_plan"]
        self.assertEqual(blocker_plan["status"], "serial_required")
        self.assertFalse(blocker_plan["scope_matrix"]["disjoint"])
        self.assertFalse(plan["dispatch_plan_patch"]["can_generate_host_spawn_requests"])
        specialist_requests = [
            item for item in plan["host_spawn_requests"]
            if item.get("scope_guard_required")
        ]
        self.assertEqual(specialist_requests, [])


def _route_plan(intent: str = "small_change") -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "login-contract",
        "route_plan_id": "route-login-contract",
        "mode": "cross_project_contract",
        "coordinator_required": True,
        "verification_plan": [{"project_id": "client-unity"}],
        "routes": [
            {
                "route_id": "client-route",
                "project_id": "client-unity",
                "domain": "game_client",
                "cwd": "client",
                "assigned_scope": ["client/Assets"],
                "rules": ["workspace/base", "game_client/unity"],
                "verification_profile_ids": ["client_quick"],
            },
            {
                "route_id": "server-route",
                "project_id": "server-game",
                "domain": "game_server",
                "cwd": "server",
                "assigned_scope": ["server/api"],
                "rules": ["workspace/base", "game_server/base"],
                "verification_profile_ids": ["server_unit"],
            },
        ],
        "task_type": "contract",
        "risk_level": "high",
        "requirements_gate": {
            "version": 1,
            "task_intent": intent,
            "status": "passed",
            "blocking": False,
            "requirement_sources": ["user_request"],
            "missing": [],
            "open_questions": [],
        },
    }


class _StringWriter:
    def __init__(self) -> None:
        self.value = ""

    def write(self, text: str) -> int:
        self.value += text
        return len(text)

    def flush(self) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
