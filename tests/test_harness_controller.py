from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import harness_controller  # noqa: E402
import task_spec  # noqa: E402


class HarnessControllerTests(unittest.TestCase):
    def test_start_scaffolds_openspec_change_for_implementation_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "openspec" / "upstream" / "openspec" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('{"resolved_version": "1.3.1"}\n', encoding="utf-8")
            task_file = root / "task.json"
            task_file.write_text(
                json.dumps(
                    {
                        "task_id": "fix-review-routing",
                        "objective": "Fix review routing",
                        "acceptance": ["OpenSpec change is bound to the task"],
                        "verification": ["primary"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=_FakeHookRunner(_empty_hook_result())):
                result = harness_controller.start_task(
                    argparse.Namespace(project_root=str(root), task_file=str(task_file), payload_json=None)
                )

            change_dir = root / "openspec" / "changes" / "fix-review-routing"
            spec_payload = json.loads(task_spec.task_spec_path(root, "fix-review-routing").read_text(encoding="utf-8"))
            proposal_exists = (change_dir / "proposal.md").exists()
            design_exists = (change_dir / "design.md").exists()
            tasks_exists = (change_dir / "tasks.md").exists()
            harness_exists = (change_dir / "harness.json").exists()
            spec_exists = any((change_dir / "specs").rglob("spec.md"))

        self.assertTrue(proposal_exists)
        self.assertTrue(design_exists)
        self.assertTrue(tasks_exists)
        self.assertTrue(harness_exists)
        self.assertTrue(spec_exists)
        self.assertEqual(result["task_spec"]["metadata"]["openspec_change_id"], "fix-review-routing")
        self.assertTrue(spec_payload["metadata"]["openspec_dispatch_required"])
        self.assertIn("openspec/changes/fix-review-routing/tasks.md", spec_payload["working_set"])

    def test_start_records_skipped_openspec_scaffold_without_trigger_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "task.json"
            task_file.write_text(
                json.dumps({"task_id": "analyze-task", "objective": "Analyze repository status"}, ensure_ascii=False),
                encoding="utf-8",
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=_FakeHookRunner(_empty_hook_result())):
                result = harness_controller.start_task(
                    argparse.Namespace(project_root=str(root), task_file=str(task_file), payload_json=None)
                )

        metadata = result["task_spec"]["metadata"]
        self.assertEqual(metadata["openspec_change_scaffold"]["reason"], "openspec_upstream_missing")
        self.assertNotIn("openspec_change", metadata)
        self.assertNotIn("openspec_dispatch_required", metadata)

    def test_start_does_not_scaffold_review_only_task_with_change_wording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_upstream_manifest(root)
            task_file = root / "task.json"
            task_file.write_text(
                json.dumps(
                    {
                        "task_id": "review-commit",
                        "objective": "Review the code changes introduced by commit abc1234",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=_FakeHookRunner(_empty_hook_result())):
                result = harness_controller.start_task(
                    argparse.Namespace(project_root=str(root), task_file=str(task_file), payload_json=None)
                )

            change_exists = (root / "openspec" / "changes" / "review-commit").exists()

        metadata = result["task_spec"]["metadata"]
        self.assertFalse(change_exists)
        self.assertEqual(metadata["openspec_change_scaffold"]["reason"], "read_only_task")
        self.assertNotIn("openspec_change", metadata)

    def test_start_scaffolds_generic_change_task_with_review_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_upstream_manifest(root)
            task_file = root / "task.json"
            task_file.write_text(
                json.dumps(
                    {
                        "task_id": "change-review-routing",
                        "objective": "Change review routing",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=_FakeHookRunner(_empty_hook_result())):
                result = harness_controller.start_task(
                    argparse.Namespace(project_root=str(root), task_file=str(task_file), payload_json=None)
                )

            change_exists = (root / "openspec" / "changes" / "change-review-routing").exists()

        metadata = result["task_spec"]["metadata"]
        self.assertTrue(change_exists)
        self.assertEqual(metadata["openspec_change_id"], "change-review-routing")
        self.assertTrue(metadata["openspec_dispatch_required"])

    def test_start_respects_read_only_even_with_existing_openspec_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_upstream_manifest(root)
            task_file = root / "task.json"
            task_file.write_text(
                json.dumps(
                    {
                        "task_id": "audit-change",
                        "objective": "Audit existing OpenSpec change",
                        "working_set": ["openspec/changes/existing-change/tasks.md"],
                        "metadata": {"read_only": True},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=_FakeHookRunner(_empty_hook_result())):
                result = harness_controller.start_task(
                    argparse.Namespace(project_root=str(root), task_file=str(task_file), payload_json=None)
                )

            proposal_exists = (root / "openspec" / "changes" / "existing-change" / "proposal.md").exists()

        metadata = result["task_spec"]["metadata"]
        self.assertFalse(proposal_exists)
        self.assertEqual(metadata["openspec_change_scaffold"]["reason"], "read_only_task")
        self.assertNotIn("openspec_change", metadata)

    def test_start_persists_hook_workspace_routing_metadata_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "task.json"
            task_file.write_text(
                json.dumps(
                    {
                        "task_id": "route-task",
                        "objective": "Implement route-bound change",
                        "acceptance": ["Dispatch plan is visible to the host"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            hook_result = _hook_result()

            with mock.patch.object(harness_controller, "HookRunner", return_value=_FakeHookRunner(hook_result)):
                result = harness_controller.start_task(
                    argparse.Namespace(project_root=str(root), task_file=str(task_file), payload_json=None)
                )

            spec_payload = json.loads(task_spec.task_spec_path(root, "route-task").read_text(encoding="utf-8"))
            route_dir = task_spec.task_dir(root, "route-task")
            workspace_routing_exists = (route_dir / "workspace_routing.json").exists()
            route_plan_exists = (route_dir / "route_plan.json").exists()
            dispatch_plan_exists = (route_dir / "subagent_dispatch_plan.json").exists()

        routing = result["task_spec"]["metadata"]["workspace_routing"]
        self.assertEqual(routing["subagent_runtime"]["execution_model"], "host_subagent_required")
        self.assertEqual(
            spec_payload["metadata"]["workspace_routing"]["subagent_dispatch_plan"]["host_spawn_requests"][0]["dispatch_id"],
            "dispatch-1",
        )
        self.assertTrue(workspace_routing_exists)
        self.assertTrue(route_plan_exists)
        self.assertTrue(dispatch_plan_exists)

    def test_checkpoint_persists_adaptive_hook_workspace_routing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = task_spec.TaskSpec(task_id="route-task", objective="Implement route-bound change")
            spec.save(task_spec.task_spec_path(root, "route-task"))
            harness_controller._write_json(
                task_spec.run_state_path(root, "route-task"),
                {"task_id": "route-task", "artifacts": [], "checklist": {}},
            )
            result_file = root / "result.json"
            result_file.write_text(
                json.dumps({"tool_name": "apply_patch", "touched_paths": ["src/app.py"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=_FakeHookRunner(_hook_result())):
                result = harness_controller.checkpoint_task(
                    argparse.Namespace(project_root=str(root), task_id="route-task", result_file=str(result_file), payload_json=None)
                )

            spec_payload = json.loads(task_spec.task_spec_path(root, "route-task").read_text(encoding="utf-8"))

        self.assertIn("workspace_routing", result["task_spec"]["metadata"])
        self.assertEqual(
            spec_payload["metadata"]["workspace_routing"]["subagent_dispatch_plan"]["host_spawn_requests"][0]["dispatch_id"],
            "dispatch-1",
        )


class _FakeHookRunner:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result

    def run_event(self, _event: str, _payload: dict[str, object] | None = None) -> dict[str, object]:
        return self.result


def _hook_result() -> dict[str, object]:
    return {
        "ok": True,
        "degraded": False,
        "event": "before_task",
        "task_id": "route-task",
        "result": {
            "task_state": {
                "task_id": "route-task",
                "metadata": {
                    "workspace_routing": {
                        "route_plan": {
                            "route_plan_id": "route-route-task",
                            "task_type": "implementation",
                        },
                        "subagent_runtime": {
                            "execution_model": "host_subagent_required",
                            "dispatch_required": True,
                        },
                        "subagent_dispatch_plan": {
                            "dispatch_required": True,
                            "host_spawn_requests": [
                                {
                                    "dispatch_id": "dispatch-1",
                                    "agent_type": "worker",
                                    "message": "Implement assigned scope.",
                                }
                            ],
                        },
                    }
                },
            }
        },
    }


def _empty_hook_result() -> dict[str, object]:
    return {
        "ok": True,
        "degraded": False,
        "event": "before_task",
        "task_id": "fix-review-routing",
        "result": {"task_state": {"task_id": "fix-review-routing", "metadata": {}}},
    }


def _write_upstream_manifest(root: Path) -> None:
    manifest = root / "openspec" / "upstream" / "openspec" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"resolved_version": "1.3.1"}\n', encoding="utf-8")
