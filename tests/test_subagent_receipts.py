from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import subagent_receipts  # noqa: E402
import workspace_subagents  # noqa: E402


class SubagentReceiptsTests(unittest.TestCase):
    def test_receipts_make_integration_ready_when_all_bindings_complete(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        receipts = [
            _receipt("binding-client-route", ["client/Login.cs"]),
            _receipt("binding-server-route", ["server/login.go"]),
        ]

        result = subagent_receipts.summarize(bindings, receipts)

        self.assertTrue(result["ok"], result["blocking_gaps"])
        self.assertEqual(result["status"], "ready_for_integration")
        self.assertFalse(result["integration_plan"]["auto_merge"])

    def test_receipts_block_missing_failed_and_out_of_scope_results(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        receipts = [
            _receipt("binding-client-route", ["server/login.go"], status="completed"),
            _receipt("binding-server-route", ["server/login.go"], status="failed"),
        ]

        result = subagent_receipts.summarize(bindings, receipts)

        self.assertFalse(result["ok"])
        gap_types = {item["type"] for item in result["blocking_gaps"]}
        self.assertIn("terminal_failure", gap_types)
        self.assertIn("scope_violation", gap_types)


def _route_plan() -> dict[str, object]:
    return {
        "task_id": "login",
        "mode": "multi_project_parallel",
        "coordinator_required": True,
        "routes": [
            {
                "route_id": "client-route",
                "project_id": "client",
                "domain": "web",
                "cwd": "client",
                "assigned_scope": ["client"],
            },
            {
                "route_id": "server-route",
                "project_id": "server",
                "domain": "api",
                "cwd": "server",
                "assigned_scope": ["server"],
            },
        ],
    }


def _receipt(binding_id: str, touched_paths: list[str], *, status: str = "completed") -> dict[str, object]:
    return {"binding_id": binding_id, "status": status, "touched_paths": touched_paths}


if __name__ == "__main__":
    unittest.main()
