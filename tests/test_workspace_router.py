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

import workspace_router


class WorkspaceRouterTests(unittest.TestCase):
    def test_route_planner_routes_single_project_by_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")
            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "ui-fix",
                    "objective": "Fix login UI panel",
                    "working_set": ["client/Assets/Scripts/UI/LoginPanel.cs"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "single_project")
        self.assertEqual(plan["task_type"], "ui")
        self.assertEqual(plan["affected_projects"], ["unity-client"])
        self.assertEqual(plan["routes"][0]["domain"], "game_client")
        self.assertIn("client/Assets/Scripts/UI/LoginPanel.cs", plan["routes"][0]["assigned_scope"])
        self.assertIn("game_client/unity", plan["routes"][0]["rules"])
        self.assertIn("game_client/ui", plan["routes"][0]["rules"])

    def test_route_planner_marks_client_server_api_task_as_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")
            _write_text(root / "server" / "go.mod", "module sample\n")
            _mkdir(root / "server" / "api")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "login-contract",
                    "objective": "Update login API protocol for client and server",
                    "working_set": ["client/Assets/Scripts/Net/Login.cs", "server/api/login.proto"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "cross_project_contract")
        self.assertTrue(plan["coordinator_required"])
        self.assertEqual(set(plan["affected_projects"]), {"unity-client", "game_server-server"})
        self.assertEqual(plan["contracts"][0]["owner"], "coordinator")

    def test_route_planner_uses_explicit_config_project_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_config(root)
            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "explicit", "project_id": "configured-admin"},
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "single_project")
        self.assertEqual(plan["affected_projects"], ["configured-admin"])
        self.assertEqual(plan["routes"][0]["verification_profile_ids"], ["admin_lint"])
        self.assertEqual(plan["routes"][0]["verification_cwd"], ".")
        self.assertEqual(plan["verification_plan"][0]["verification_cwd"], ".")
        self.assertNotIn("read_scopes", plan["routes"][0]["memory_binding"])

    def test_configured_game_client_rules_get_task_rule_enrichment(self) -> None:
        rules = workspace_router.route_rules(
            {"domain": "game_client", "engine": "unity", "rules": ["workspace/base", "custom/client"]},
            "ui",
        )

        self.assertIn("custom/client", rules)
        self.assertIn("game_client/unity", rules)
        self.assertIn("game_client/ui", rules)

    def test_route_planner_honors_configured_diagnostic_logging_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "workspace": {"name": "configured"},
                    "diagnostic_logging": {
                        "default_allowed": True,
                        "release_must_be_disabled": True,
                        "allowed_scopes": ["state"],
                    },
                    "projects": [
                        {
                            "id": "configured-admin",
                            "path": "admin",
                            "cwd": "admin",
                            "verification_cwd": ".",
                            "domain": "backoffice_web",
                            "rules": ["workspace/base", "web/vue"],
                            "verification_profiles": {"ui": "admin_ui"},
                            "diagnostic_logging": {
                                "default_allowed": False,
                                "allowed_scopes": ["state"],
                            },
                        }
                    ],
                    "fallback": {"rules": ["workspace/generic"], "verification_profiles": ["primary"]},
                },
            )

            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "admin-ui", "objective": "Fix admin UI", "working_set": ["admin/src/App.vue"]},
                max_depth=1,
            )

        diagnostic = plan["routes"][0]["diagnostic_logging"]
        self.assertFalse(diagnostic["allowed"])
        self.assertEqual(diagnostic["required_scopes"], ["state"])

    def test_route_planner_matches_workspace_meta_root_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _write_text(root / "plugins" / "tool" / "script.py", "print('ok')\n")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "tooling",
                    "objective": "Fix tooling command",
                    "working_set": ["plugins/tool/script.py"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "single_project")
        self.assertEqual(plan["affected_projects"], ["workspace_meta-tooling"])
        self.assertEqual(plan["routes"][0]["assigned_scope"], ["plugins/tool/script.py"])

    def test_route_planner_preserves_dot_cwd_for_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _mkdir(root / "plugins")

            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "root-cwd", "objective": "Update tooling", "cwd": ".", "working_set": ["."]},
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "single_project")
        self.assertEqual(plan["affected_projects"], ["workspace_meta-tooling"])
        self.assertEqual(plan["routes"][0]["assigned_scope"], ["."])

    def test_release_path_marks_route_release_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _write_text(root / "release" / "build.ps1", "Write-Output ok\n")

            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "build-script", "objective": "Update script", "working_set": ["release/build.ps1"]},
                max_depth=1,
            )

        self.assertEqual(plan["task_type"], "release")
        self.assertEqual(plan["risk_level"], "release_blocking")
        self.assertFalse(plan["routes"][0]["diagnostic_logging"]["allowed"])

    def test_route_planner_selects_profile_for_task_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_config(root)

            quick_plan = workspace_router.build_route_plan(
                root,
                {"task_id": "admin-ui", "objective": "Fix admin UI", "working_set": ["admin/src/App.vue"]},
                max_depth=1,
            )
            release_plan = workspace_router.build_route_plan(
                root,
                {"task_id": "admin-release", "objective": "Update script", "working_set": ["admin/release/build.ps1"]},
                max_depth=1,
            )

        self.assertEqual(quick_plan["routes"][0]["verification_profile_ids"], ["admin_lint"])
        self.assertEqual(quick_plan["verification_profile_ids"], ["admin_lint"])
        self.assertEqual(release_plan["routes"][0]["verification_profile_ids"], ["admin_build"])
        self.assertEqual(release_plan["verification_profile_ids"], ["admin_build"])

    def test_route_planner_normalizes_absolute_paths_under_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")
            absolute_path = root / "client" / "Assets" / "Scripts" / "LoginPanel.cs"

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "absolute-path",
                    "objective": "Fix login UI",
                    "working_set": [str(absolute_path)],
                    "cwd": str(root / "client"),
                },
                max_depth=1,
            )

        self.assertEqual(plan["affected_projects"], ["unity-client"])
        self.assertEqual(plan["routes"][0]["assigned_scope"], ["client/Assets/Scripts/LoginPanel.cs"])

    def test_route_planner_does_not_assign_workspace_external_paths_to_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _mkdir(root / "plugins")
            external_path = Path(temp_dir) / "outside" / "secret.txt"

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "external-path",
                    "objective": "Inspect file",
                    "working_set": [
                        "../outside/secret.txt",
                        "/tmp/outside.txt",
                        "\\tmp\\outside.txt",
                        str(external_path),
                    ],
                },
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "unknown_low_confidence")
        self.assertEqual(plan["affected_projects"], [])
        self.assertEqual(plan["routes"], [])

    def test_route_planner_preserves_leading_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "escape", "working_set": ["../../client/Assets/Scripts/LoginPanel.cs"]},
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "unknown_low_confidence")
        self.assertEqual(plan["affected_projects"], [])

    def test_route_planner_normalizes_dot_prefixed_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "dot-relative-path",
                    "objective": "Fix login UI",
                    "working_set": [".\\client\\Assets\\Scripts\\LoginPanel.cs"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["affected_projects"], ["unity-client"])
        self.assertEqual(plan["routes"][0]["assigned_scope"], ["client/Assets/Scripts/LoginPanel.cs"])

    def test_child_cwd_does_not_score_workspace_meta_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _mkdir(root / "plugins")
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "client-cwd",
                    "objective": "Fix client script",
                    "cwd": str(root / "client"),
                },
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "single_project")
        self.assertEqual(plan["affected_projects"], ["unity-client"])

    def test_root_cwd_does_not_outrank_child_path_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _mkdir(root / "plugins")
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "root-cwd-child-path",
                    "objective": "Update login script",
                    "cwd": str(root),
                    "working_set": ["client/Assets/Scripts/LoginPanel.cs"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "single_project")
        self.assertEqual(plan["affected_projects"], ["unity-client"])

    def test_build_text_without_release_path_is_not_release_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "build-ui",
                    "objective": "Build login UI",
                    "working_set": ["client/Assets/Scripts/LoginPanel.cs"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["task_type"], "ui")
        self.assertEqual(plan["risk_level"], "medium")

    def test_task_type_uses_word_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _write_text(root / "plugins" / "tool" / "doctor.py", "print('ok')\n")

            review_plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "review-code",
                    "objective": "Review current code changes",
                    "working_set": ["plugins/tool/doctor.py"],
                },
                max_depth=1,
            )
            doctor_plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "doctor-command",
                    "objective": "Fix doctor command",
                    "working_set": ["plugins/tool/doctor.py"],
                },
                max_depth=1,
            )

        self.assertEqual(review_plan["task_type"], "implementation")
        self.assertEqual(doctor_plan["task_type"], "implementation")

    def test_changed_routing_includes_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _run_git(root, "init")
            _unity_project(root / "client")
            _write_text(root / "client" / "Assets" / "Scripts" / "NewPanel.cs", "class NewPanel {}\n")

            plan = workspace_router.build_route_plan(root, {"task_id": "changed"}, changed=True, max_depth=1)

        self.assertEqual(plan["affected_projects"], ["unity-client"])
        self.assertIn("client/Assets/Scripts/NewPanel.cs", plan["routes"][0]["assigned_scope"])

    def test_unknown_plan_uses_configured_fallback_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "workspace": {"name": "configured"},
                    "projects": [
                        {
                            "id": "configured-admin",
                            "path": "admin",
                            "cwd": "admin",
                            "domain": "backoffice_web",
                            "rules": ["workspace/base", "web/vue"],
                            "verification_profiles": {"quick": "admin_lint"},
                        }
                    ],
                    "fallback": {
                        "rules": ["workspace/generic"],
                        "verification_profiles": ["workspace_fallback"],
                    },
                },
            )

            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "unknown", "working_set": ["misc/new-file.txt"]},
                max_depth=1,
            )

        self.assertEqual(plan["mode"], "unknown_low_confidence")
        self.assertEqual(plan["verification_profile_ids"], ["workspace_fallback"])
        self.assertEqual(
            plan["verification_plan"],
            [
                {
                    "project_id": "workspace",
                    "domain": "workspace",
                    "cwd": ".",
                    "verification_profile_ids": ["workspace_fallback"],
                    "blocking": True,
                }
            ],
        )


def _unity_project(path: Path) -> None:
    _mkdir(path / "Assets")
    _mkdir(path / "ProjectSettings")
    _write_json(path / "Packages" / "manifest.json", {})


def _workspace_config(root: Path) -> None:
    _write_json(
        root / ".codex" / "harness" / "workspace-routing.json",
        {
            "version": 1,
            "workspace": {"name": "configured"},
            "projects": [
                {
                    "id": "configured-admin",
                    "path": "admin",
                    "cwd": "admin",
                    "verification_cwd": ".",
                    "domain": "backoffice_web",
                    "rules": ["workspace/base", "web/vue"],
                    "verification_profiles": {"quick": "admin_lint", "release": "admin_build"},
                    "memory_binding": {
                        "storage_scope": "project",
                        "semantic_scope": "project",
                        "project_id": "configured-admin",
                        "shared_memory_allowed": True,
                        "read_scopes": ["workspace"],
                    },
                }
            ],
            "fallback": {"rules": ["workspace/generic"], "verification_profiles": ["primary"]},
        },
    )


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


if __name__ == "__main__":
    unittest.main()
