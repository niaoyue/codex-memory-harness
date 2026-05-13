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

import governance_adapter  # noqa: E402
import task_spec  # noqa: E402


class GovernanceAdapterTests(unittest.TestCase):
    def test_prepare_maps_openspec_contract_and_harness_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root, "change-a")
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))

            bundle = governance_adapter.prepare(root, task_id="task-a", change_id="change-a")

        statuses = {(item["kind"], item["status"]) for item in bundle["evidence"]}
        self.assertIn(("openspec_contract", "passed"), statuses)
        self.assertIn(("harness_task", "passed"), statuses)

    def test_collect_requires_passed_verification_and_clean_commit_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root, "change-a")
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))
            _write_json(root / ".codex" / "harness" / "tasks" / "task-a" / "verification.json", {
                "overall_status": "passed",
                "release_gates": {
                    "webgl_minigame_compatible": {"status": "passed", "summary": "ok"}
                },
            })
            _write_jsonl(root / ".codex" / "harness" / "review" / "review-ledger.jsonl", [
                {
                    "status": "clean",
                    "commit_ref": "abc1234",
                    "diff_fingerprint": {"fingerprint": "fp"},
                }
            ])

            bundle = governance_adapter.collect(
                root,
                task_id="task-a",
                change_id="change-a",
                commit_ref="abc1234",
                verification_artifact=".codex/harness/tasks/task-a/verification.json",
                review_result=".codex/harness/review/review-ledger.jsonl",
            )
            archived = governance_adapter.sync_archive(root, bundle, archive=True)
            archive_path_exists = Path(archived["archive_evidence_path"]).exists()

        self.assertTrue(bundle["safe_to_archive"])
        self.assertEqual(bundle["overall_status"], "passed")
        self.assertTrue(archive_path_exists)

    def test_collect_blocks_when_review_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root, "change-a")
            _write_json(root / "verification.json", {"overall_status": "passed"})

            bundle = governance_adapter.collect(
                root,
                task_id="task-a",
                change_id="change-a",
                verification_artifact="verification.json",
                review_result="missing.jsonl",
            )

        self.assertFalse(bundle["safe_to_archive"])
        self.assertTrue(bundle["blocking_gaps"])


def _write_openspec_change(root: Path, change_id: str) -> None:
    change = root / "openspec" / "changes" / change_id
    change.mkdir(parents=True)
    for name in ("proposal.md", "design.md", "tasks.md"):
        (change / name).write_text(f"# {name}\n", encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in entries) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
