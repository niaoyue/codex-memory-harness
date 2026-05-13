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
            _receipt("binding-client-route", ["client/Login.cs"], status="ready"),
            _receipt("binding-server-route", ["server/login.go"]),
        ]

        result = subagent_receipts.summarize(bindings, receipts)

        self.assertTrue(result["ok"], result["blocking_gaps"])
        self.assertEqual(result["status"], "ready_for_integration")
        integration_plan = result["integration_plan"]
        self.assertFalse(integration_plan["auto_merge"])
        self.assertTrue(integration_plan["merge_preflight_required"])
        self.assertTrue(integration_plan["integration_worktree_required"])
        self.assertEqual(
            [item["binding_id"] for item in integration_plan["candidate_branches"]],
            ["binding-client-route", "binding-server-route"],
        )
        self.assertEqual(integration_plan["candidate_branches"][0]["branch"], "codex/binding-client-route")

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

    def test_successful_receipts_missing_candidate_metadata_stay_blocked(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        receipts = [
            _receipt("binding-client-route", ["client/Login.cs"], candidate_metadata=False),
            _receipt("binding-server-route", ["server/login.go"]),
        ]

        result = subagent_receipts.summarize(bindings, receipts)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "blocked")
        metadata_gaps = [item for item in result["blocking_gaps"] if item["type"] == "receipt_metadata"]
        self.assertEqual(len(metadata_gaps), 1)
        self.assertEqual(metadata_gaps[0]["binding_id"], "binding-client-route")
        self.assertEqual(
            set(metadata_gaps[0]["missing_fields"]),
            {"branch", "effective_cwd", "base_head", "head", "candidate_commit"},
        )


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


def _receipt(
    binding_id: str,
    touched_paths: list[str],
    *,
    status: str = "completed",
    candidate_metadata: bool = True,
) -> dict[str, object]:
    receipt: dict[str, object] = {"binding_id": binding_id, "status": status, "touched_paths": touched_paths}
    if candidate_metadata:
        receipt.update(
            {
                "branch": f"codex/{binding_id}",
                "effective_cwd": f"/worktrees/{binding_id}",
                "base_head": "a" * 40,
                "head": "b" * 40,
                "candidate_commit": "c" * 40,
            }
        )
    return receipt


if __name__ == "__main__":
    unittest.main()
