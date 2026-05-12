from __future__ import annotations

import json
import os
import sys
import tempfile
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

import workspace_lifecycle  # noqa: E402
import memory_store  # noqa: E402
import workspace_task_state  # noqa: E402
import workspace_session  # noqa: E402
import workspace_session_cli  # noqa: E402
import workspace_subagents  # noqa: E402
from workspace_test_helpers import route_plan  # noqa: E402


class RequirementsGateEnforcementTests(unittest.TestCase):
    def test_blocking_gate_removes_write_permission_from_route_bindings(self) -> None:
        plan = _blocked_plan()

        bindings = workspace_lifecycle.create_bindings(plan)

        specialist = next(item for item in bindings if item.get("binding_mode") == "specialist")
        permissions = specialist["permissions"]
        enforcement = specialist["requirements_gate_enforcement"]
        self.assertFalse(permissions["may_write"])
        self.assertTrue(permissions["write_blocked"])
        self.assertEqual(enforcement["status"], "blocked_by_requirements_gate")
        self.assertEqual(enforcement["gate_status"], "needs_clarification")
        self.assertIn("验收条件", enforcement["reason"])

    def test_standalone_workspace_bindings_apply_requirements_gate_block(self) -> None:
        plan = _blocked_plan()

        bindings = workspace_subagents.create_bindings(plan)

        specialist = next(item for item in bindings if item.get("binding_mode") == "specialist")
        self.assertFalse(specialist["permissions"]["may_write"])
        self.assertTrue(specialist["permissions"]["write_blocked"])
        self.assertEqual(
            specialist["requirements_gate_enforcement"]["status"],
            "blocked_by_requirements_gate",
        )

    def test_fallback_action_ask_user_removes_write_permission(self) -> None:
        plan = _fallback_blocked_plan()

        bindings = workspace_subagents.create_bindings(plan)

        specialist = next(item for item in bindings if item.get("binding_mode") == "specialist")
        self.assertFalse(specialist["permissions"]["may_write"])
        self.assertEqual(
            specialist["requirements_gate_enforcement"]["gate_status"],
            "needs_clarification",
        )

    def test_workspace_bind_cli_path_applies_requirements_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            route_path = Path(temp_dir) / "route.json"
            route_path.write_text(json.dumps(_blocked_plan()), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "project_root": str(PROJECT_ROOT),
                    "command": "bind",
                    "route_file": str(route_path),
                    "task_file": None,
                    "task_id": None,
                    "objective": None,
                    "working_set": [],
                    "changed": False,
                    "checkpoint": False,
                },
            )()

            result = workspace_subagents.dispatch(args)

        specialist = next(item for item in result["bindings"] if item.get("binding_mode") == "specialist")
        self.assertFalse(specialist["permissions"]["may_write"])
        self.assertEqual(result["mode"], "bind")

    def test_workspace_bind_cli_path_prefers_adaptive_block(self) -> None:
        passed_plan = route_plan()
        passed_plan["requirements_gate"] = {"status": "passed", "blocking": False}
        with tempfile.TemporaryDirectory() as temp_dir:
            route_path = Path(temp_dir) / "routing.json"
            route_path.write_text(
                json.dumps({"route_plan": passed_plan, "adaptive_route_plan": _blocked_plan()}),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "project_root": str(PROJECT_ROOT),
                    "command": "bind",
                    "route_file": str(route_path),
                    "task_file": None,
                    "task_id": None,
                    "objective": None,
                    "working_set": [],
                    "changed": False,
                    "checkpoint": False,
                },
            )()

            result = workspace_subagents.dispatch(args)

        specialist = next(item for item in result["bindings"] if item.get("binding_mode") == "specialist")
        self.assertFalse(specialist["permissions"]["may_write"])
        self.assertEqual(result["route_plan"]["requirements_gate"]["status"], "needs_clarification")

    def test_passed_gate_keeps_existing_write_permissions(self) -> None:
        plan = route_plan()
        plan["requirements_gate"] = {
            "status": "passed",
            "blocking": False,
            "open_questions": [],
            "missing": [],
        }

        bindings = workspace_lifecycle.create_bindings(plan)

        specialist = next(item for item in bindings if item.get("binding_mode") == "specialist")
        self.assertTrue(specialist["permissions"]["may_write"])
        self.assertNotIn("requirements_gate_enforcement", specialist)

    def test_safe_workspace_routing_exposes_before_write_block(self) -> None:
        plan = _blocked_plan()

        with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=plan):
            routing = workspace_lifecycle.safe_workspace_routing(
                "blocked-write",
                {"objective": "Add feature"},
            )

        self.assertEqual(routing["write_enforcement"]["status"], "blocked_by_requirements_gate")
        self.assertTrue(all(not item["permissions"]["may_write"] for item in routing["bindings"]))

    def test_adaptive_routing_clears_stale_write_enforcement_after_pass(self) -> None:
        blocked_plan = _blocked_plan()
        workspace_routing = {
            "route_plan": blocked_plan,
            "bindings": workspace_lifecycle.create_bindings(blocked_plan),
            "write_enforcement": {"status": "blocked_by_requirements_gate"},
        }
        passed_plan = route_plan()
        passed_plan["requirements_gate"] = {"status": "passed", "blocking": False}

        workspace_lifecycle.merge_adaptive_routing(
            workspace_routing,
            {"route_plan": passed_plan, "bindings": workspace_lifecycle.create_bindings(passed_plan)},
        )

        self.assertEqual(workspace_routing["adaptive_route_plan"]["requirements_gate"]["status"], "passed")
        self.assertNotIn("write_enforcement", workspace_routing)
        self.assertTrue(workspace_routing["bindings"][0]["permissions"]["may_write"])
        self.assertNotIn("requirements_gate_enforcement", workspace_routing["bindings"][0])

    def test_adaptive_blocked_bindings_replace_canonical_bindings(self) -> None:
        passed_plan = route_plan()
        passed_plan["requirements_gate"] = {"status": "passed", "blocking": False}
        workspace_routing = {"route_plan": passed_plan, "bindings": workspace_lifecycle.create_bindings(passed_plan)}
        self.assertTrue(workspace_routing["bindings"][0]["permissions"]["may_write"])

        blocked_plan = _blocked_plan()
        adaptive_routing = {
            "route_plan": blocked_plan,
            "bindings": workspace_lifecycle.create_bindings(blocked_plan),
            "write_enforcement": workspace_lifecycle.requirements_write_enforcement(blocked_plan),
        }
        workspace_lifecycle.merge_adaptive_routing(workspace_routing, adaptive_routing)

        self.assertEqual(workspace_routing["write_enforcement"]["status"], "blocked_by_requirements_gate")
        self.assertTrue(all(not item["permissions"]["may_write"] for item in workspace_routing["bindings"]))

    def test_signal_route_plan_clears_stale_adaptive_write_enforcement(self) -> None:
        passed_plan = route_plan()
        passed_plan["requirements_gate"] = {"status": "passed", "blocking": False}
        stale_blocked_plan = _blocked_plan()
        workspace_routing = {
            "route_plan": stale_blocked_plan,
            "bindings": workspace_lifecycle.create_bindings(stale_blocked_plan),
            "adaptive_route_plan": stale_blocked_plan,
            "adaptive_bindings": workspace_lifecycle.create_bindings(stale_blocked_plan),
            "adaptive_subagent_dispatch_plan": {"status": "stale"},
            "write_enforcement": workspace_lifecycle.requirements_write_enforcement(stale_blocked_plan),
        }

        bindings = workspace_lifecycle.apply_signal_route_plan(workspace_routing, passed_plan, {})

        self.assertNotIn("adaptive_route_plan", workspace_routing)
        self.assertNotIn("adaptive_bindings", workspace_routing)
        self.assertNotIn("adaptive_subagent_dispatch_plan", workspace_routing)
        self.assertNotIn("write_enforcement", workspace_routing)
        self.assertEqual(workspace_session.requirements_gate_write_enforcement(workspace_routing), {})
        self.assertTrue(all(item["permissions"]["may_write"] for item in bindings))

    def test_write_guard_blocks_before_allocating_write_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "registry.jsonl"
            old_registry = _set_registry(registry)
            try:
                result = workspace_session.write_guard(
                    PROJECT_ROOT,
                    session_id="session-a",
                    task_id="task-a",
                    route_plan=_blocked_plan(),
                )
            finally:
                _restore_registry(old_registry)

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "requirements_gate_blocked")
        self.assertFalse(registry.exists())

    def test_write_guard_loads_stored_task_requirements_gate_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            root.joinpath(".codex").mkdir()
            registry = root / "registry.jsonl"
            old_registry = _set_registry(registry)
            old_scope = _set_env("CODEX_MEMORY_SCOPE", "project")
            old_cwd = _set_env("CODEX_MEMORY_CWD", str(root))
            try:
                memory_store.MemoryStore().upsert_task_state(
                    "task-stored",
                    {"metadata": {"workspace_routing": {"route_plan": _blocked_plan()}}},
                )
                result = workspace_session.write_guard(
                    root,
                    session_id="session-stored",
                    task_id="task-stored",
                )
            finally:
                _restore_env("CODEX_MEMORY_CWD", old_cwd)
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_registry(old_registry)

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "requirements_gate_blocked")
        self.assertFalse(registry.exists())

    def test_write_guard_loads_project_task_state_when_ambient_scope_is_global(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            root.joinpath(".codex").mkdir(parents=True)
            registry = Path(temp_dir) / "registry.jsonl"
            codex_home = Path(temp_dir) / "codex-home"
            old_registry = _set_registry(registry)
            old_home = _set_env("CODEX_HOME", str(codex_home))
            old_scope = _set_env("CODEX_MEMORY_SCOPE", "project")
            old_cwd = _set_env("CODEX_MEMORY_CWD", str(root))
            try:
                memory_store.MemoryStore().upsert_task_state(
                    "task-global-ambient",
                    {"metadata": {"workspace_routing": {"route_plan": _blocked_plan()}}},
                )
                os.environ["CODEX_MEMORY_SCOPE"] = "global"
                result = workspace_session.write_guard(
                    root,
                    session_id="session-global-ambient",
                    task_id="task-global-ambient",
                )
            finally:
                _restore_env("CODEX_MEMORY_CWD", old_cwd)
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_env("CODEX_HOME", old_home)
                _restore_registry(old_registry)

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "requirements_gate_blocked")
        self.assertFalse(registry.exists())

    def test_write_guard_reads_canonical_memory_from_managed_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            managed = Path(temp_dir) / "managed"
            root.joinpath(".codex").mkdir(parents=True)
            managed.mkdir()
            registry = Path(temp_dir) / "registry.jsonl"
            old_registry = _set_registry(registry)
            old_scope = _set_env("CODEX_MEMORY_SCOPE", "project")
            old_cwd = _set_env("CODEX_MEMORY_CWD", str(root))

            def fake_project_key(path: Path) -> str:
                resolved = Path(path).resolve(strict=False)
                if resolved in {root.resolve(strict=False), managed.resolve(strict=False)}:
                    return "project-key"
                return ""

            try:
                memory_store.MemoryStore().upsert_task_state(
                    "task-managed",
                    {"metadata": {"workspace_routing": {"route_plan": _blocked_plan()}}},
                )
                with mock.patch.object(workspace_task_state, "_git_project_key", side_effect=fake_project_key):
                    result = workspace_session.write_guard(
                        managed,
                        session_id="session-managed",
                        task_id="task-managed",
                    )
            finally:
                _restore_env("CODEX_MEMORY_CWD", old_cwd)
                _restore_env("CODEX_MEMORY_SCOPE", old_scope)
                _restore_registry(old_registry)

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "requirements_gate_blocked")
        self.assertFalse(registry.exists())

    def test_write_guard_blocks_fallback_action_without_requirements_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "registry.jsonl"
            old_registry = _set_registry(registry)
            try:
                result = workspace_session.write_guard(
                    PROJECT_ROOT,
                    session_id="session-fallback",
                    task_id="task-fallback",
                    route_plan=_fallback_blocked_plan(),
                )
            finally:
                _restore_registry(old_registry)

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["action"], "requirements_gate_blocked")
        self.assertFalse(registry.exists())

    def test_write_guard_cli_accepts_route_plan_file_for_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            route_path = Path(temp_dir) / "route.json"
            route_path.write_text(json.dumps({"route_plan": _blocked_plan()}), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "project_root": str(PROJECT_ROOT),
                    "session_id": "session-cli",
                    "task_id": "task-cli",
                    "path": [],
                    "route_plan_file": str(route_path),
                    "requirements_gate_file": None,
                },
            )()
            payloads: list[dict[str, object]] = []

            def capture(payload: dict[str, object]) -> int:
                payloads.append(payload)
                return 0 if payload.get("ok", True) else 2

            with mock.patch.object(workspace_session_cli, "print_json", side_effect=capture):
                exit_code = workspace_session_cli.cmd_write_guard(args)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payloads[0]["action"], "requirements_gate_blocked")

    def test_route_plan_loader_prefers_adaptive_pass_over_stale_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            route_path = Path(temp_dir) / "routing.json"
            passed_plan = route_plan()
            passed_plan["requirements_gate"] = {"status": "passed", "blocking": False}
            route_path.write_text(
                json.dumps({"route_plan": _blocked_plan(), "adaptive_route_plan": passed_plan}),
                encoding="utf-8",
            )

            loaded = workspace_session_cli.load_route_plan(str(route_path))

        self.assertEqual(loaded["requirements_gate"]["status"], "passed")
        self.assertEqual(workspace_session.requirements_gate_write_enforcement(loaded), {})

    def test_route_plan_loader_prefers_adaptive_block_over_original_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            route_path = Path(temp_dir) / "routing.json"
            passed_plan = route_plan()
            passed_plan["requirements_gate"] = {"status": "passed", "blocking": False}
            route_path.write_text(
                json.dumps({"route_plan": passed_plan, "adaptive_route_plan": _blocked_plan()}),
                encoding="utf-8",
            )

            loaded = workspace_session_cli.load_route_plan(str(route_path))

        enforcement = workspace_session.requirements_gate_write_enforcement(loaded)
        self.assertEqual(loaded["requirements_gate"]["status"], "needs_clarification")
        self.assertEqual(enforcement["status"], "blocked_by_requirements_gate")


def _blocked_plan() -> dict[str, object]:
    plan = route_plan()
    plan["requirements_gate"] = {
        "status": "needs_clarification",
        "blocking": True,
        "open_questions": ["本任务完成后按哪些验收条件判断通过？"],
        "missing": [{"field": "acceptance_criteria", "reason": "缺少可验证的验收条件"}],
        "recommended_next_step": "Ask the user to resolve missing requirements before implementation.",
    }
    plan["fallback_action"] = "ask_user"
    return plan


def _fallback_blocked_plan() -> dict[str, object]:
    plan = route_plan()
    plan["fallback_action"] = "ask_user"
    plan.pop("requirements_gate", None)
    return plan


def _set_registry(registry: Path) -> str | None:
    old_registry = os.environ.get(workspace_session.REGISTRY_ENV)
    os.environ[workspace_session.REGISTRY_ENV] = str(registry)
    return old_registry


def _set_env(name: str, value: str) -> str | None:
    old_value = os.environ.get(name)
    os.environ[name] = value
    return old_value


def _restore_registry(value: str | None) -> None:
    _restore_env(workspace_session.REGISTRY_ENV, value)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
