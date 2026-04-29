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
        self.assertEqual(plan["items"][0]["phase"], "prepare")
        self.assertEqual(plan["items"][-1]["phase"], "summarize")
        specialist = [item for item in plan["items"] if item.get("binding_mode") == "specialist"][0]
        self.assertIn("dispatch-binding-coordinator-prepare", specialist["dependencies"])
        self.assertIn("Do not edit outside assigned_scope", specialist["prompt"])

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


def _route_plan() -> dict[str, object]:
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
    }


if __name__ == "__main__":
    unittest.main()
