from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import hook_runner
import memory_store
import shared_memory
import workspace_lifecycle
import workspace_subagents


class WorkspaceReviewRegressionTests(unittest.TestCase):
    def test_after_tool_preserves_scope_guard_violation_after_empty_checkpoint(self) -> None:
        with _memory_env():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=_client_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )
                runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "edit",
                        "summary": "Touched server path",
                        "touched_paths": ["server/api/login.proto"],
                    },
                )
                second = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "note",
                        "summary": "No edited paths",
                        "touched_paths": [],
                    },
                )
                review = runner.run_event("before_response", {"task_id": "route-task"})

        scope_guard = second["result"]["task_state"]["metadata"]["workspace_routing"]["scope_guard"]
        self.assertFalse(scope_guard[0]["ok"])
        self.assertEqual(scope_guard[0]["violations"][0]["path"], "server/api/login.proto")
        self.assertFalse(review["result"]["workspace_routing_review"]["ok"])

    def test_after_tool_skips_scope_guard_for_verification_checkpoint(self) -> None:
        with _memory_env():
            with mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=_client_route_plan()):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {
                        "task_id": "route-task",
                        "objective": "Fix client UI",
                        "working_set": ["client/Assets/Login.cs"],
                    },
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "verification_runner",
                        "summary": "Verification passed",
                        "touched_paths": ["C:/Users/Administrator/.codex/config.toml"],
                    },
                )
                review = runner.run_event("before_response", {"task_id": "route-task"})

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertNotIn("scope_guard", routing)
        self.assertTrue(review["result"]["workspace_routing_review"]["ok"])

    def test_bound_verification_paths_do_not_trigger_adaptive_routing(self) -> None:
        release_plan = _client_route_plan()
        release_plan["task_type"] = "release"
        release_plan["risk_level"] = "release_blocking"
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), release_plan],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Fix client UI"})
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "binding_id": "binding-client-route",
                        "subagent_id": "agent-client-route",
                        "tool_name": "verification_runner",
                        "phase": "verification",
                        "touched_paths": ["scripts/build_release.py"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertEqual(build_route_plan.call_count, 1)
        self.assertNotIn("adaptive_route_plan", routing)
        self.assertFalse(routing["scope_guard"][0]["ok"])
        self.assertEqual(routing["scope_guard"][0]["violations"][0]["path"], "scripts/build_release.py")

    def test_verification_tool_alias_paths_do_not_trigger_adaptive_routing(self) -> None:
        release_plan = _client_route_plan()
        release_plan["task_type"] = "release"
        release_plan["risk_level"] = "release_blocking"
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), release_plan],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Fix client UI"})
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool": "verification_runner",
                        "touched_paths": ["scripts/build_release.py"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertEqual(build_route_plan.call_count, 1)
        self.assertNotIn("adaptive_route_plan", routing)

    def test_workspace_verification_paths_do_not_trigger_adaptive_routing(self) -> None:
        release_plan = _client_route_plan()
        release_plan["task_type"] = "release"
        release_plan["risk_level"] = "release_blocking"
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), release_plan],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Fix client UI"})
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "workspace_verifier",
                        "phase": "workspace_verification",
                        "touched_paths": ["scripts/build_release.py"],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertEqual(build_route_plan.call_count, 1)
        self.assertNotIn("adaptive_route_plan", routing)

    def test_after_tool_metadata_only_updates_adaptive_routing(self) -> None:
        updated_plan = _client_route_plan()
        updated_plan["requirements_gate"] = {"status": "passed", "blocking": False}
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), updated_plan, updated_plan],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {"task_id": "route-task", "objective": "Add feature", "working_set": ["client/Assets/Login.cs"]},
                )
                runner.run_event(
                    "after_tool",
                    {"task_id": "route-task", "tool_name": "verification_runner", "touched_paths": ["scripts/build_release.py"]},
                )
                result = runner.run_event(
                    "after_tool",
                    {
                        "task_id": "route-task",
                        "tool_name": "planning",
                        "metadata": {"acceptance": ["opens"], "requirement_sources": ["issue-1"]},
                    },
                )
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Add feature"})

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertEqual(build_route_plan.call_count, 3)
        for call in build_route_plan.call_args_list[1:]:
            self.assertNotIn("scripts/build_release.py", call.args[1]["working_set"])
        self.assertIn("scripts/build_release.py", result["result"]["task_state"]["working_set"])
        self.assertEqual(routing["adaptive_route_plan"]["requirements_gate"]["status"], "passed")

    def test_after_tool_source_docs_metadata_updates_adaptive_routing(self) -> None:
        updated_plan = _client_route_plan()
        updated_plan["requirements_gate"] = {"status": "passed", "blocking": False}
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), updated_plan],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {"task_id": "route-task", "objective": "Add feature", "working_set": ["client/Assets/Login.cs"]},
                )
                result = runner.run_event(
                    "after_tool",
                    {"task_id": "route-task", "tool_name": "planning", "metadata": {"design_docs": ["docs/design.md"]}},
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        self.assertEqual(build_route_plan.call_count, 2)
        self.assertEqual(routing["adaptive_route_plan"]["requirements_gate"]["status"], "passed")

    def test_real_edit_clears_prior_verification_routing_exclusion(self) -> None:
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), _client_route_plan(), _client_route_plan()],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Update docs"})
                runner.run_event(
                    "after_tool",
                    {"task_id": "route-task", "tool_name": "verification_runner", "touched_paths": ["scripts/build_release.py"]},
                )
                edit = runner.run_event(
                    "after_tool",
                    {"task_id": "route-task", "tool_name": "edit", "touched_paths": ["scripts/build_release.py"]},
                )
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Update docs"})

        metadata = edit["result"]["task_state"]["metadata"]
        self.assertNotIn("scripts/build_release.py", metadata.get("routing_excluded_paths", []))
        self.assertIn("scripts/build_release.py", build_route_plan.call_args.args[1]["working_set"])

    def test_verification_does_not_exclude_existing_working_set_path(self) -> None:
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), _client_route_plan(), _client_route_plan()],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event(
                    "before_task",
                    {"task_id": "route-task", "objective": "Update release script", "working_set": ["scripts/build_release.py"]},
                )
                verification = runner.run_event(
                    "after_tool",
                    {"task_id": "route-task", "tool_name": "verification_runner", "touched_paths": ["scripts/build_release.py"]},
                )
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Update release script"})

        metadata = verification["result"]["task_state"]["metadata"]
        self.assertNotIn("scripts/build_release.py", metadata.get("routing_excluded_paths", []))
        self.assertIn("scripts/build_release.py", build_route_plan.call_args.args[1]["working_set"])

    def test_before_task_explicit_working_set_clears_verification_exclusion(self) -> None:
        with _memory_env():
            with mock.patch.object(
                workspace_lifecycle.workspace_router,
                "build_route_plan",
                side_effect=[_client_route_plan(), _client_route_plan()],
            ) as build_route_plan:
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                runner.run_event("before_task", {"task_id": "route-task", "objective": "Update docs", "working_set": ["docs/guide.md"]})
                runner.run_event(
                    "after_tool",
                    {"task_id": "route-task", "tool_name": "verification_runner", "touched_paths": ["scripts/build_release.py"]},
                )
                result = runner.run_event(
                    "before_task",
                    {"task_id": "route-task", "objective": "Update release script", "working_set": ["scripts/build_release.py"]},
                )

        metadata = result["result"]["task_state"]["metadata"]
        self.assertNotIn("scripts/build_release.py", metadata.get("routing_excluded_paths", []))
        self.assertIn("scripts/build_release.py", build_route_plan.call_args.args[1]["working_set"])

    def test_coordinator_summary_ignores_verification_runner_artifacts(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        client = next(item for item in bindings if item.get("project_id") == "client-unity")
        server = next(item for item in bindings if item.get("project_id") == "server-game")

        summary = workspace_subagents.coordinator_summary(
            bindings,
            [
                _artifact(client, ["client/Assets/Login.cs"]),
                _artifact(server, ["server/api/login.proto"]),
                {
                    "tool_name": "verification_runner",
                    "phase": "verification",
                    "touched_paths": ["client/Assets/Login.cs"],
                },
            ],
            {"overall_status": "passed", "gaps": []},
        )

        self.assertTrue(summary["ok"], summary)
        self.assertEqual(summary["artifact_gaps"], [])
        self.assertEqual(summary["conflicts"], [])

    def test_coordinator_summary_rejects_stale_binding_ids_with_matching_project_id(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        client = next(item for item in bindings if item.get("project_id") == "client-unity")
        server = next(item for item in bindings if item.get("project_id") == "server-game")
        stale_client = _artifact(client, ["client/Assets/Login.cs"])
        stale_client["binding_id"] = "binding-stale-client"
        stale_client["subagent_id"] = "agent-stale-client"

        summary = workspace_subagents.coordinator_summary(
            bindings,
            [stale_client, _artifact(server, ["server/api/login.proto"])],
            {"overall_status": "passed", "gaps": []},
        )

        missing = [item for item in summary["artifact_gaps"] if item["type"] == "missing_checkpoint"]
        self.assertFalse(summary["ok"])
        self.assertIn("binding-client-route", {item["binding_id"] for item in missing})

    def test_promote_escapes_task_id_in_front_matter_source(self) -> None:
        task_id = "task:evil\nstatus: accepted"
        with _memory_env() as temp_dir:
            store = memory_store.MemoryStore()
            store.write_task_summary(task_id, "# Safe\n\nNo secrets.")
            result = shared_memory.promote_task(Path(temp_dir), task_id, title="Safe Entry")
            text = Path(result["path"]).read_text(encoding="utf-8")

        metadata = shared_memory._parse_front_matter(text)
        self.assertEqual(metadata["status"], "proposed")
        self.assertIn("\\nstatus: accepted", metadata["source"])
        self.assertNotIn("\nstatus: accepted", metadata["source"])

    def test_promote_route_entries_are_workspace_scoped(self) -> None:
        with _memory_env() as temp_dir:
            store = memory_store.MemoryStore()
            store.write_task_summary("route-task", "# Route\n\nWorkspace route summary.")
            result = shared_memory.promote_task(Path(temp_dir), "route-task", kind="route", title="Route Entry")
            text = Path(result["path"]).read_text(encoding="utf-8")

        metadata = shared_memory._parse_front_matter(text)
        self.assertEqual(metadata["scope"], "workspace")


def _route_plan() -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "route-task",
        "route_plan_id": "route-route-task",
        "mode": "cross_project_contract",
        "affected_projects": ["client-unity", "server-game"],
        "coordinator_required": True,
        "routes": [
            {
                "route_id": "client-route",
                "project_id": "client-unity",
                "domain": "game_client",
                "cwd": "client",
                "assigned_scope": ["client/Assets"],
            },
            {
                "route_id": "server-route",
                "project_id": "server-game",
                "domain": "game_server",
                "cwd": "server",
                "assigned_scope": ["server/api"],
            },
        ],
        "risk_level": "medium",
        "confidence": 0.8,
        "reasons": ["test"],
        "verification_plan": [],
    }


def _client_route_plan() -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "route-task",
        "route_plan_id": "route-route-task",
        "mode": "single_project",
        "affected_projects": ["client-unity"],
        "routes": [
            {
                "route_id": "client-route",
                "project_id": "client-unity",
                "domain": "game_client",
                "cwd": "client",
                "assigned_scope": ["client/Assets"],
            }
        ],
        "risk_level": "medium",
        "confidence": 0.8,
        "reasons": ["test"],
        "verification_plan": [],
    }


def _artifact(binding: dict[str, object], touched_paths: list[str]) -> dict[str, object]:
    binding_id = str(binding["binding_id"])
    return {
        "dispatch_id": f"dispatch-{binding_id}",
        "binding_id": binding_id,
        "subagent_id": str(binding["subagent_id"]),
        "project_id": str(binding["project_id"]),
        "domain": str(binding["domain"]),
        "assigned_scope": list(binding["assigned_scope"]),
        "touched_paths": touched_paths,
    }


class _memory_env:
    def __enter__(self) -> str:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        self.old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        os.environ["CODEX_MEMORY_SCOPE"] = "project"
        os.environ["CODEX_MEMORY_CWD"] = self.temp_dir.name
        Path(self.temp_dir.name, ".codex").mkdir()
        return self.temp_dir.name

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _restore_env("CODEX_MEMORY_SCOPE", self.old_scope)
        _restore_env("CODEX_MEMORY_CWD", self.old_cwd)
        self.temp_dir.cleanup()


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
