from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import eval_replay  # noqa: E402


class EvalReplayTests(unittest.TestCase):
    def test_create_writes_failure_artifact_testcase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifacts" / "failed.json"
            fixture = root / "fixtures" / "input.json"
            _write_json(fixture, {"name": "fixture"})
            _write_json(
                artifact,
                {
                    "artifact_id": "failed gate",
                    "status": "failed",
                    "command": "py -X utf8 scripts/check.py",
                    "expected_fields": ["status", "artifact_id"],
                    "fixtures": ["fixtures/input.json"],
                },
            )

            result = eval_replay.create_testcase(root, artifact, case_id="failed-gate")

            target = root / ".codex" / "evals" / "failed-gate.json"
            self.assertTrue(result["ok"])
            self.assertTrue(target.exists())
            testcase = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(testcase["kind"], "failure")
            self.assertEqual(testcase["source_artifact"], "artifacts/failed.json")
            self.assertEqual(testcase["fixtures"], ["fixtures/input.json"])

    def test_create_accepts_high_value_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifacts" / "valuable.json"
            _write_json(
                artifact,
                {
                    "artifact_id": "valuable",
                    "status": "passed",
                    "high_value": True,
                    "argv": ["py", "-X", "utf8", "-m", "pytest"],
                    "ok": True,
                },
            )

            result = eval_replay.create_testcase(root, artifact, case_id="valuable")

            testcase = result["testcase"]
            self.assertEqual(testcase["kind"], "high_value")
            self.assertEqual(testcase["command"]["argv"], ["py", "-X", "utf8", "-m", "pytest"])

    def test_list_returns_eval_testcases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / ".codex" / "evals" / "one.json",
                {
                    "version": 1,
                    "case_id": "one",
                    "kind": "failure",
                    "source_artifact": "artifacts/one.json",
                },
            )

            result = eval_replay.list_testcases(root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["cases"][0]["case_id"], "one")
            self.assertEqual(result["cases"][0]["path"], ".codex/evals/one.json")

    def test_run_passes_deterministic_checks_without_executing_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "fixtures" / "input.json", {"ok": True})
            _write_json(
                root / ".codex" / "evals" / "pass.json",
                {
                    "version": 1,
                    "case_id": "pass",
                    "command": {"argv": ["py", "-X", "utf8", "-m", "pytest", "tests/test_eval_replay.py"]},
                    "expected_fields": ["status", "payload.exit_code"],
                    "fixtures": ["fixtures/input.json"],
                    "artifact_snapshot": {"status": "failed", "payload": {"exit_code": 1}},
                },
            )

            result = eval_replay.run_testcases(root)

            self.assertTrue(result["ok"])
            check_names = {item["name"] for item in result["results"][0]["checks"]}
            self.assertIn("no_network_command", check_names)
            self.assertIn("fixtures_exist", check_names)

    def test_run_fails_for_network_command_missing_field_and_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / ".codex" / "evals" / "fail.json",
                {
                    "version": 1,
                    "case_id": "fail",
                    "command": {"command": "curl https://example.test"},
                    "expected_fields": ["status", "missing.field"],
                    "fixtures": ["fixtures/missing.json"],
                    "artifact_snapshot": {"status": "failed"},
                },
            )

            result = eval_replay.run_testcases(root)

            self.assertFalse(result["ok"])
            checks = {item["name"]: item for item in result["results"][0]["checks"]}
            self.assertFalse(checks["no_network_command"]["ok"])
            self.assertFalse(checks["expected_fields_present"]["ok"])
            self.assertFalse(checks["fixtures_exist"]["ok"])


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
