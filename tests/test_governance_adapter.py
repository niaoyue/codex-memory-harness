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
            _write_openspec_upstream(root)
            _write_openspec_change(root, "change-a")
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))

            bundle = governance_adapter.prepare(root, task_id="task-a", change_id="change-a")

        statuses = {(item["kind"], item["status"]) for item in bundle["evidence"]}
        self.assertIn(("openspec_contract", "passed"), statuses)
        self.assertIn(("openspec_upstream", "passed"), statuses)
        self.assertIn(("harness_binding", "passed"), statuses)
        self.assertIn(("harness_task", "passed"), statuses)

    def test_collect_requires_passed_verification_and_clean_commit_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_upstream(root)
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
            _write_openspec_upstream(root)
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

    def test_collect_blocks_clean_review_for_different_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_upstream(root)
            _write_openspec_change(root, "change-a")
            _write_json(root / "verification.json", {"overall_status": "passed"})
            _write_jsonl(root / "review.jsonl", [{"status": "clean", "commit_ref": "def5678"}])

            bundle = governance_adapter.collect(
                root,
                task_id="task-a",
                change_id="change-a",
                commit_ref="abc1234",
                verification_artifact="verification.json",
                review_result="review.jsonl",
            )

        self.assertFalse(bundle["safe_to_archive"])
        self.assertIn(("xhigh_review", "mismatch"), {(item["kind"], item["status"]) for item in bundle["evidence"]})

    def test_collect_blocks_clean_review_without_commit_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_upstream(root)
            _write_openspec_change(root, "change-a")
            _write_json(root / "verification.json", {"overall_status": "passed"})
            _write_jsonl(root / "review.jsonl", [{"status": "clean"}])

            bundle = governance_adapter.collect(
                root,
                task_id="task-a",
                change_id="change-a",
                commit_ref="abc1234",
                verification_artifact="verification.json",
                review_result="review.jsonl",
            )

        self.assertFalse(bundle["safe_to_archive"])
        self.assertIn(("xhigh_review", "invalid"), {(item["kind"], item["status"]) for item in bundle["evidence"]})

    def test_collect_blocks_clean_review_without_requested_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_upstream(root)
            _write_openspec_change(root, "change-a")
            _write_json(root / "verification.json", {"overall_status": "passed"})
            _write_jsonl(root / "review.jsonl", [{"status": "clean"}])

            bundle = governance_adapter.collect(
                root,
                task_id="task-a",
                change_id="change-a",
                verification_artifact="verification.json",
                review_result="review.jsonl",
            )

        self.assertFalse(bundle["safe_to_archive"])
        self.assertIn(("xhigh_review", "invalid"), {(item["kind"], item["status"]) for item in bundle["evidence"]})

    def test_prepare_requires_harness_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_upstream(root)
            _write_openspec_change(root, "change-a", with_harness=False)
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))

            bundle = governance_adapter.prepare(root, task_id="task-a", change_id="change-a")

        statuses = {(item["kind"], item["status"]) for item in bundle["evidence"]}
        self.assertIn(("harness_binding", "missing"), statuses)
        self.assertFalse(bundle["safe_to_archive"])

    def test_prepare_rejects_change_without_spec_md_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_upstream(root)
            _write_openspec_change(root, "change-a")
            spec_path = root / "openspec" / "changes" / "change-a" / "specs" / "capability-a" / "spec.md"
            spec_path.unlink()
            (spec_path.parent / "README.md").write_text("# not a delta spec\n", encoding="utf-8")
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))

            bundle = governance_adapter.prepare(root, task_id="task-a", change_id="change-a")

        statuses = {(item["kind"], item["status"]) for item in bundle["evidence"]}
        self.assertIn(("openspec_contract", "missing"), statuses)
        self.assertFalse(bundle["safe_to_archive"])

    def test_prepare_rejects_harness_binding_for_different_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_upstream(root)
            _write_openspec_change(root, "change-a")
            harness_path = root / "openspec" / "changes" / "change-a" / "harness.json"
            payload = json.loads(harness_path.read_text(encoding="utf-8"))
            payload["harness_task_id"] = "other-task"
            _write_json(harness_path, payload)
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))

            bundle = governance_adapter.prepare(root, task_id="task-a", change_id="change-a")

        statuses = {(item["kind"], item["status"]) for item in bundle["evidence"]}
        self.assertIn(("harness_binding", "invalid"), statuses)
        self.assertFalse(bundle["safe_to_archive"])

    def test_prepare_requires_openspec_upstream_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root, "change-a")
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))

            bundle = governance_adapter.prepare(root, task_id="task-a", change_id="change-a")

        statuses = {(item["kind"], item["status"]) for item in bundle["evidence"]}
        self.assertIn(("openspec_upstream", "missing"), statuses)
        self.assertFalse(bundle["safe_to_archive"])

    def test_prepare_reports_invalid_openspec_upstream_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root, "change-a")
            target = root / "openspec" / "upstream" / "openspec"
            target.mkdir(parents=True)
            (target / "manifest.json").write_text("{invalid\n", encoding="utf-8")
            spec = task_spec.TaskSpec(task_id="task-a", objective="Implement change")
            spec.save(task_spec.task_spec_path(root, "task-a"))

            bundle = governance_adapter.prepare(root, task_id="task-a", change_id="change-a")

        statuses = {(item["kind"], item["status"]) for item in bundle["evidence"]}
        self.assertIn(("openspec_upstream", "invalid"), statuses)
        self.assertFalse(bundle["safe_to_archive"])


