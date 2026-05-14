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

import workspace_scanner


class WorkspaceScannerTests(unittest.TestCase):
    def test_scanner_detects_common_game_workspace_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "client-unity" / "Assets")
            _mkdir(root / "client-unity" / "ProjectSettings")
            _write_json(root / "client-unity" / "Packages" / "manifest.json", {})

            _mkdir(root / "client-laya" / ".laya")
            _mkdir(root / "client-laya" / "src")
            _mkdir(root / "client-laya" / "bin")

            _mkdir(root / "client-cocos" / "assets")
            _mkdir(root / "client-cocos" / "settings")
            _mkdir(root / "client-cocos" / "profiles")

            _write_text(root / "server" / "go.mod", "module sample\n")
            _mkdir(root / "server" / "cmd")

            _write_json(root / "admin" / "package.json", {"dependencies": {"vue": "latest"}})
            _mkdir(root / "admin" / "src" / "views")

            _write_text(root / "docs" / "feature.md", "# Feature\n")
            _mkdir(root / "art" / "Textures")

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        projects = {project["id"]: project for project in inventory["projects"]}
        domains = {project["domain"] for project in projects.values()}
        engines = {
            project["engine"]
            for project in projects.values()
            if project["domain"] == "game_client"
        }

        self.assertTrue(inventory["config_loaded"] is False)
        self.assertIn("game_server", domains)
        self.assertIn("backoffice_web", domains)
        self.assertIn("design_docs", domains)
        self.assertIn("art_pipeline", domains)
        self.assertEqual(engines, {"unity", "laya", "cocos"})

    def test_explicit_workspace_config_is_loaded_before_scanner_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            harness_dir = root / ".codex" / "harness"
            _write_json(
                harness_dir / "workspace-routing.json",
                {
                    "version": 1,
                    "workspace": {"name": "configured-workspace"},
                    "projects": [
                        {
                            "id": "configured-client",
                            "path": "./client",
                            "cwd": "client/.",
                            "verification_cwd": ".",
                            "domain": "game_client",
                            "engine": "unity",
                            "rules": ["workspace/base", "game_client/unity"],
                            "verification_profiles": {"quick": "client_quick"},
                            "memory_binding": {
                                "storage_scope": "project",
                                "semantic_scope": "project",
                                "project_id": "configured-client",
                                "shared_memory_allowed": True,
                                "read_scopes": ["workspace"],
                            },
                        }
                    ],
                    "fallback": {
                        "rules": ["workspace/generic"],
                        "verification_profiles": ["primary"],
                    },
                },
            )
            _mkdir(root / "client" / "Assets")
            _mkdir(root / "client" / "ProjectSettings")

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        self.assertTrue(inventory["config_loaded"])
        self.assertEqual(inventory["workspace"]["name"], "configured-workspace")
        projects = {project["id"]: project for project in inventory["projects"]}
        self.assertIn("configured-client", projects)
        self.assertEqual(projects["configured-client"]["source"], "explicit_config")
        self.assertEqual(projects["configured-client"]["path"], "client")
        self.assertEqual(projects["configured-client"]["cwd"], "client")
        self.assertEqual(projects["configured-client"]["verification_cwd"], ".")
        self.assertEqual(len([item for item in projects.values() if item["cwd"] == "client"]), 1)
        self.assertNotIn("read_scopes", projects["configured-client"]["memory_binding"])

    def test_explicit_workspace_config_rejects_paths_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            outside = Path(temp_dir) / "shared"
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "projects": [
                        {"id": "outside-relative", "path": "../shared", "cwd": "../shared", "domain": "unknown"},
                        {"id": "outside-absolute", "path": str(outside), "cwd": str(outside), "domain": "unknown"},
                    ],
                },
            )

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        project_ids = {project["id"] for project in inventory["projects"]}
        self.assertNotIn("outside-relative", project_ids)
        self.assertNotIn("outside-absolute", project_ids)

    def test_explicit_workspace_config_rejects_verification_cwd_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            outside = Path(temp_dir) / "shared"
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "projects": [
                        {
                            "id": "outside-verification-relative",
                            "path": "client",
                            "cwd": "client",
                            "verification_cwd": "../shared",
                            "domain": "game_client",
                        },
                        {
                            "id": "outside-verification-absolute",
                            "path": "server",
                            "cwd": "server",
                            "verification_cwd": str(outside),
                            "domain": "game_server",
                        },
                    ],
                },
            )

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        project_ids = {project["id"] for project in inventory["projects"]}
        self.assertNotIn("outside-verification-relative", project_ids)
        self.assertNotIn("outside-verification-absolute", project_ids)

    def test_scanner_detects_workspace_meta_root_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _mkdir(root / "plugins")

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        projects = {project["id"]: project for project in inventory["projects"]}
        self.assertIn("workspace_meta-tooling", projects)
        self.assertEqual(projects["workspace_meta-tooling"]["cwd"], ".")

    def test_root_workspace_meta_wins_over_root_ci_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "tooling"
            _write_text(root / "README.md", "# Tooling\n")
            _write_text(root / "pyproject.toml", "[project]\nname = \"tooling\"\n")
            _mkdir(root / "plugins")
            _mkdir(root / ".github")

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        root_project = next(project for project in inventory["projects"] if project["cwd"] == ".")
        self.assertEqual(root_project["domain"], "workspace_meta")

    def test_root_business_project_wins_over_workspace_meta_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "client"
            _write_text(root / "README.md", "# Client\n")
            _write_text(root / "AGENTS.md", "# Agents\n")
            _mkdir(root / "Assets")
            _mkdir(root / "ProjectSettings")
            _write_json(root / "Packages" / "manifest.json", {})

            inventory = workspace_scanner.scan_workspace(root, max_depth=0)

        root_project = next(project for project in inventory["projects"] if project["cwd"] == ".")
        self.assertEqual(root_project["domain"], "game_client")
        self.assertEqual(root_project["engine"], "unity")

    def test_plain_src_bin_directory_is_not_classified_as_laya(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "tool" / "src")
            _mkdir(root / "tool" / "bin")
            _write_json(
                root / "tool" / "package.json",
                {"name": "playable-tools", "description": "build playable ads", "dependencies": {"vite": "latest"}},
            )

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        self.assertFalse(any(project.get("engine") == "laya" for project in inventory["projects"]))

    def test_laya_dependency_metadata_is_detected_without_dot_laya(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "client" / "src")
            _write_json(root / "client" / "package.json", {"dependencies": {"layaair": "^2.13.0"}})

            inventory = workspace_scanner.scan_workspace(root, max_depth=1)

        projects = {project["id"]: project for project in inventory["projects"]}
        self.assertEqual(projects["laya-client"]["domain"], "game_client")
        self.assertEqual(projects["laya-client"]["engine"], "laya")

    def test_launcher_exposes_workspace_dispatcher(self) -> None:
        launcher = (PLUGIN_SCRIPTS_DIR / "codexm.ps1").read_text(encoding="utf-8")
        workspace_helper = (PLUGIN_SCRIPTS_DIR / "codexm_workspace.ps1").read_text(encoding="utf-8")
        dispatch = launcher + "\n" + workspace_helper

        self.assertIn("function Invoke-WorkspaceCommand", workspace_helper)
        self.assertIn('"workspace"', launcher)
        self.assertIn("workspace_scanner.py", dispatch)
        self.assertIn("workspace_router.py", dispatch)
        self.assertIn("workspace_verifier.py", dispatch)
        self.assertIn("workspace_subagents.py", dispatch)

    def test_cli_accepts_max_depth_after_workspace_subcommands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "client" / "Assets")
            _mkdir(root / "client" / "ProjectSettings")
            for command in ("scan", "doctor"):
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-X",
                        "utf8",
                        str(PLUGIN_SCRIPTS_DIR / "workspace_scanner.py"),
                        "--workspace-root",
                        str(root),
                        command,
                        "--max-depth",
                        "0",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["mode"], command)
                self.assertEqual(payload["inventory"]["projects"], [])


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
