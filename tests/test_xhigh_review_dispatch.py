from __future__ import annotations

import shlex
import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import hook_runner
import memory_store
import workspace_lifecycle
import xhigh_review_dispatch
from workspace_test_helpers import MemoryEnv, route_plan


class XHighReviewDispatchTests(unittest.TestCase):
    def test_runner_command_is_explicit_and_total_timeout_free(self) -> None:
        command = xhigh_review_dispatch.runner_command()
        parts = shlex.split(command, posix=False) if xhigh_review_dispatch.os.name == "nt" else shlex.split(command)
        script = Path(next(part for part in parts if part.strip('"').endswith("review_gate_runner.py")).strip('"'))

        self.assertIn("review_gate_runner.py", command)
        self.assertEqual(script, (PLUGIN_SCRIPTS_DIR / "review_gate_runner.py").resolve())
        self.assertTrue(script.is_absolute())
        self.assertNotEqual(script, Path("plugins/codex-memory/scripts/review_gate_runner.py"))
        self.assertIn(f"--idle-seconds {xhigh_review_dispatch.XHIGH_REVIEW_IDLE_SECONDS}", command)
        self.assertIn("--max-seconds 0", command)
        self.assertGreater(xhigh_review_dispatch.XHIGH_REVIEW_IDLE_SECONDS, 0)
        self.assertIn("--uncommitted", command)
        self.assertNotEqual(command, "codex xhigh review --uncommitted")

    def test_runner_command_quotes_explicit_script_path(self) -> None:
        script = mock.Mock()
        script.resolve.return_value = r"C:\Installed Codex\plugins\codex-memory\scripts\review_gate_runner.py"

        with mock.patch.object(xhigh_review_dispatch.os, "name", "nt"):
            command = xhigh_review_dispatch.command_line(xhigh_review_dispatch.runner_command_parts(script))

        self.assertIn('"C:\\Installed Codex\\plugins\\codex-memory\\scripts\\review_gate_runner.py"', command)
        self.assertNotIn(" ./plugins/codex-memory/scripts/review_gate_runner.py ", command.replace("\\", "/"))

    def test_runner_command_uses_python_when_py_launcher_missing(self) -> None:
        script = mock.Mock()
        script.resolve.return_value = r"C:\Installed Codex\plugins\codex-memory\scripts\review_gate_runner.py"

        def which(name: str) -> str | None:
            return {"python": r"C:\Python312\python.exe"}.get(name)

        with (
            mock.patch.object(xhigh_review_dispatch.shutil, "which", side_effect=which),
            mock.patch.object(xhigh_review_dispatch, "python_version", return_value="3.12.1"),
        ):
            parts = xhigh_review_dispatch.runner_command_parts(script)

        self.assertEqual(parts[:3], [r"C:\Python312\python.exe", "-X", "utf8"])
        self.assertIn(r"C:\Installed Codex\plugins\codex-memory\scripts\review_gate_runner.py", parts)
        self.assertNotIn("py", parts)

    def test_runner_command_matches_codexm_py_launcher_prefix(self) -> None:
        script = mock.Mock()
        script.resolve.return_value = r"C:\Installed Codex\plugins\codex-memory\scripts\review_gate_runner.py"

        def which(name: str) -> str | None:
            return {"py": r"C:\Windows\py.exe", "python": r"C:\Python312\python.exe"}.get(name)

        with (
            mock.patch.object(xhigh_review_dispatch.shutil, "which", side_effect=which),
            mock.patch.object(xhigh_review_dispatch, "python_version", return_value="3.12.1"),
        ):
            parts = xhigh_review_dispatch.runner_command_parts(script)

        self.assertEqual(parts[:4], [r"C:\Windows\py.exe", "-3", "-X", "utf8"])

    def test_review_gate_recommends_runner_subagent_without_autostart(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "review-task",
                        "objective": "Run codex xhigh review --uncommitted as the final review gate",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )

        runtime = result["result"]["task_state"]["metadata"]["workspace_routing"]["subagent_runtime"]
        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        dispatch_plan = routing["subagent_dispatch_plan"]
        self.assertEqual(runtime["status"], "recommended_not_started")
        self.assertEqual(runtime["trigger"], "xhigh_review_gate")
        self.assertEqual(runtime["execution_model"], "host_subagent_or_manual")
        self.assertEqual(runtime["recommended_role"], "XHigh Review Runner")
        self.assertEqual(runtime["timeout_policy"], "progress_output_observation")
        self.assertEqual(runtime["total_timeout_policy"], "none")
        self.assertEqual(runtime["observation_window_policy"], "poll_only_never_interrupt")
        self.assertEqual(runtime["dispatch_roles"], ["xhigh_review_runner"])
        self.assertFalse(runtime["autostart"])
        roles = [item["role"] for item in dispatch_plan["host_spawn_requests"]]
        self.assertEqual(roles, ["XHigh Review Runner"])
        self.assertNotIn("Route Specialist", roles)
        self.assertNotIn("Route Review Specialist", roles)
        self.assertEqual(len(dispatch_plan["host_spawn_requests"]), 1)
        self.assertEqual(dispatch_plan["items"][0]["binding_mode"], "review_gate_runner")
        request = dispatch_plan["host_spawn_requests"][0]
        self.assertIn("review_gate_runner.py", request["command"])
        self.assertIn(f"--idle-seconds {xhigh_review_dispatch.XHIGH_REVIEW_IDLE_SECONDS}", request["command"])
        self.assertIn("--max-seconds 0", request["command"])
        self.assertNotEqual(request["command"], request["alias_command"])
        self.assertEqual(request["alias_command"], "codex xhigh review --uncommitted")
        self.assertEqual(request["total_timeout_policy"], "none")
        self.assertEqual(request["observation_window_policy"], "poll_only_never_interrupt")
        self.assertTrue(request["no_fixed_total_timeout"])
        self.assertEqual(
            request["fallback_command"],
            'codex-raw -- review -c model_reasoning_effort="xhigh" --uncommitted',
        )
        self.assertIn("explicit runner command", request["message"])
        self.assertIn("idle/no-output observation window", request["message"])
        self.assertIn("not a fixed total timeout", request["message"])
        self.assertIn("codex xhigh review --uncommitted", request["message"])
        self.assertIn("Host wait windows are observation polls only", request["message"])
        self.assertIn("codex-raw -- review -c", request["message"])


if __name__ == "__main__":
    unittest.main()