def _write_openspec_change(root: Path, change_id: str, *, with_harness: bool = True) -> None:
    change = root / "openspec" / "changes" / change_id
    change.mkdir(parents=True)
    for name in ("proposal.md", "design.md", "tasks.md"):
        (change / name).write_text(f"# {name}\n", encoding="utf-8")
    spec = change / "specs" / "capability-a" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "## ADDED Requirements\n\n"
        "### Requirement: Capability A\n"
        "The system SHALL provide capability A.\n\n"
        "#### Scenario: Capability A is used\n"
        "- **WHEN** capability A is requested\n"
        "- **THEN** the system provides capability A\n",
        encoding="utf-8",
    )
    if with_harness:
        _write_json(
            change / "harness.json",
            {
                "version": 1,
                "harness_task_id": "task-a",
                "risk_level": "medium",
                "working_set": ["openspec/**"],
                "openspec_upstream": {
                    "package": "@fission-ai/openspec",
                    "version": "1.3.1",
                    "schema": "spec-driven",
                    "manifest": "openspec/upstream/openspec/manifest.json",
                },
                "verification_profile_ids": ["primary"],
                "review_gate": {"type": "codex_xhigh_review_commit", "required": True},
                "memory_policy": {"scope": "project"},
                "archive_gate": {
                    "requires_passed_verification": True,
                    "requires_clean_review": True,
                    "requires_openspec_validate": True,
                },
            },
        )


def _write_openspec_upstream(root: Path) -> None:
    target = root / "openspec" / "upstream" / "openspec"
    target.mkdir(parents=True)
    file_records = []
    for rel in (
        "LICENSE",
        "README.md",
        "package.json",
        "schemas/spec-driven/schema.yaml",
        "schemas/spec-driven/templates/proposal.md",
        "schemas/spec-driven/templates/spec.md",
        "schemas/spec-driven/templates/design.md",
        "schemas/spec-driven/templates/tasks.md",
    ):
        file_path = target / rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f"{rel}\n", encoding="utf-8")
        file_records.append({"path": rel, "source": rel, "sha256": _sha256(file_path)})
    (target / "package.json").write_text(
        json.dumps({"name": "@fission-ai/openspec", "version": "1.3.1", "license": "MIT"}) + "\n",
        encoding="utf-8",
    )
    for item in file_records:
        if item["path"] == "package.json":
            item["sha256"] = _sha256(target / "package.json")
    (target / "NOTICE.md").write_text("# OpenSpec Upstream Snapshot\n", encoding="utf-8")
    file_records.append({"path": "NOTICE.md", "source": "NOTICE.md", "sha256": _sha256(target / "NOTICE.md")})
    _write_json(
        target / "manifest.json",
        {
            "version": 1,
            "package": "@fission-ai/openspec",
            "resolved_version": "1.3.1",
            "schema": "spec-driven",
            "license": "MIT",
            "integrity": "sha512-test",
            "shasum": "abc",
            "source_policy": "official_npm_package_snapshot",
            "telemetry_policy": {
                "OPENSPEC_TELEMETRY": "0",
                "DO_NOT_TRACK": "1",
            },
            "files": file_records,
        },
    )


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in entries) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
