from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import hook_runner
import memory_store
import requirements_gate
import workspace_lifecycle
import workspace_router


class RequirementsGateTests(unittest.TestCase):
    def test_allows_quick_bugfix_without_design_doc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "quick-bugfix",
                    "objective": "Fix crash in login UI",
                    "working_set": ["client/Assets/Scripts/UI/LoginPanel.cs"],
                },
                max_depth=1,
            )

        gate = plan["requirements_gate"]
        self.assertEqual(gate["task_intent"], "bugfix")
        self.assertFalse(gate["blocking"])
        self.assertEqual(plan["fallback_action"], "none")

    def test_blocks_feature_story_without_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "new-activity",
                    "objective": "新增限时活动入口",
                    "working_set": ["client/Assets/Scripts/UI/ActivityEntry.cs"],
                },
                max_depth=1,
            )

        gate = plan["requirements_gate"]
        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertTrue(gate["blocking"])
        self.assertEqual(plan["fallback_action"], "ask_user")
        self.assertIn("acceptance_criteria", {item["field"] for item in gate["missing"]})

    def test_passes_system_change_with_design_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "resource-system",
                    "objective": "Refactor resource loading architecture",
                    "working_set": ["client/Assets/Scripts/Resources/Loader.cs", "docs/resource-gdd.md"],
                    "requirement_sources": ["docs/resource-gdd.md"],
                    "acceptance": ["old bundles load successfully", "failed downloads show retry UI"],
                    "architecture": ["Loader exposes an interface and keeps platform adapters isolated."],
                },
                max_depth=1,
            )

        gate = plan["requirements_gate"]
        self.assertEqual(gate["task_intent"], "system_change")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])

    def test_openspec_change_path_counts_as_contract_evidence(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Implement OpenSpec change contract"},
            {
                "text": "implement openspec change contract",
                "paths": ["openspec/changes/require-subagent-dispatch/tasks.md"],
                "cwd": "",
            },
            mode="single_project",
            task_type="contract",
            risk_level="medium",
            domains=["workspace_meta"],
        )

        self.assertEqual(gate["task_intent"], "system_change")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])
        self.assertIn("openspec/changes/require-subagent-dispatch/tasks.md", gate["requirement_sources"])

    def test_routing_review_reports_blocking_requirements_gate(self) -> None:
        review = workspace_lifecycle.routing_review(
            {
                "metadata": {
                    "workspace_routing": {
                        "route_plan": {
                            "mode": "single_project",
                            "requirements_gate": {
                                "blocking": True,
                                "open_questions": ["本任务完成后按哪些验收条件判断通过？"],
                                "missing": [{"field": "acceptance_criteria", "reason": "缺少可验证的验收条件"}],
                            },
                        }
                    }
                }
            }
        )

        self.assertFalse(review["ok"])
        self.assertEqual(review["gaps"][0]["type"], "requirements_gate")
        self.assertTrue(review["gaps"][0]["blocking"])

    def test_routing_review_reports_blocking_adaptive_requirements_gate(self) -> None:
        review = workspace_lifecycle.routing_review(
            {
                "metadata": {
                    "workspace_routing": {
                        "route_plan": {"mode": "single_project"},
                        "adaptive_route_plan": {
                            "requirements_gate": {
                                "blocking": True,
                                "open_questions": ["补充发布回滚条件？"],
                                "missing": [{"field": "rollback_plan", "reason": "缺少回滚方案"}],
                            }
                        },
                    }
                }
            }
        )

        self.assertFalse(review["ok"])
        self.assertEqual(review["gaps"][0]["type"], "adaptive_requirements_gate")
        self.assertTrue(review["gaps"][0]["blocking"])

    def test_explicit_unknown_intent_normalizes_to_schema_safe_value(self) -> None:
        gate = requirements_gate.evaluate(
            {"task_intent": "production_support"},
            {"text": "", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="implementation",
            risk_level="medium",
            domains=["workspace_meta"],
        )

        self.assertEqual(gate["task_intent"], "tech_task")
        self.assertEqual(gate["status"], "passed")

    def test_feature_keyword_requires_word_boundary(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Address config drift"},
            {"text": "address config drift", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="implementation",
            risk_level="medium",
            domains=["workspace_meta"],
        )

        self.assertEqual(gate["task_intent"], "tech_task")
        self.assertFalse(gate["blocking"])

    def test_acceptance_does_not_count_as_requirement_source(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Add tournament mode", "acceptance": ["matchmaking screen opens"]},
            {"text": "add tournament mode", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="implementation",
            risk_level="medium",
            domains=["game_client"],
        )

        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertTrue(gate["blocking"])
        self.assertIn("requirement_sources", {item["field"] for item in gate["missing"]})
        self.assertNotIn("acceptance_criteria", gate["requirement_sources"])

    def test_tech_keywords_win_over_feature_verbs(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Add tests for routing"},
            {"text": "add tests for routing", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="implementation",
            risk_level="medium",
            domains=["workspace_meta"],
        )

        self.assertEqual(gate["task_intent"], "tech_task")
        self.assertFalse(gate["blocking"])

    def test_docs_only_wins_over_release_signals(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Update release notes"},
            {"text": "update release notes", "paths": ["docs/release.md"], "cwd": ""},
            mode="single_project",
            task_type="release",
            risk_level="release_blocking",
            domains=["design_docs"],
        )

        self.assertEqual(gate["task_intent"], "docs_only")
        self.assertFalse(gate["blocking"])

    def test_bare_hot_update_text_routes_to_release_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "hot-update",
                    "objective": "准备热更",
                    "working_set": ["client/Assets/Scripts/LoginPanel.cs"],
                },
                max_depth=1,
            )

        gate = plan["requirements_gate"]
        self.assertEqual(plan["task_type"], "release")
        self.assertEqual(gate["task_intent"], "release_gate")
        self.assertTrue(gate["blocking"])
        self.assertIn("rollback_plan", {item["field"] for item in gate["missing"]})

    def test_bare_english_hot_update_text_routes_to_release_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "hot-update-en",
                    "objective": "Prepare hot update",
                    "working_set": ["client/Assets/Scripts/LoginPanel.cs"],
                },
                max_depth=1,
            )

        gate = plan["requirements_gate"]
        self.assertEqual(plan["task_type"], "release")
        self.assertEqual(gate["task_intent"], "release_gate")
        self.assertTrue(gate["blocking"])

    def test_sufficient_detail_uses_word_boundary_for_english_conditions(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Add gift mode", "acceptance": ["gift view opens"]},
            {"text": "add gift mode", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="implementation",
            risk_level="medium",
            domains=["game_client"],
        )

        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertTrue(gate["blocking"])
        self.assertIn("requirement_sources", {item["field"] for item in gate["missing"]})
        self.assertNotIn("user_request", gate["requirement_sources"])

    def test_release_signal_wins_over_low_risk_keywords(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Test release build"},
            {"text": "test release build", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="release",
            risk_level="release_blocking",
            domains=["game_client"],
        )

        self.assertEqual(gate["task_intent"], "release_gate")
        self.assertTrue(gate["blocking"])
        self.assertIn("rollback_plan", {item["field"] for item in gate["missing"]})

    def test_contract_signal_wins_over_bugfix_keywords(self) -> None:
        gate = requirements_gate.evaluate(
            {
                "objective": "Fix login protocol",
                "requirement_sources": ["issue-123"],
                "acceptance": ["client and server tests pass"],
            },
            {"text": "fix login protocol", "paths": [], "cwd": ""},
            mode="cross_project_contract",
            task_type="contract",
            risk_level="high",
            domains=["game_client", "game_server"],
        )

        self.assertEqual(gate["task_intent"], "system_change")
        self.assertIn("architecture", {item["field"] for item in gate["missing"]})

    def test_detailed_user_request_counts_when_objective_is_short(self) -> None:
        gate = requirements_gate.evaluate(
            {
                "objective": "Add gift mode",
                "user_request": "When the player opens gifts, show the reward list and claim button.",
                "acceptance": ["gift reward list opens"],
            },
            {"text": "add gift mode", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="implementation",
            risk_level="medium",
            domains=["game_client"],
        )

        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertFalse(gate["blocking"])
        self.assertIn("user_request", gate["requirement_sources"])

    def test_lifecycle_metadata_fields_feed_requirements_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_scope = _set_env("CODEX_MEMORY_SCOPE", "project")
            old_cwd = _set_env("CODEX_MEMORY_CWD", str(root))
            try:
                root.joinpath(".codex").mkdir()
                _unity_project(root / "client")

                routing = workspace_lifecycle.safe_workspace_routing(
                    "metadata-feature",
                    {
                        "objective": "Add tutorial mode",
                        "working_set": ["client/Assets/Scripts/TutorialPanel.cs"],
                        "metadata": {
                            "requirement_sources": ["issue-42"],
                            "acceptance": ["tutorial panel opens from the lobby"],
                        },
                    },
                )
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

        gate = routing["route_plan"]["requirements_gate"]
        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])

    def test_hook_before_task_top_level_fields_feed_requirements_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_scope = _set_env("CODEX_MEMORY_SCOPE", "project")
            old_cwd = _set_env("CODEX_MEMORY_CWD", str(root))
            try:
                root.joinpath(".codex").mkdir()
                _unity_project(root / "client")
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "top-level-feature",
                        "objective": "Add tutorial mode",
                        "working_set": ["client/Assets/Scripts/TutorialPanel.cs"],
                        "requirement_sources": ["issue-42"],
                        "acceptance": ["tutorial panel opens from the lobby"],
                    },
                )
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

        gate = result["result"]["task_state"]["metadata"]["workspace_routing"]["route_plan"]["requirements_gate"]
        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])

    def test_hook_preserves_top_level_requirement_fields_for_adaptive_reroute(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_scope = _set_env("CODEX_MEMORY_SCOPE", "project")
            old_cwd = _set_env("CODEX_MEMORY_CWD", str(root))
            try:
                root.joinpath(".codex").mkdir()
                _unity_project(root / "client")
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "adaptive-feature",
                        "objective": "Add tutorial mode",
                        "working_set": ["client/Assets/Scripts/TutorialPanel.cs"],
                        "requirement_sources": ["issue-42"],
                        "acceptance": ["tutorial panel opens from the lobby"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "adaptive-feature",
                        "tool_name": "edit",
                        "touched_paths": ["client/Assets/Scripts/TutorialPanel.cs"],
                    },
                )
            finally:
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_MEMORY_CWD", old_cwd)

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        gate = routing["adaptive_route_plan"]["requirements_gate"]
        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])

    def test_code_task_that_mentions_design_doc_is_not_docs_only(self) -> None:
        gate = requirements_gate.evaluate(
            {"objective": "Add tutorial from design doc"},
            {"text": "add tutorial from design doc", "paths": [], "cwd": ""},
            mode="single_project",
            task_type="docs",
            risk_level="medium",
            domains=["game_client"],
        )

        self.assertEqual(gate["task_intent"], "feature_story")
        self.assertTrue(gate["blocking"])
        self.assertIn("acceptance_criteria", {item["field"] for item in gate["missing"]})

    def test_tooling_governance_adapter_task_is_not_feature_story(self) -> None:
        gate = requirements_gate.evaluate(
            {
                "objective": (
                    "完成 T86：核对 OpenSpec/BMAD 上游核心代码复用边界并落地复用决策文档，"
                    "不复制第三方代码、不实现 runtime。"
                )
            },
            {
                "text": "完成 T86 核对 upstream adapter 复用边界 不实现 runtime",
                "paths": ["openspec/changes/integrate-openspec-bmad-governance/upstream-reuse-decision.md"],
                "cwd": "",
            },
            mode="multi_project_parallel",
            task_type="docs",
            risk_level="medium",
            domains=["workspace_meta", "design_docs"],
        )

        self.assertEqual(gate["task_intent"], "tech_task")
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["blocking"])
        for text in ("add task-list entry for upstream adapter decision docs", "add runtime guide", "add adapter README", "add runtime release notes", "implement governance docs", "新增工具治理文档", "实现治理文档"):
            gate = requirements_gate.evaluate(
                {"objective": text},
                {"text": text, "paths": [], "cwd": ""},
                mode="multi_project_parallel",
                task_type="docs",
                risk_level="medium",
                domains=["workspace_meta", "design_docs"],
            )
            self.assertEqual(gate["task_intent"], "tech_task")
            self.assertFalse(gate["blocking"])

    def test_runtime_adapter_implementation_still_requires_requirements(self) -> None:
        cases = (
            ("implement runtime adapter", "implementation", "feature_story"),
            ("implement runtime adapter according to design docs", "docs", "feature_story"),
            ("implement runtime adapter using design docs", "docs", "feature_story"),
            ("implement runtime adapter with design docs", "docs", "feature_story"),
            ("根据设计文档实现 runtime adapter", "docs", "feature_story"),
            ("add runtime adapter according to design docs", "docs", "feature_story"),
            ("refactor runtime adapter design docs", "general", "system_change"),
            ("接入 upstream adapter 设计", "general", "system_change"),
        )
        for text, task_type, expected_intent in cases:
            with self.subTest(text=text):
                gate = requirements_gate.evaluate(
                    {"objective": text},
                    {"text": text, "paths": [], "cwd": ""},
                    mode="single_project",
                    task_type=task_type,
                    risk_level="medium",
                    domains=["design_docs"] if task_type == "docs" else ["workspace_meta"],
                )
                self.assertEqual(gate["task_intent"], expected_intent)
                self.assertEqual(gate["status"], "needs_clarification")
                self.assertTrue(gate["blocking"])


def _unity_project(path: Path) -> None:
    path.joinpath("Assets").mkdir(parents=True, exist_ok=True)
    path.joinpath("ProjectSettings").mkdir(parents=True, exist_ok=True)
    _write_json(path / "Packages" / "manifest.json", {})


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _set_env(name: str, value: str) -> str | None:
    old_value = __import__("os").environ.get(name)
    __import__("os").environ[name] = value
    return old_value


def _restore_env(name: str, value: str | None) -> None:
    env = __import__("os").environ
    if value is None:
        env.pop(name, None)
    else:
        env[name] = value


if __name__ == "__main__":
    unittest.main()
