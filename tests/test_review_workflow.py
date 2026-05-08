from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import review_workflow


class ReviewWorkflowTests(unittest.TestCase):
    def test_preflight_records_diff_fingerprint_and_slice_plan(self) -> None:
        with temp_repo() as root:
            _write(root / "plugins" / "codex-memory" / "scripts" / "sample.py", "print('changed')\n")

            result = review_workflow.preflight(root, task_id="review-task")
            preflight_exists = (root / ".codex" / "harness" / "review" / "preflight.json").exists()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["diff_fingerprint"]["algorithm"], "sha256")
        self.assertTrue(result["diff_fingerprint"]["fingerprint"].startswith("sha256:"))
        self.assertEqual(result["slice_plan"][0]["kind"], "runtime")
        self.assertTrue(preflight_exists)

    def test_untracked_content_changes_fingerprint_and_sensitive_scan(self) -> None:
        with temp_repo() as root:
            target = root / "new-secret.txt"
            _write(target, "plain text\n")
            first = review_workflow.diff_fingerprint(root)["fingerprint"]
            target.write_text("OPENAI_" + "API_" + "KEY=" + "sk-" + "sampletokenvalue12345\n", encoding="utf-8")
            second = review_workflow.diff_fingerprint(root)["fingerprint"]
            result = review_workflow.preflight(root, task_id="review-task")

        sensitive = next(item for item in result["checks"] if item["name"] == "sensitive_scan")
        self.assertNotEqual(first, second)
        self.assertFalse(sensitive["ok"])

    def test_preflight_checks_cached_diff_for_staged_changes(self) -> None:
        with temp_repo() as root:
            tracked = root / "README.md"
            tracked.write_text("# test   \n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            tracked.write_text("# test\n", encoding="utf-8")

            result = review_workflow.preflight(root, mode="uncommitted", task_id="review-task")

        diff = next(item for item in result["checks"] if item["name"] == "git_diff_check")
        cached = next(item for item in diff["checks"] if item["name"] == "cached")
        self.assertFalse(diff["ok"])
        self.assertFalse(cached["ok"])

    def test_package_boundary_honors_staged_mode(self) -> None:
        with temp_repo() as root:
            _write(root / ".codex" / "memories" / "memory.db", "unstaged runtime")

            result = review_workflow.preflight(root, mode="staged", task_id="review-task")

        boundary = next(item for item in result["checks"] if item["name"] == "package_boundary")
        self.assertTrue(result["ok"], result)
        self.assertTrue(boundary["ok"])
        self.assertEqual(boundary["blocked_paths"], [])

    def test_package_boundary_honors_working_mode(self) -> None:
        with temp_repo() as root:
            _write(root / ".codex" / "memories" / "memory.db", "staged runtime")
            subprocess.run(["git", "add", ".codex/memories/memory.db"], cwd=root, check=True)

            result = review_workflow.preflight(root, mode="working", task_id="review-task")

        boundary = next(item for item in result["checks"] if item["name"] == "package_boundary")
        self.assertTrue(result["ok"], result)
        self.assertTrue(boundary["ok"])
        self.assertEqual(boundary["blocked_paths"], [])

    def test_package_boundary_blocks_runtime_files(self) -> None:
        with temp_repo() as root:
            _write(root / ".codex" / "memories" / "memory.db", "not a real db")

            result = review_workflow.preflight(root, task_id="review-task")

        boundary = next(item for item in result["checks"] if item["name"] == "package_boundary")
        self.assertFalse(result["ok"])
        self.assertFalse(boundary["ok"])
        self.assertIn(".codex/memories/memory.db", boundary["blocked_paths"])

    def test_package_boundary_blocks_review_runtime_artifacts(self) -> None:
        with temp_repo() as root:
            _write(root / ".codex" / "harness" / "review" / "final-xhigh" / "stderr.log", "old finding\n")

            result = review_workflow.preflight(root, task_id="review-task")

        boundary = next(item for item in result["checks"] if item["name"] == "package_boundary")
        self.assertFalse(result["ok"])
        self.assertFalse(boundary["ok"])
        self.assertIn(".codex/harness/review/final-xhigh/stderr.log", boundary["blocked_paths"])

    def test_package_boundary_matches_runtime_paths_on_segment_boundaries(self) -> None:
        with temp_repo() as root:
            _write(root / "distillation" / "notes.md", "reviewable docs\n")
            _write(root / ".codex" / "harness" / "review-notes.md", "reviewable docs\n")

            result = review_workflow.preflight(root, task_id="review-task")

        boundary = next(item for item in result["checks"] if item["name"] == "package_boundary")
        self.assertTrue(result["ok"], result)
        self.assertTrue(boundary["ok"])
        self.assertEqual(boundary["blocked_paths"], [])

    def test_sensitive_scan_reads_full_untracked_file_content(self) -> None:
        marker = "sampletokenvalue12345"
        with temp_repo() as root:
            payload = "a" * 270000 + "\n" + "OPENAI_" + "API_" + "KEY=sk-" + marker + "\n"
            _write(root / "large-untracked.txt", payload)

            result = review_workflow.preflight(root, task_id="review-task")

        sensitive = next(item for item in result["checks"] if item["name"] == "sensitive_scan")
        self.assertFalse(result["ok"])
        self.assertFalse(sensitive["ok"])
        self.assertTrue(any("api_key" in item for item in sensitive["report"]["categories"]))

    def test_record_infra_failure_adds_recoverable_policy(self) -> None:
        with temp_repo() as root:
            result = review_workflow.record_review(
                root,
                {"ok": False, "stderr_tail": ["429 rate limit"]},
                task_id="review-task",
            )

        entry = result["entry"]
        self.assertEqual(entry["status"], "infra_failed")
        self.assertEqual(entry["runner_status"], "infra_failed")
        self.assertEqual(entry["recoverable_failure_policy"]["primary_action"], "send_input_to_active_review_runner")

    def test_record_clean_requires_reviewed_fingerprint(self) -> None:
        with temp_repo() as root:
            result = review_workflow.record_review(
                root,
                {"ok": True},
                task_id="review-task",
            )

        entry = result["entry"]
        self.assertFalse(result["ok"])
        self.assertEqual(entry["status"], "invalidated")
        self.assertEqual(entry["fingerprint_validation"]["reason"], "missing_reviewed_diff_fingerprint")

    def test_record_clean_rejects_changed_reviewed_fingerprint(self) -> None:
        with temp_repo() as root:
            reviewed = review_workflow.diff_fingerprint(root)
            _write(root / "README.md", "# changed\n")

            result = review_workflow.record_review(
                root,
                {"ok": True, "diff_fingerprint": reviewed},
                task_id="review-task",
            )

        entry = result["entry"]
        self.assertFalse(result["ok"])
        self.assertEqual(entry["status"], "invalidated")
        self.assertEqual(entry["diff_fingerprint"]["fingerprint"], reviewed["fingerprint"])
        self.assertEqual(entry["fingerprint_validation"]["reason"], "reviewed_diff_changed")

    def test_clean_payload_with_timeout_policy_is_not_infra_failure(self) -> None:
        with temp_repo() as root:
            fingerprint = review_workflow.diff_fingerprint(root)
            result = review_workflow.record_review(
                root,
                {
                    "ok": True,
                    "diff_fingerprint": fingerprint,
                    "idle_timeout": False,
                    "max_timeout": False,
                    "total_timeout_policy": "none",
                },
                task_id="review-task",
            )

        entry = result["entry"]
        self.assertEqual(entry["status"], "clean")
        self.assertEqual(entry["runner_status"], "completed")
        self.assertNotIn("recoverable_failure_policy", entry)

    def test_record_structured_runner_findings_without_tails(self) -> None:
        with temp_repo() as root:
            fingerprint = review_workflow.diff_fingerprint(root)
            result = review_workflow.record_review(
                root,
                {
                    "ok": False,
                    "diff_fingerprint": fingerprint,
                    "review_findings_count": 1,
                    "review_finding_priorities": ["P1"],
                },
                task_id="review-task",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["entry"]["status"], "findings")
        self.assertEqual(result["entry"]["findings"][0]["severity"], "P1")
        self.assertEqual(result["entry"]["findings"][0]["source"], "review_runner_summary")

    def test_record_ok_payload_with_findings_is_not_clean(self) -> None:
        with temp_repo() as root:
            fingerprint = review_workflow.diff_fingerprint(root)
            result = review_workflow.record_review(
                root,
                {
                    "ok": True,
                    "diff_fingerprint": fingerprint,
                    "findings": [{"id": "finding-001", "summary": "Blocking review finding"}],
                },
                task_id="review-task",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["entry"]["status"], "findings")
        self.assertEqual(result["entry"]["runner_status"], "completed")
        self.assertEqual(result["entry"]["findings"][0]["summary"], "Blocking review finding")

    def test_record_clean_runner_result_uses_saved_preflight_fingerprint(self) -> None:
        with temp_repo() as root:
            review_workflow.preflight(root, task_id="review-task")
            result = review_workflow.record_review(
                root,
                {"ok": True, "exit_code": 0, "stdout_tail": [], "stderr_tail": []},
                task_id="review-task",
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["entry"]["status"], "clean")
        self.assertNotIn("fingerprint_validation", result["entry"])

    def test_working_mode_package_boundary_includes_untracked_runtime(self) -> None:
        with temp_repo() as root:
            _write(root / ".codex" / "harness" / "review" / "final-xhigh" / "stderr.log", "old finding\n")

            result = review_workflow.preflight(root, mode="working", task_id="review-task")

        boundary = next(item for item in result["checks"] if item["name"] == "package_boundary")
        self.assertFalse(result["ok"])
        self.assertFalse(boundary["ok"])
        self.assertIn(".codex/harness/review/final-xhigh/stderr.log", boundary["blocked_paths"])

    def test_cli_accepts_documented_subcommand_mode_flags(self) -> None:
        with temp_repo() as root:
            by_mode = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(PLUGIN_SCRIPTS_DIR / "review_workflow.py"),
                    "--project-root",
                    str(root),
                    "preflight",
                    "--mode",
                    "uncommitted",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            by_alias = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(PLUGIN_SCRIPTS_DIR / "review_workflow.py"),
                    "--project-root",
                    str(root),
                    "status",
                    "--uncommitted",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            top_level_mode = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(PLUGIN_SCRIPTS_DIR / "review_workflow.py"),
                    "--project-root",
                    str(root),
                    "--mode",
                    "staged",
                    "status",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(by_mode.returncode, 0, by_mode.stderr)
        self.assertEqual(by_alias.returncode, 0, by_alias.stderr)
        self.assertEqual(top_level_mode.returncode, 0, top_level_mode.stderr)
        self.assertEqual(json.loads(top_level_mode.stdout)["mode"], "staged")

    def test_resolved_findings_still_require_final_rerun(self) -> None:
        with temp_repo() as root:
            review_workflow.record_review(
                root,
                {"ok": False, "findings": [{"id": "finding-001", "summary": "Bug"}]},
                task_id="review-task",
            )
            before = review_workflow.findings_list(root)
            review_workflow.resolve_finding(root, "finding-001", evidence="fixed in test")
            after = review_workflow.findings_list(root)

        self.assertEqual(len(before["findings"]), 1)
        self.assertEqual(after["findings"], [])
        self.assertTrue(after["requires_final_review_rerun"])

    def test_resolved_findings_are_scoped_to_review(self) -> None:
        with temp_repo() as root:
            first = review_workflow.record_review(
                root,
                {"ok": False, "findings": [{"id": "finding-001", "summary": "First"}]},
                task_id="review-task",
            )
            _write(root / "README.md", "# changed\n")
            second = review_workflow.record_review(
                root,
                {"ok": False, "findings": [{"id": "finding-001", "summary": "Second"}]},
                task_id="review-task",
            )

            review_workflow.resolve_finding(
                root,
                "finding-001",
                review_id=first["entry"]["review_id"],
                evidence="fixed first",
            )
            after = review_workflow.findings_list(root)

        remaining = after["findings"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["summary"], "Second")
        self.assertEqual(remaining[0]["review_id"], second["entry"]["review_id"])

    def test_resolve_finding_defaults_to_latest_matching_review(self) -> None:
        with temp_repo() as root:
            review_workflow.record_review(
                root,
                {"ok": False, "findings": [{"id": "finding-001", "summary": "First"}]},
                task_id="review-task",
            )
            _write(root / "README.md", "# changed\n")
            review_workflow.record_review(
                root,
                {"ok": False, "findings": [{"id": "finding-001", "summary": "Second"}]},
                task_id="review-task",
            )

            review_workflow.resolve_finding(root, "finding-001", evidence="fixed latest")
            after = review_workflow.findings_list(root)

        remaining = after["findings"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["summary"], "First")


class temp_repo:
    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
        _write(root / "README.md", "# test\n")
        _write(root / ".codex" / "harness" / "commands.json", '{"version":1}\n')
        _write(root / ".codex" / "harness" / "project_profile.json", '{"version":1}\n')
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
        self.root = root
        return root

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.temp_dir.cleanup()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
