from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import requirements_gate  # noqa: E402
import workspace_artifact_filters  # noqa: E402
import workspace_router  # noqa: E402


class RequirementsGateReviewRegressionTests(unittest.TestCase):
    def test_runtime_adapter_implementation_keeps_intent_with_non_goal(self) -> None:
        cases = (
            "implement runtime adapter according to design docs; do not implement UI yet",
            "根据设计文档实现 runtime adapter，不实现 UI",
            "do not implement UI but implement runtime adapter",
            "do not implement UI and implement runtime adapter",
            "do not implement runtime docs but implement runtime adapter",
            "不实现 UI 但实现 runtime adapter",
            "不实现 UI 并实现 runtime adapter",
            "implement runtime adapter and update docs",
            "implement runtime adapter and update docs guide",
            "implement runtime adapter and update README",
            "implement runtime adapter and update runbook",
            "implement runtime adapter and adapter docs",
            "implement runtime adapter per proposal",
        )
        for text in cases:
            with self.subTest(text=text):
                gate = requirements_gate.evaluate(
                    {"objective": text},
                    {"text": text, "paths": [], "cwd": ""},
                    mode="single_project",
                    task_type="docs",
                    risk_level="medium",
                    domains=["design_docs"],
                )
                self.assertEqual(gate["task_intent"], "feature_story")
                self.assertEqual(gate["status"], "needs_clarification")
                self.assertTrue(gate["blocking"])

    def test_generic_adapter_docs_with_non_goal_stay_docs_only(self) -> None:
        cases = (
            "add runtime adapter docs; do not implement runtime",
            "新增 runtime adapter 文档，不实现 runtime",
            "核对 upstream adapter 复用边界，不要实现 runtime",
            "check upstream adapter reuse boundary; don't implement runtime",
        )
        for text in cases:
            with self.subTest(text=text):
                gate = requirements_gate.evaluate(
                    {"objective": text},
                    {"text": text, "paths": [], "cwd": ""},
                    mode="single_project",
                    task_type="docs",
                    risk_level="medium",
                    domains=["design_docs"],
                )
                self.assertEqual(gate["task_intent"], "docs_only")
                self.assertEqual(gate["status"], "passed")
                self.assertFalse(gate["blocking"])

    def test_doc_source_references_do_not_bypass_runtime_implementation_gate(self) -> None:
        cases = (
            "implement runtime adapter using README",
            "implement runtime adapter according to README",
            "implement runtime adapter from guide",
            "implement runtime adapter per runbook",
            "implement runtime adapter using governance docs",
        )
        for text in cases:
            with self.subTest(text=text):
                gate = requirements_gate.evaluate(
                    {"objective": text},
                    {"text": text, "paths": [], "cwd": ""},
                    mode="single_project",
                    task_type="docs",
                    risk_level="medium",
                    domains=["design_docs"],
                )
                self.assertEqual(gate["task_intent"], "feature_story")
                self.assertEqual(gate["status"], "needs_clarification")
                self.assertTrue(gate["blocking"])

    def test_adapter_docs_can_cite_design_docs_without_becoming_implementation(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "add runtime adapter docs with design docs"},
            {"text": "add runtime adapter docs with design docs", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="docs",
            risk_level="medium",
            domains=["design_docs"],
        )

        self.assertEqual(gate["task_intent"], "docs_only")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])

    def test_design_docs_spec_scope_survives_inferred_implementation_type(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "add change governance spec"},
            {"text": "add change governance spec", "paths": ["docs/spec.md"], "cwd": ""},
            mode="single_project",
            task_type="implementation",
            risk_level="medium",
            domains=["design_docs"],
        )

        self.assertEqual(gate["task_intent"], "docs_only")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])

    def test_route_plan_keeps_mixed_implementation_and_docs_blocking(self) -> None:
        plan = workspace_router.build_route_plan(
            PROJECT_ROOT,
            {
                "task_id": "mixed-implementation-docs",
                "objective": "implement runtime adapter and update docs",
                "working_set": ["plugins/codex-memory/scripts/new_adapter.py", "docs/guide.md"],
            },
        )

        gate = plan["requirements_gate"]
        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertEqual(gate["status"], "needs_clarification")
        self.assertTrue(gate["blocking"])

    def test_route_plan_blocks_mixed_adapter_implementation_and_docs(self) -> None:
        plan = workspace_router.build_route_plan(
            PROJECT_ROOT,
            {
                "task_id": "mixed-adapter-docs",
                "objective": "implement runtime adapter and adapter docs",
                "working_set": ["plugins/codex-memory/scripts/new_adapter.py", "docs/guide.md"],
            },
        )

        gate = plan["requirements_gate"]
        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertEqual(gate["status"], "needs_clarification")
        self.assertTrue(gate["blocking"])

    def test_route_plan_blocks_spec_named_adapter_implementation(self) -> None:
        plan = workspace_router.build_route_plan(
            PROJECT_ROOT,
            {
                "task_id": "spec-parser-adapter",
                "objective": "add spec parser runtime adapter",
                "working_set": ["plugins/codex-memory/scripts/spec_parser_adapter.py"],
            },
        )

        gate = plan["requirements_gate"]
        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertEqual(gate["status"], "needs_clarification")
        self.assertTrue(gate["blocking"])

    def test_route_plan_blocks_docs_parser_adapter_implementation(self) -> None:
        cases = (
            ("docs-parser-adapter", "implement docs parser adapter", "plugins/codex-memory/scripts/docs_parser_adapter.py"),
            ("docs-generator-adapter", "add documentation generator runtime adapter", "plugins/codex-memory/scripts/docs_generator_adapter.py"),
            ("runtime-docs-adapter", "implement runtime docs adapter", "plugins/codex-memory/scripts/runtime_docs_adapter.py"),
            ("governance-docs-adapter", "implement governance docs adapter", "plugins/codex-memory/scripts/governance_docs_adapter.py"),
        )
        for task_id, objective, path in cases:
            with self.subTest(objective=objective):
                plan = workspace_router.build_route_plan(
                    PROJECT_ROOT,
                    {
                        "task_id": task_id,
                        "objective": objective,
                        "working_set": [path],
                    },
                )

                gate = plan["requirements_gate"]
                self.assertEqual(gate["task_intent"], "feature_story")
                self.assertEqual(gate["status"], "needs_clarification")
                self.assertTrue(gate["blocking"])

    def test_route_plan_keeps_design_docs_spec_non_blocking(self) -> None:
        plan = workspace_router.build_route_plan(
            PROJECT_ROOT,
            {
                "task_id": "design-docs-spec",
                "objective": "add change governance spec",
                "working_set": ["docs/spec.md"],
            },
        )

        gate = plan["requirements_gate"]
        self.assertEqual(gate["task_intent"], "docs_only")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])

    def test_route_plan_keeps_openspec_specs_non_blocking(self) -> None:
        cases = (
            "add change governance spec",
            "implement change governance spec",
            "实现治理 spec",
        )
        for objective in cases:
            with self.subTest(objective=objective):
                plan = workspace_router.build_route_plan(
                    PROJECT_ROOT,
                    {
                        "task_id": "openspec-spec",
                        "objective": objective,
                        "working_set": ["openspec/specs/change-governance/spec.md"],
                    },
                )

                gate = plan["requirements_gate"]
                self.assertEqual(gate["task_intent"], "tech_task")
                self.assertEqual(gate["status"], "passed")
                self.assertFalse(gate["blocking"])

    def test_tool_alias_marks_verification_artifact(self) -> None:
        cases = (
            ("tool", {"tool": "verification_runner", "touched_paths": ["scripts/build_release.py"]}),
            ("workspace_verifier", {"tool_name": "workspace_verifier", "touched_paths": ["scripts/build_release.py"]}),
            ("tool", {"phase": "workspace_verification", "touched_paths": ["scripts/build_release.py"]}),
        )
        for tool_name, payload in cases:
            with self.subTest(tool_name=tool_name, payload=payload):
                self.assertTrue(workspace_artifact_filters.is_verification_artifact(tool_name, payload))
                self.assertEqual(workspace_artifact_filters.routing_touched_paths(tool_name, payload, payload["touched_paths"]), [])
                self.assertEqual(
                    workspace_artifact_filters.routing_excluded_paths(tool_name, payload, payload["touched_paths"]),
                    ["scripts/build_release.py"],
                )


if __name__ == "__main__":
    unittest.main()
