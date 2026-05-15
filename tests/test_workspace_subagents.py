from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import workspace_subagents


class WorkspaceSubagentTests(unittest.TestCase):
    def test_bindings_include_coordinator_for_cross_project_route(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())

        self.assertEqual(bindings[0]["binding_mode"], "coordinator")
        self.assertEqual(bindings[0]["coordinates_projects"], ["client-unity", "server-game"])
        specialist_ids = {item["project_id"] for item in bindings[1:]}
        self.assertEqual(specialist_ids, {"client-unity", "server-game"})
        self.assertIn("artifact_policy", bindings[1])
        self.assertIn("dispatch_id", bindings[1]["artifact_policy"]["required_fields"])
        self.assertIn("binding_id", bindings[1]["artifact_policy"]["required_fields"])
        self.assertIn("subagent_id", bindings[1]["artifact_policy"]["required_fields"])
        self.assertEqual(bindings[1]["scope_guard"]["on_violation"], "report_cross_project_dependency")

    def test_scope_guard_reports_paths_outside_assigned_scope(self) -> None:
        binding = workspace_subagents.create_bindings(_route_plan())[1]
        result = workspace_subagents.check_scope(
            binding,
            ["client/Assets/Scripts/Login.cs", "server/api/login.proto"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["allowed_paths"], ["client/Assets/Scripts/Login.cs"])
        self.assertEqual(result["violations"][0]["path"], "server/api/login.proto")
        self.assertTrue(result["cross_project_dependencies"])

    def test_scope_guard_folds_parent_directory_traversal_before_matching(self) -> None:
        binding = workspace_subagents.create_bindings(_route_plan())[1]

        result = workspace_subagents.check_scope(
            binding,
            ["client/../server/api/login.proto"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["violations"][0]["path"], "server/api/login.proto")
        self.assertIn("denied scope server/api", result["violations"][0]["reason"])

    def test_scope_guard_normalizes_absolute_paths_under_project_root(self) -> None:
        binding = workspace_subagents.create_bindings(_route_plan())[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            absolute_path = root / "client" / "Assets" / "Scripts" / "Login.cs"

            result = workspace_subagents.check_scope(
                binding,
                [str(absolute_path)],
                project_root=root,
            )

        self.assertTrue(result["ok"], result["violations"])
        self.assertEqual(result["allowed_paths"], ["client/Assets/Scripts/Login.cs"])

    def test_scope_guard_rejects_absolute_paths_outside_project_root(self) -> None:
        binding = {"binding_id": "binding-root", "assigned_scope": ["."]}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            external_path = Path(temp_dir) / "outside" / "secret.txt"

            result = workspace_subagents.check_scope(
                binding,
                [str(external_path)],
                project_root=root,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["violations"][0]["path"].startswith("../"))
        self.assertEqual(result["violations"][0]["reason"], "outside assigned scope")

    def test_scope_guard_rejects_rooted_paths_before_normalizing(self) -> None:
        binding = {"binding_id": "binding-root", "assigned_scope": ["."]}
        result = workspace_subagents.check_scope(
            binding,
            ["/tmp/outside.txt", "\\tmp\\outside.txt"],
            project_root=PROJECT_ROOT,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(len(result["violations"]), 2)
        self.assertTrue(all(item["path"].startswith("../") for item in result["violations"]))

    def test_scope_guard_rejects_drive_relative_windows_paths(self) -> None:
        binding = {"binding_id": "binding-root", "assigned_scope": ["."]}

        result = workspace_subagents.check_scope(
            binding,
            ["C:", "C:secret.txt", "C:/outside/secret.txt"],
            project_root=PROJECT_ROOT,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(len(result["violations"]), 3)
        self.assertTrue(all(item["path"].startswith("../") for item in result["violations"]))

    def test_scope_guard_prefers_most_specific_denied_scope(self) -> None:
        binding = {
            "binding_id": "binding-docs-private",
            "assigned_scope": ["docs/private"],
            "denied_scope": ["docs", "docs/private/secret"],
        }

        result = workspace_subagents.check_scope(binding, ["docs/private/secret/plan.md"])

        self.assertFalse(result["ok"])
        self.assertEqual(result["violations"][0]["reason"], "matches denied scope docs/private/secret")

    def test_coordinator_summary_detects_same_file_conflict(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        summary = workspace_subagents.coordinator_summary(
            bindings,
            [
                {"binding_id": "binding-client-route", "touched_paths": ["shared/proto/login.proto"]},
                {"binding_id": "binding-server-route", "touched_paths": ["shared/proto/login.proto"]},
            ],
            {"gaps": []},
        )

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["conflicts"][0]["path"], "shared/proto/login.proto")
        self.assertTrue(summary["rollback_required"])

    def test_coordinator_summary_matches_artifact_by_project_id_and_requires_rollback_on_scope_violation(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        summary = workspace_subagents.coordinator_summary(
            bindings,
            [
                {
                    "project_id": "client-unity",
                    "domain": "game_client",
                    "assigned_scope": ["client/Assets/Scripts"],
                    "touched_paths": ["server/api/login.proto"],
                }
            ],
            {"gaps": []},
        )

        self.assertFalse(summary["ok"])
        self.assertTrue(summary["rollback_required"])
        self.assertEqual(summary["scope_guard"][0]["violations"][0]["path"], "server/api/login.proto")

    def test_coordinator_summary_blocks_failed_verification_without_gaps(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        summary = workspace_subagents.coordinator_summary(
            bindings,
            [],
            {
                "overall_status": "blocked",
                "results": [],
                "release_gates": {
                    "diagnostic_logging_disabled": {
                        "status": "manual_required",
                        "blocking": True,
                    }
                },
                "gaps": [],
            },
        )

        self.assertFalse(summary["ok"])
        self.assertTrue(summary["rollback_required"])
        self.assertTrue(summary["verification_gaps"])

    def test_coordinator_summary_rejects_unmatched_artifact_with_touched_paths(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())

        summary = workspace_subagents.coordinator_summary(
            bindings,
            [{"touched_paths": ["server/api/login.proto"]}],
            {"gaps": []},
        )

        self.assertFalse(summary["ok"])
        self.assertTrue(summary["rollback_required"])
        self.assertEqual(summary["artifact_gaps"][0]["type"], "artifact_attribution")

    def test_coordinator_summary_requires_specialist_checkpoints(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())

        summary = workspace_subagents.coordinator_summary(bindings, [], {"gaps": []})

        self.assertFalse(summary["ok"])
        self.assertTrue(summary["rollback_required"])
        missing = [item for item in summary["artifact_gaps"] if item["type"] == "missing_checkpoint"]
        self.assertEqual(
            {item["binding_id"] for item in missing},
            {"binding-client-route", "binding-server-route"},
        )

    def test_coordinator_summary_requires_complete_checkpoint_artifacts(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        server = next(item for item in bindings if item.get("project_id") == "server-game")

        summary = workspace_subagents.coordinator_summary(
            bindings,
            [{"binding_id": "binding-client-route"}, _artifact(server, ["server/api/login.proto"])],
            {"gaps": []},
        )

        missing = [item for item in summary["artifact_gaps"] if item["type"] == "missing_checkpoint"]
        self.assertFalse(summary["ok"])
        self.assertEqual({item["binding_id"] for item in missing}, {"binding-client-route"})

    def test_coordinator_summary_blocks_sensitive_artifact_output(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        client = next(item for item in bindings if item.get("project_id") == "client-unity")
        artifact = _artifact(client, ["client/Assets/Scripts/Login.cs"])
        artifact["summary"] = "password=abc def"

        summary = workspace_subagents.coordinator_summary(bindings, [artifact], {"gaps": []})

        sensitive = [item for item in summary["artifact_gaps"] if item["type"] == "sensitive_artifact_output"]
        self.assertFalse(summary["ok"])
        self.assertEqual(sensitive[0]["binding_id"], "binding-client-route")
        self.assertTrue(summary["rollback_required"])

    def test_coordinator_summary_blocks_preserved_sensitive_scan_report(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        client = next(item for item in bindings if item.get("project_id") == "client-unity")
        artifact = _artifact(client, ["client/Assets/Scripts/Login.cs"])
        artifact["summary"] = "password=[REDACTED]"
        artifact["_sensitive_scan"] = {
            "redacted": True,
            "blocked": False,
            "finding_count": 1,
            "categories": ["password"],
            "actions": ["redact"],
        }

        summary = workspace_subagents.coordinator_summary(bindings, [artifact], {"gaps": []})

        sensitive = [item for item in summary["artifact_gaps"] if item["type"] == "sensitive_artifact_output"]
        self.assertFalse(summary["ok"])
        self.assertEqual(sensitive[0]["scan"]["categories"], ["password"])
        self.assertTrue(summary["rollback_required"])

    def test_coordinator_summary_keeps_non_blocking_verification_gaps_as_warnings(self) -> None:
        bindings = workspace_subagents.create_bindings(_route_plan())
        client = next(item for item in bindings if item.get("project_id") == "client-unity")
        server = next(item for item in bindings if item.get("project_id") == "server-game")

        summary = workspace_subagents.coordinator_summary(
            bindings,
            [
                _artifact(client, ["client/Assets/Scripts/Login.cs"]),
                _artifact(server, ["server/api/login.proto"]),
            ],
            {"overall_status": "passed", "gaps": [{"reason": "optional docs check missing", "blocking": False}]},
        )

        self.assertTrue(summary["ok"], summary)
        self.assertFalse(summary["rollback_required"])
        self.assertEqual(summary["verification_gaps"], [])
        self.assertEqual(summary["verification_warnings"][0]["reason"], "optional docs check missing")

    def test_scope_check_rejects_full_bind_output(self) -> None:
        route_plan = _route_plan()
        bindings = workspace_subagents.create_bindings(route_plan)
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_file = Path(temp_dir) / "bindings.json"
            binding_file.write_text(json.dumps({"route_plan": route_plan, "bindings": bindings}), encoding="utf-8")
            args = argparse.Namespace(
                project_root=temp_dir,
                command="scope-check",
                binding_file=str(binding_file),
                touched_path=["server/api/login.proto"],
                artifact_file=[],
            )

            with self.assertRaises(ValueError):
                workspace_subagents.dispatch(args)

    def test_scope_check_rejects_route_plan_output(self) -> None:
        route_plan = _route_plan()
        with tempfile.TemporaryDirectory() as temp_dir:
            binding_file = Path(temp_dir) / "route.json"
            binding_file.write_text(json.dumps({"ok": True, "route_plan": route_plan}), encoding="utf-8")
            args = argparse.Namespace(
                project_root=temp_dir,
                command="scope-check",
                binding_file=str(binding_file),
                touched_path=["server/api/login.proto"],
                artifact_file=[],
            )

            with self.assertRaises(ValueError):
                workspace_subagents.dispatch(args)

    def test_child_route_is_not_denied_by_root_scope(self) -> None:
        bindings = workspace_subagents.create_bindings(_root_and_docs_route_plan())
        docs_binding = next(item for item in bindings if item.get("project_id") == "design-docs")
        result = workspace_subagents.check_scope(docs_binding, ["docs/guide.md"])

        self.assertTrue(result["ok"], result["violations"])
        self.assertNotIn(".", docs_binding.get("denied_scope", []))

    def test_nested_child_scope_wins_over_parent_denied_scope(self) -> None:
        bindings = workspace_subagents.create_bindings(_nested_route_plan())
        assets_binding = next(item for item in bindings if item.get("project_id") == "client-assets")

        result = workspace_subagents.check_scope(assets_binding, ["client/Assets/Textures/Hero.png"])

        self.assertTrue(result["ok"], result["violations"])
        self.assertEqual(result["allowed_paths"], ["client/Assets/Textures/Hero.png"])

    def test_read_json_list_accepts_harness_jsonl_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifacts.jsonl"
            path.write_text(
                json.dumps({"binding_id": "binding-client", "touched_paths": ["client/a.cs"]}) + "\n"
                + json.dumps({"binding_id": "binding-server", "touched_paths": ["server/a.go"]}) + "\n",
                encoding="utf-8",
            )

            items = workspace_subagents.read_json_list([str(path)])

        self.assertEqual(len(items), 2)
        self.assertEqual(items[1]["binding_id"], "binding-server")


def _route_plan() -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "login-contract",
        "route_plan_id": "route-login-contract",
        "mode": "cross_project_contract",
        "affected_projects": ["client-unity", "server-game"],
        "coordinator_required": True,
        "routes": [
            {
                "route_id": "client-route",
                "project_id": "client-unity",
                "domain": "game_client",
                "cwd": "client",
                "task_type": "contract",
                "assigned_scope": ["client/Assets/Scripts"],
                "rules": ["workspace/base", "game_client/unity"],
                "verification_profile_ids": ["client_quick"],
                "confidence": 0.8,
            },
            {
                "route_id": "server-route",
                "project_id": "server-game",
                "domain": "game_server",
                "cwd": "server",
                "task_type": "contract",
                "assigned_scope": ["server/api"],
                "rules": ["workspace/base", "game_server/base"],
                "verification_profile_ids": ["server_unit"],
                "confidence": 0.8,
            },
        ],
        "risk_level": "high",
        "confidence": 0.8,
        "reasons": ["test"],
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


def _root_and_docs_route_plan() -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "root-docs",
        "route_plan_id": "route-root-docs",
        "mode": "multi_project_parallel",
        "affected_projects": ["workspace-root", "design-docs"],
        "coordinator_required": True,
        "routes": [
            {
                "route_id": "root-route",
                "project_id": "workspace-root",
                "domain": "workspace_meta",
                "cwd": ".",
                "task_type": "implementation",
                "assigned_scope": ["."],
                "rules": ["workspace/base"],
                "verification_profile_ids": ["primary"],
                "confidence": 0.8,
            },
            {
                "route_id": "docs-route",
                "project_id": "design-docs",
                "domain": "design_docs",
                "cwd": "docs",
                "task_type": "docs",
                "assigned_scope": ["docs"],
                "rules": ["workspace/base", "docs/design"],
                "verification_profile_ids": ["primary"],
                "confidence": 0.8,
            },
        ],
        "risk_level": "medium",
        "confidence": 0.8,
        "reasons": ["test"],
    }


def _nested_route_plan() -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "nested",
        "route_plan_id": "route-nested",
        "mode": "multi_project_parallel",
        "affected_projects": ["client-unity", "client-assets"],
        "coordinator_required": True,
        "routes": [
            {
                "route_id": "client-route",
                "project_id": "client-unity",
                "domain": "game_client",
                "cwd": "client",
                "assigned_scope": ["client"],
            },
            {
                "route_id": "assets-route",
                "project_id": "client-assets",
                "domain": "art_pipeline",
                "cwd": "client/Assets",
                "assigned_scope": ["client/Assets"],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
