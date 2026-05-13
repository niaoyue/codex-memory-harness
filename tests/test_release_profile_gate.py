from __future__ import annotations

import json
import io
import hashlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import release_profile_gate  # noqa: E402


class ReleaseProfileGateTests(unittest.TestCase):
    def test_release_manifest_passes_with_artifacts_rollback_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "dist" / "game.zip"
            artifact.parent.mkdir()
            artifact.write_text("package", encoding="utf-8")

            result = release_profile_gate.evaluate_release_manifest(
                root,
                {
                    "release_id": "v1",
                    "platforms": ["webgl"],
                    "artifacts": [{"kind": "package", "path": "dist/game.zip", "platforms": ["webgl"]}],
                    "rollback_plan": {"summary": "restore previous package"},
                    "evidence": {key: True for key in release_profile_gate.RELEASE_GATE_KEYS},
                },
            )

        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["blocking_gaps"])

    def test_release_manifest_blocks_missing_rollback_and_gate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = release_profile_gate.evaluate_release_manifest(
                Path(temp_dir),
                {"release_id": "v1", "platforms": ["webgl"], "artifacts": [{"path": "missing.zip"}]},
            )

        self.assertEqual(result["status"], "blocked")
        gap_types = {item["type"] for item in result["blocking_gaps"]}
        self.assertIn("rollback_plan", gap_types)
        self.assertIn("artifact", gap_types)
        self.assertIn("release_gate", gap_types)

    def test_release_manifest_cli_returns_zero_for_passing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "dist" / "game.zip"
            artifact.parent.mkdir()
            artifact.write_text("package", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "release_id": "v1",
                        "platforms": ["webgl"],
                        "artifacts": [{"kind": "package", "path": "dist/game.zip", "platforms": ["webgl"]}],
                        "rollback_plan": "restore previous package",
                        "evidence": {key: True for key in release_profile_gate.RELEASE_GATE_KEYS},
                    }
                ),
                encoding="utf-8",
            )

            old_argv = sys.argv
            try:
                sys.argv = [
                    "release_profile_gate.py",
                    "--project-root",
                    str(root),
                    "--manifest-file",
                    str(manifest),
                ]
                with redirect_stdout(io.StringIO()):
                    exit_code = release_profile_gate.main()
            finally:
                sys.argv = old_argv

        self.assertEqual(exit_code, 0)

    def test_release_manifest_validates_artifact_schema_hash_size_and_report_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "dist" / "game.zip"
            report = root / "reports" / "build.json"
            artifact.parent.mkdir()
            report.parent.mkdir()
            artifact.write_text("package", encoding="utf-8")
            report.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

            result = release_profile_gate.evaluate_release_manifest(
                root,
                {
                    "release_id": "v1",
                    "platforms": ["webgl", "wechat-minigame"],
                    "artifacts": [
                        {
                            "kind": "package",
                            "path": "dist/game.zip",
                            "platforms": ["webgl", "wechat-minigame"],
                            "sha256": digest,
                            "size_bytes": artifact.stat().st_size,
                        },
                        {
                            "kind": "build_report",
                            "path": "reports/build.json",
                            "platforms": ["webgl", "wechat-minigame"],
                        },
                    ],
                    "rollback_plan": "restore previous package",
                    "evidence": {
                        key: {"status": "passed", "report_path": "reports/build.json"}
                        for key in release_profile_gate.RELEASE_GATE_KEYS
                    },
                },
            )

        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["blocking_gaps"])

    def test_release_manifest_blocks_invalid_artifact_schema_and_evidence_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "dist" / "game.zip"
            artifact.parent.mkdir()
            artifact.write_text("package", encoding="utf-8")
            result = release_profile_gate.evaluate_release_manifest(
                root,
                {
                    "release_id": "v1",
                    "platforms": ["webgl", "wechat-minigame"],
                    "artifacts": [
                        {"kind": "unknown", "path": "dist/game.zip", "platforms": ["webgl"], "sha256": "bad"},
                        {"kind": "package", "platforms": ["wechat-minigame"]},
                    ],
                    "rollback_plan": "restore previous package",
                    "evidence": {
                        key: {"status": "passed", "report_path": "missing/report.json"}
                        for key in release_profile_gate.RELEASE_GATE_KEYS
                    },
                },
            )

        self.assertEqual(result["status"], "blocked")
        gap_types = {item["type"] for item in result["blocking_gaps"]}
        self.assertIn("artifact_kind", gap_types)
        self.assertIn("artifact_path", gap_types)
        self.assertIn("artifact_checksum", gap_types)
        self.assertIn("evidence_report", gap_types)

    def test_release_manifest_reports_directory_integrity_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_dir = root / "dist"
            artifact_dir.mkdir()
            result = release_profile_gate.evaluate_release_manifest(
                root,
                {
                    "release_id": "v1",
                    "platforms": ["webgl"],
                    "artifacts": [
                        {
                            "kind": "package",
                            "path": "dist",
                            "platforms": ["webgl"],
                            "sha256": "0" * 64,
                            "size_bytes": 10,
                        }
                    ],
                    "rollback_plan": "restore previous package",
                    "evidence": {key: True for key in release_profile_gate.RELEASE_GATE_KEYS},
                },
            )

        self.assertEqual(result["status"], "blocked")
        gap_types = {item["type"] for item in result["blocking_gaps"]}
        self.assertIn("artifact_checksum", gap_types)
        self.assertIn("artifact_size", gap_types)


if __name__ == "__main__":
    unittest.main()
