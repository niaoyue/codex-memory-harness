from __future__ import annotations

import io
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

import workspace_verifier
import task_spec


class WorkspaceVerifierTests(unittest.TestCase):
    def test_workspace_verifier_runs_route_profiles_with_route_cwd(self) -> None:
        captured_cwds: list[str] = []

        def fake_run(spec: object, project_root: Path, max_output_chars: int) -> dict[str, object]:
            captured_cwds.append(getattr(spec, "cwd"))
            return {"ok": True, "exit_code": 0, "duration_seconds": 0.01}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            _mkdir(root / "client")
            route_plan = _route_plan("client", ["client_quick"])

            with mock.patch.object(workspace_verifier.verification_runner, "run_command", side_effect=fake_run):
                aggregation = workspace_verifier.aggregate_verification(root, route_plan)

        self.assertEqual(aggregation["overall_status"], "passed")
        self.assertEqual(captured_cwds, ["client"])
        self.assertEqual(aggregation["results"][0]["profile_id"], "client_quick")
        self.assertEqual(aggregation["results"][0]["status"], "passed")

    def test_workspace_verifier_records_missing_profile_as_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            route_plan = _route_plan("client", ["missing_profile"])

            aggregation = workspace_verifier.aggregate_verification(root, route_plan, no_run=True)

        self.assertEqual(aggregation["overall_status"], "gap")
        self.assertEqual(aggregation["gaps"][0]["profile_id"], "missing_profile")
        self.assertTrue(aggregation["gaps"][0]["blocking"])

    def test_workspace_verifier_records_invalid_route_cwd_as_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            route_plan = _route_plan("missing-client", ["client_quick"])

            aggregation = workspace_verifier.aggregate_verification(root, route_plan)

        self.assertEqual(aggregation["overall_status"], "gap")
        self.assertEqual(aggregation["results"], [])
        self.assertTrue(aggregation["gaps"][0]["blocking"])
        self.assertIn("cwd does not exist", aggregation["gaps"][0]["reason"])

    def test_workspace_verifier_records_actual_command_cwd(self) -> None:
        def fake_run(spec: object, project_root: Path, max_output_chars: int) -> dict[str, object]:
            return {
                "ok": True,
                "exit_code": 0,
                "duration_seconds": 0.01,
                "cwd": str(project_root / "tools"),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root, command_cwd="tools")
            _mkdir(root / "client")
            _mkdir(root / "tools")
            route_plan = _route_plan("client", ["client_quick"])

            with mock.patch.object(workspace_verifier.verification_runner, "run_command", side_effect=fake_run):
                aggregation = workspace_verifier.aggregate_verification(root, route_plan)

        self.assertEqual(aggregation["results"][0]["cwd"], str(root / "tools"))

    def test_workspace_verifier_normalizes_plan_blocking_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            route_plan = _route_plan("client", ["client_quick"])
            del route_plan["verification_plan"][0]["blocking"]

            aggregation = workspace_verifier.aggregate_verification(root, route_plan, no_run=True)

        self.assertTrue(aggregation["verification_plan"][0]["blocking"])

    def test_release_blocking_gate_blocks_bare_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            _write_text(root / "client" / "Assets" / "Login.cs", "Debug.Log(\"release leak\");\n")
            route_plan = _route_plan("client", ["client_quick"])
            route_plan["risk_level"] = "release_blocking"
            route_plan["routes"] = [
                {
                    "route_id": "client-release",
                    "project_id": "client",
                    "domain": "game_client",
                    "cwd": "client",
                    "assigned_scope": ["client/Assets"],
                }
            ]

            aggregation = workspace_verifier.aggregate_verification(root, route_plan, no_run=True)

        self.assertEqual(aggregation["overall_status"], "blocked")
        gate = aggregation["release_gates"]["diagnostic_logging_disabled"]
        self.assertTrue(gate["blocking"])
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["findings"][0]["type"], "bare_log")

    def test_release_blocking_gate_passes_clean_scoped_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            _write_text(root / "client" / "Assets" / "Login.cs", "DiagnosticLog.Flow(\"ok\");\n")
            route_plan = _route_plan("client", ["client_quick"])
            route_plan["risk_level"] = "release_blocking"
            route_plan["routes"] = [
                {
                    "route_id": "client-release",
                    "project_id": "client",
                    "domain": "game_client",
                    "cwd": "client",
                    "assigned_scope": ["client/Assets"],
                }
            ]

            aggregation = workspace_verifier.aggregate_verification(root, route_plan, no_run=True)

        gate = aggregation["release_gates"]["diagnostic_logging_disabled"]
        self.assertEqual(gate["status"], "passed")
        self.assertEqual(aggregation["overall_status"], "not_run")

    def test_main_skips_checkpoint_when_route_task_spec_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            route_plan = _route_plan("client", ["client_quick"])
            route_file = root / "route.json"
            route_file.write_text(json.dumps(route_plan), encoding="utf-8")

            with (
                mock.patch.object(workspace_verifier, "checkpoint", return_value={"ok": True}) as checkpoint,
                mock.patch("sys.stdout", io.StringIO()),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "workspace_verifier.py",
                        "--project-root",
                        str(root),
                        "--route-file",
                        str(route_file),
                        "--no-run",
                    ],
                ),
            ):
                exit_code = workspace_verifier.main()

        self.assertEqual(exit_code, 0)
        checkpoint.assert_not_called()

    def test_main_checkpoints_route_plan_task_id_when_task_spec_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_harness_config(root)
            route_plan = _route_plan("client", ["client_quick"])
            route_file = root / "route.json"
            route_file.write_text(json.dumps(route_plan), encoding="utf-8")
            spec = task_spec.TaskSpec(task_id="verify-task", objective="Verify route", project_root=str(root))
            spec.save(task_spec.task_spec_path(root, spec.task_id))

            with (
                mock.patch.object(workspace_verifier, "checkpoint", return_value={"ok": True}) as checkpoint,
                mock.patch("sys.stdout", io.StringIO()),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "workspace_verifier.py",
                        "--project-root",
                        str(root),
                        "--route-file",
                        str(route_file),
                        "--no-run",
                    ],
                ),
            ):
                exit_code = workspace_verifier.main()

        self.assertEqual(exit_code, 0)
        checkpoint.assert_called_once()
        self.assertEqual(checkpoint.call_args.args[1], "verify-task")


def _route_plan(cwd: str, profiles: list[str]) -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "verify-task",
        "route_plan_id": "route-verify-task",
        "mode": "single_project",
        "affected_projects": ["client"],
        "routes": [],
        "risk_level": "medium",
        "confidence": 0.8,
        "reasons": ["test"],
        "verification_plan": [
            {
                "project_id": "client",
                "domain": "game_client",
                "cwd": cwd,
                "verification_profile_ids": profiles,
                "blocking": True,
            }
        ],
    }


def _write_harness_config(root: Path, command_cwd: str | None = None) -> None:
    command: dict[str, object] = {
        "command": 'py -X utf8 -c "print(123)"',
        "timeout_seconds": 30,
    }
    if command_cwd:
        command["cwd"] = command_cwd
    _write_json(
        root / ".codex" / "harness" / "commands.json",
        {
            "version": 1,
            "settings": {"max_output_chars": 1200},
            "commands": {
                "client_unit": command
            },
        },
    )
    _write_json(
        root / ".codex" / "harness" / "project_profile.json",
        {
            "version": 1,
            "verification": {
                "client_quick": ["client_unit"],
            },
        },
    )


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
