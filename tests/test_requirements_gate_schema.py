from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import requirements_gate  # noqa: E402
import requirements_gate_schema  # noqa: E402
import workspace_lifecycle  # noqa: E402


class RequirementsGateSchemaTests(unittest.TestCase):
    def test_passed_result_contains_strict_report_fields(self) -> None:
        gate = _evaluate(
            {
                "objective": "Add gift mode",
                "user_request": "When the player opens gifts, show the reward list and claim button.",
                "acceptance": ["gift reward list opens"],
                "non_goals": ["do not change payment flows"],
                "technical_decision_basis": ["use existing reward UI module"],
                "platform_constraint_gaps": ["confirm WebGL memory budget"],
                "asset_bundle_constraints": ["business prefab may depend on module AB plus one shared AB"],
            },
            text="add gift mode",
        )

        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])
        self.assertFalse(_required_schema_keys() - set(gate))
        self.assertEqual(gate["missing_requirements"], gate["missing"])
        self.assertEqual(gate["non_goals"], ["do not change payment flows"])
        self.assertEqual(gate["technical_decision_basis"], ["use existing reward UI module"])
        self.assertEqual(gate["platform_constraint_gaps"], ["confirm WebGL memory budget"])
        self.assertEqual(gate["asset_bundle_constraints"], ["business prefab may depend on module AB plus one shared AB"])
        self.assertTrue(gate["recommended_next_step"])

    def test_missing_requirements_use_blocking_clarification_schema(self) -> None:
        gate = _evaluate({"objective": "Add tournament mode"}, text="add tournament mode")

        self.assertEqual(gate["status"], "needs_clarification")
        self.assertTrue(gate["blocking"])
        self.assertEqual(gate["missing_requirements"], gate["missing"])
        self.assertIn("acceptance_criteria", {item["field"] for item in gate["missing"]})
        self.assertTrue(gate["acceptance_gaps"])
        self.assertTrue(gate["scope_gaps"])
        self.assertTrue(gate["open_questions"])

    def test_needs_bmad_upstream_status_is_strict_and_blocking(self) -> None:
        gate = _evaluate(
            {
                "task_intent": "tech_task",
                "requirements_gate_status": "needs_bmad_upstream",
                "scope_gaps": ["request spans product, architecture, and multiple implementation slices"],
            },
            text="plan a broad workflow",
            domains=["workspace_meta"],
        )

        self.assertEqual(gate["status"], "needs_bmad_upstream")
        self.assertTrue(gate["blocking"])
        self.assertEqual(
            gate["recommended_next_step"],
            "Produce BMAD-style upstream planning artifacts before implementation.",
        )
        self.assertTrue(gate["scope_gaps"])
        self.assertTrue(gate["open_questions"])

    def test_blocked_by_conflict_status_is_strict_and_blocking(self) -> None:
        gate = _evaluate(
            {
                "task_intent": "tech_task",
                "requirements_gate_status": "blocked_by_conflict",
                "logical_conflicts": ["request assumes auto-execution, but the current runtime only emits dispatch plans"],
            },
            text="implement bmad runtime",
            domains=["workspace_meta"],
        )

        self.assertEqual(gate["status"], "blocked_by_conflict")
        self.assertTrue(gate["blocking"])
        self.assertEqual(
            gate["logical_conflicts"],
            ["request assumes auto-execution, but the current runtime only emits dispatch plans"],
        )
        self.assertTrue(gate["open_questions"])

    def test_explicit_passed_status_cannot_bypass_missing_requirements(self) -> None:
        gate = _evaluate(
            {"objective": "Add tournament mode", "requirements_gate_status": "passed"},
            text="add tournament mode",
        )

        self.assertEqual(gate["status"], "needs_clarification")
        self.assertTrue(gate["blocking"])
        self.assertIn("acceptance_criteria", {item["field"] for item in gate["missing"]})

    def test_json_schema_accepts_all_runtime_statuses(self) -> None:
        schema_statuses = set(_gate_schema()["properties"]["status"]["enum"])
        self.assertTrue(set(requirements_gate_schema.VALID_GATE_STATUSES).issubset(schema_statuses))

    def test_json_schema_enforces_blocking_status_invariant(self) -> None:
        rules = _gate_schema()["oneOf"]
        non_blocking_rule = next(rule for rule in rules if rule["properties"]["blocking"].get("const") is False)
        blocking_rule = next(rule for rule in rules if rule["properties"]["blocking"].get("const") is True)

        self.assertEqual(set(non_blocking_rule["properties"]["status"]["enum"]), {"passed", "warning"})
        self.assertEqual(
            set(blocking_rule["properties"]["status"]["enum"]),
            {"needs_clarification", "needs_bmad_upstream", "blocked_by_conflict"},
        )
        for rule in rules:
            self.assertEqual(set(rule["required"]), {"status", "blocking"})

    def test_conflict_evidence_derives_blocked_by_conflict_without_requested_status(self) -> None:
        gate = _evaluate(
            {
                "task_intent": "tech_task",
                "logical_conflicts": ["requested behavior conflicts with the baseline change-governance spec"],
            },
            text="review conflicting requirement",
            domains=["workspace_meta"],
        )

        self.assertEqual(gate["status"], "blocked_by_conflict")
        self.assertTrue(gate["blocking"])
        self.assertEqual(
            gate["logical_conflicts"],
            ["requested behavior conflicts with the baseline change-governance spec"],
        )

    def test_lifecycle_preserves_top_level_requested_gate_status(self) -> None:
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        os.environ["CODEX_MEMORY_CWD"] = str(PROJECT_ROOT)
        try:
            routing = workspace_lifecycle.safe_workspace_routing(
                "lifecycle-bmad-status",
                {
                    "objective": "Plan broad workflow readiness",
                    "working_set": ["docs/plan.md"],
                    "task_intent": "tech_task",
                    "requirements_gate_status": "needs_bmad_upstream",
                },
            )
        finally:
            if old_cwd is None:
                os.environ.pop("CODEX_MEMORY_CWD", None)
            else:
                os.environ["CODEX_MEMORY_CWD"] = old_cwd

        gate = routing["route_plan"]["requirements_gate"]
        self.assertEqual(gate["status"], "needs_bmad_upstream")
        self.assertTrue(gate["blocking"])


def _evaluate(
    task: dict[str, object],
    *,
    text: str,
    domains: list[str] | None = None,
) -> dict[str, object]:
    return requirements_gate.evaluate(
        task,
        {"text": text, "paths": [], "cwd": ""},
        mode="single_project",
        task_type="implementation",
        risk_level="medium",
        domains=domains or ["game_client"],
    )


def _required_schema_keys() -> set[str]:
    return set(_gate_schema()["required"])


def _gate_schema() -> dict[str, object]:
    schema_path = PROJECT_ROOT / "schemas" / "workspace_route_plan.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return schema["$defs"]["requirements_gate"]


if __name__ == "__main__":
    unittest.main()
