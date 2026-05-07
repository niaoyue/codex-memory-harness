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
import review_gate_env
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
        self.assertNotIn("codex xhigh review --uncommitted", request["message"])
        self.assertEqual(request["alias_command"], "codex xhigh review --uncommitted")
        self.assertIn("Host wait windows are observation polls only", request["message"])
        self.assertIn("codex-raw -- review -c", request["message"])

    def test_ambient_review_gate_env_does_not_suppress_normal_dispatch(self) -> None:
        old_running = xhigh_review_dispatch.os.environ.get(review_gate_env.REVIEW_GATE_RUNNING_ENV)
        old_disable = xhigh_review_dispatch.os.environ.get(review_gate_env.XHIGH_REVIEW_DISPATCH_DISABLE_ENV)
        with MemoryEnv():
            try:
                xhigh_review_dispatch.os.environ[review_gate_env.REVIEW_GATE_RUNNING_ENV] = "1"
                xhigh_review_dispatch.os.environ[review_gate_env.XHIGH_REVIEW_DISPATCH_DISABLE_ENV] = "1"
                with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                    runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                    result = runner.run_event(
                        "before_task",
                        {
                            "task_id": "nested-review-task",
                            "objective": "Run codex xhigh review --uncommitted as the final review gate",
                            "working_set": ["client/Assets/Login.cs"],
                        },
                    )
            finally:
                _restore_env(review_gate_env.REVIEW_GATE_RUNNING_ENV, old_running)
                _restore_env(review_gate_env.XHIGH_REVIEW_DISPATCH_DISABLE_ENV, old_disable)

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["trigger"], "xhigh_review_gate")
        self.assertIn("subagent_dispatch_plan", routing)

    def test_review_gate_runtime_flags_suppress_nested_runner_dispatch(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "nested-review-task",
                        "objective": (
                            "Role: XHigh Review Runner. Do not wrap the SubAgent or review runner "
                            "in any fixed timeout. Run codex xhigh review --uncommitted."
                        ),
                        "working_set": ["client/Assets/Login.cs"],
                        "review_gate_running": True,
                        "xhigh_review_dispatch_disabled": True,
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["trigger"], "review_gate_dispatch_disabled")
        self.assertEqual(runtime["execution_model"], "main_agent_serial")
        self.assertFalse(runtime["recommended"])
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertTrue(runtime["decision_factors"]["review_gate_dispatch_disabled"])
        self.assertNotIn("subagent_dispatch_plan", routing)

    def test_review_gate_runtime_flags_do_not_persist_across_same_task(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                store = memory_store.MemoryStore()
                runner = hook_runner.HookRunner(memory_store=store)
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "review-task",
                        "objective": (
                            "Role: XHigh Review Runner. Do not wrap the SubAgent or review runner "
                            "in any fixed timeout. Run codex xhigh review --uncommitted."
                        ),
                        "working_set": ["client/Assets/Login.cs"],
                        "review_gate_running": True,
                        "xhigh_review_dispatch_disabled": True,
                    },
                )
                stored = store.get_task_state("review-task")
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "review-task",
                        "objective": "Run codex xhigh review --uncommitted as the final review gate",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )

        stored_metadata = stored["metadata"]
        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertNotIn("review_gate_running", stored_metadata)
        self.assertNotIn("xhigh_review_dispatch_disabled", stored_metadata)
        self.assertEqual(routing["subagent_runtime"]["trigger"], "xhigh_review_gate")
        self.assertIn("subagent_dispatch_plan", routing)

    def test_stale_review_gate_metadata_does_not_suppress_future_dispatch(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        "task_id": "review-task",
                        "objective": "Run codex xhigh review --uncommitted as the final review gate",
                        "working_set": ["client/Assets/Login.cs"],
                        "metadata": {
                            "review_gate_running": True,
                            "xhigh_review_dispatch_disabled": True,
                        },
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertEqual(routing["subagent_runtime"]["trigger"], "xhigh_review_gate")
        self.assertIn("subagent_dispatch_plan", routing)

    def test_after_tool_review_gate_flags_clear_stale_dispatch_plan(self) -> None:
        with MemoryEnv():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan()):
                store = memory_store.MemoryStore()
                runner = hook_runner.HookRunner(memory_store=store)
                before = runner.run_event(
                    "before_task",
                    {
                        "task_id": "review-task",
                        "objective": "Run codex xhigh review --uncommitted as the final review gate",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )
                after = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "review-task",
                        "tool_name": "review-runner",
                        "summary": "Runner checkpoint inside active gate",
                        "touched_paths": ["client/Assets/Login.cs"],
                        "review_gate_running": True,
                        "xhigh_review_dispatch_disabled": True,
                    },
                )

        before_routing = before["result"]["task_state"]["metadata"]["workspace_routing"]
        after_routing = after["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertIn("subagent_dispatch_plan", before_routing)
        self.assertEqual(after_routing["subagent_runtime"]["trigger"], "review_gate_dispatch_disabled")
        self.assertNotIn("subagent_dispatch_plan", after_routing)
        self.assertNotIn("adaptive_subagent_dispatch_plan", after_routing)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        xhigh_review_dispatch.os.environ.pop(name, None)
    else:
        xhigh_review_dispatch.os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
