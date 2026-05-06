from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import api_authority_router


class ApiAuthorityRouterPathTests(unittest.TestCase):
    def test_absolute_working_set_prefers_child_project_over_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")
            absolute = root / "client" / "Assets" / "Login.cs"

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": [str(absolute)]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual([(item["cwd"], item["ecosystem"]) for item in plan["projects"]], [("client", "unity")])

    def test_rooted_without_drive_working_set_is_external(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")

            for working_path in (r"\client\Assets\Login.cs", "/client/Assets/Login.cs"):
                with self.subTest(working_path=working_path):
                    plan = api_authority_router.build_authority_plan(
                        root,
                        {"working_set": [working_path]},
                        max_depth=1,
                        installed_mcp_servers=[],
                    )

                    self.assertEqual(plan["projects"], [])
                    self.assertEqual(len(plan["unmatched_working_set"]), 1)
                    self.assertTrue(plan["blocked"])

    def test_drive_relative_working_set_is_external(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["C:outside/foo.cs"]},
                max_depth=0,
                installed_mcp_servers=[],
            )

        self.assertEqual(plan["projects"], [])
        self.assertEqual(len(plan["unmatched_working_set"]), 1)
        self.assertTrue(plan["blocked"])

    def test_dot_relative_working_set_prefers_child_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")

            for working_path in (r".\client\Assets\Login.cs", "./client/Assets/Login.cs"):
                with self.subTest(working_path=working_path):
                    plan = api_authority_router.build_authority_plan(
                        root,
                        {"working_set": [working_path]},
                        max_depth=1,
                        installed_mcp_servers=[],
                    )

                    self.assertEqual(
                        [(item["cwd"], item["ecosystem"]) for item in plan["projects"]],
                        [("client", "unity")],
                    )

    def test_working_set_matches_child_project_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "Client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["client/Assets/Login.cs"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual([(item["cwd"], item["ecosystem"]) for item in plan["projects"]], [("Client", "unity")])

    def test_parent_segments_are_collapsed_before_project_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")
            _write_text(root / "server" / "Game.Server.csproj", "<Project />\n")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["client/../server/Game.Server.csproj"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual([(item["cwd"], item["ecosystem"]) for item in plan["projects"]], [("server", "dotnet")])

    def test_mixed_root_and_child_working_set_keeps_both_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["plugins/tool.py", "client/Assets/Login.cs"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        routes = [(item["cwd"], item["ecosystem"]) for item in plan["projects"]]
        self.assertEqual(routes, [(".", "python_tooling"), ("client", "unity")])
        self.assertFalse(plan["blocked"])

    def test_unmatched_working_set_does_not_fall_back_to_all_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            outside = Path(temp_dir).parent / "outside" / "Login.cs"
            _workspace_meta(root)
            _unity_project(root / "client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": [str(outside)]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual(plan["projects"], [])
        self.assertEqual(len(plan["unmatched_working_set"]), 1)
        self.assertTrue(plan["blocked"])

    def test_mixed_unmatched_working_set_blocks_even_when_some_projects_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            outside = Path(temp_dir).parent / "outside" / "Login.cs"
            _workspace_meta(root)
            _unity_project(root / "client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["client/Assets/Login.cs", str(outside)]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual([(item["cwd"], item["ecosystem"]) for item in plan["projects"]], [("client", "unity")])
        self.assertEqual(len(plan["unmatched_working_set"]), 1)
        self.assertTrue(plan["blocked"])

    def test_unknown_explicit_project_id_blocks_without_fallback_to_all_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"project_id": "missing-project"},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual(plan["projects"], [])
        self.assertEqual(plan["unmatched_project_id"], "missing-project")
        self.assertTrue(plan["blocked"])

    def test_plural_project_ids_select_only_requested_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"project_ids": ["unity-client"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        routes = [(item["project_id"], item["cwd"]) for item in plan["projects"]]
        self.assertEqual(routes, [("unity-client", "client")])
        self.assertFalse(plan["blocked"])

    def test_unknown_plural_project_id_blocks_without_fallback_to_all_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)
            _unity_project(root / "client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"affected_projects": ["unity-client", "missing-project"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual(plan["projects"], [])
        self.assertEqual(plan["unmatched_project_id"], "missing-project")
        self.assertTrue(plan["blocked"])

    def test_explicit_project_id_blocks_when_working_set_matches_different_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _unity_project(root / "client")
            _write_text(root / "server" / "go.mod", "module sample\n\ngo 1.22\n")

            plan = api_authority_router.build_authority_plan(
                root,
                {"project_id": "unity-client", "working_set": ["server/go.mod"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertEqual([(item["project_id"], item["cwd"]) for item in plan["projects"]], [("unity-client", "client")])
        self.assertEqual(plan["unmatched_working_set"], ["server/go.mod"])
        self.assertTrue(plan["blocked"])


def _unity_project(path: Path) -> None:
    _mkdir(path / "Assets")
    _mkdir(path / "ProjectSettings")
    _write_text(path / "ProjectSettings" / "ProjectVersion.txt", "m_EditorVersion: 2022.3.37f1\n")
    _write_json(
        path / "Packages" / "manifest.json",
        {"dependencies": {"com.unity.addressables": "1.21.21", "com.unity.textmeshpro": "3.0.6"}},
    )


def _workspace_meta(path: Path) -> None:
    _write_text(path / "README.md", "# Tooling\n")
    _write_text(path / "pyproject.toml", "[project]\nname = \"tooling\"\nversion = \"0.1.0\"\n")
    _mkdir(path / "plugins")


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
