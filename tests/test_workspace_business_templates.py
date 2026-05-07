from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import workspace_business_templates
import workspace_template_commands
import workspace_router


class WorkspaceBusinessTemplateTests(unittest.TestCase):
    def test_template_builds_all_business_domains(self) -> None:
        cases = [
            ("game_server", {"language": "go"}),
            ("backoffice_web", {"framework": "vue"}),
            ("design_docs", {}),
            ("art_pipeline", {}),
        ]

        for domain, kwargs in cases:
            with self.subTest(domain=domain):
                template = workspace_business_templates.build_template(domain, domain, domain, **kwargs)

                self.assertTrue(template["commands"])
                self.assertTrue(template["profiles"])
                self.assertEqual(template["workspace_project"]["domain"], domain)
                self.assertEqual(template["workspace_project"]["cwd"], domain)

    def test_init_server_template_feeds_workspace_route_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / ".codex" / "harness" / "commands.json", {"version": 1, "commands": {}})
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "verification": {}})
            _write_text(root / "server" / "go.mod", "module sample\n")
            _mkdir(root / "server" / "cmd")

            result = workspace_business_templates.init_template(
                root,
                "game_server",
                "server",
                "server",
                overwrite=False,
                language="go",
            )
            commands = _read_json(root / ".codex" / "harness" / "commands.json")
            profile = _read_json(root / ".codex" / "harness" / "project_profile.json")
            workspace = _read_json(root / ".codex" / "harness" / "workspace-routing.json")
            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "server-release",
                    "objective": "Release game server",
                    "working_set": ["server/cmd/main.go"],
                },
                max_depth=1,
            )

        self.assertTrue(result["ok"])
        self.assertIn("server_go_unit", commands["commands"])
        self.assertEqual(profile["verification"]["server_release"], ["server_go_unit", "server_go_release"])
        self.assertEqual(workspace["projects"][0]["domain"], "game_server")
        self.assertEqual(plan["routes"][0]["verification_profile_ids"], ["server_release"])
        self.assertIn("server/go", plan["routes"][0]["rules"])

    def test_init_rejects_project_cwd_outside_workspace_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"

            with self.assertRaisesRegex(ValueError, "project_cwd must stay inside project_root"):
                workspace_business_templates.init_template(
                    root,
                    "game_server",
                    "../outside",
                    "server",
                    overwrite=False,
                    language="go",
                )

            self.assertFalse((root / ".codex" / "harness" / "commands.json").exists())
            self.assertFalse((root / ".codex" / "harness" / "project_profile.json").exists())
            self.assertFalse((root / ".codex" / "harness" / "workspace-routing.json").exists())

    def test_cli_default_ids_are_derived_from_project_cwd_for_same_domain_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "server-a")
            _mkdir(root / "server-b")

            for project_cwd in ("server-a", "server-b"):
                with mock.patch("sys.stdout", io.StringIO()):
                    workspace_business_templates.main_with_args(
                        [
                            "--project-root",
                            str(root),
                            "init",
                            "--domain",
                            "game_server",
                            "--project-cwd",
                            project_cwd,
                            "--language",
                            "go",
                        ]
                    )
            commands = _read_json(root / ".codex" / "harness" / "commands.json")
            profile = _read_json(root / ".codex" / "harness" / "project_profile.json")
            workspace = _read_json(root / ".codex" / "harness" / "workspace-routing.json")

        project_ids = [project["id"] for project in workspace["projects"]]
        self.assertEqual(project_ids, ["server-a-game", "server-b-game"])
        self.assertIn("server-a_go_unit", commands["commands"])
        self.assertIn("server-b_go_unit", commands["commands"])
        self.assertIn("server-a_release", profile["verification"])
        self.assertIn("server-b_release", profile["verification"])

    def test_cli_default_ids_use_full_project_cwd_when_leaf_repeats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "world" / "server")
            _mkdir(root / "battle" / "server")

            for project_cwd in ("world/server", "battle/server"):
                with mock.patch("sys.stdout", io.StringIO()):
                    workspace_business_templates.main_with_args(
                        [
                            "--project-root",
                            str(root),
                            "init",
                            "--domain",
                            "game_server",
                            "--project-cwd",
                            project_cwd,
                            "--language",
                            "go",
                        ]
                    )
            commands = _read_json(root / ".codex" / "harness" / "commands.json")
            workspace = _read_json(root / ".codex" / "harness" / "workspace-routing.json")

        project_ids = [project["id"] for project in workspace["projects"]]
        self.assertEqual(project_ids, ["server-world-server-game", "server-battle-server-game"])
        self.assertIn("server-world-server_go_unit", commands["commands"])
        self.assertIn("server-battle-server_go_unit", commands["commands"])

    def test_init_templates_preserve_existing_workspace_project_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "workspace": {"name": "sample"},
                    "projects": [
                        {
                            "id": "admin-web",
                            "path": "admin",
                            "cwd": "admin",
                            "domain": "backoffice_web",
                            "rules": ["custom"],
                            "verification_profiles": {"quick": "custom"},
                        }
                    ],
                    "fallback": {"rules": ["workspace/generic"], "verification_profiles": ["primary"]},
                },
            )

            result = workspace_business_templates.init_template(
                root,
                "backoffice_web",
                "admin",
                "admin",
                project_id="admin-web",
                framework="react",
                overwrite=False,
            )
            workspace = _read_json(root / ".codex" / "harness" / "workspace-routing.json")

        self.assertTrue(result["ok"])
        self.assertEqual(workspace["projects"][0]["rules"], ["custom"])
        self.assertIn({"action": "keep_workspace_project", "id": "admin-web"}, result["actions"])

    def test_init_template_deduplicates_existing_project_with_custom_id_by_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "workspace": {"name": "sample"},
                    "projects": [
                        {
                            "id": "backend",
                            "path": "server",
                            "cwd": "./server",
                            "domain": "game_server",
                            "rules": ["custom"],
                            "verification_profiles": {"quick": "backend_quick"},
                        }
                    ],
                    "fallback": {"rules": ["workspace/generic"], "verification_profiles": ["primary"]},
                },
            )

            result = workspace_business_templates.init_template(
                root,
                "game_server",
                "server",
                "server",
                language="go",
                overwrite=False,
            )
            workspace = _read_json(root / ".codex" / "harness" / "workspace-routing.json")

        self.assertEqual(len(workspace["projects"]), 1)
        self.assertEqual(workspace["projects"][0]["id"], "backend")
        self.assertEqual(workspace["projects"][0]["rules"], ["custom"])
        self.assertEqual(result["project_id"], "backend")
        self.assertIn({"action": "keep_workspace_project", "id": "backend"}, result["actions"])

    def test_overwrite_template_keeps_existing_custom_project_id_for_same_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "workspace": {"name": "sample"},
                    "projects": [
                        {
                            "id": "backend",
                            "path": "server",
                            "cwd": "server",
                            "domain": "game_server",
                            "rules": ["custom"],
                            "verification_profiles": {"quick": "backend_quick"},
                        }
                    ],
                    "fallback": {"rules": ["workspace/generic"], "verification_profiles": ["primary"]},
                },
            )

            result = workspace_business_templates.init_template(
                root,
                "game_server",
                "server",
                "server",
                language="go",
                overwrite=True,
            )
            workspace = _read_json(root / ".codex" / "harness" / "workspace-routing.json")

        self.assertEqual(len(workspace["projects"]), 1)
        self.assertEqual(workspace["projects"][0]["id"], "backend")
        self.assertEqual(workspace["projects"][0]["memory_binding"]["project_id"], "backend")
        self.assertIn("server/go", workspace["projects"][0]["rules"])
        self.assertEqual(result["project_id"], "backend")
        self.assertIn({"action": "write_workspace_project", "id": "backend"}, result["actions"])

    def test_python_checks_use_resolved_runtime(self) -> None:
        with mock.patch.object(
            workspace_template_commands,
            "select_mcp_python_runtime",
            return_value={"command": "py", "prefix_args": ["-3"]},
        ):
            template = workspace_business_templates.build_template("design_docs", "docs", "docs")

        argv = template["commands"]["docs_markdown_utf8"]["argv"]
        self.assertEqual(argv[:4], ["py", "-3", "-X", "utf8"])
        self.assertNotEqual(argv[0], "python")

    def test_node_templates_generate_windows_runnable_npm_argv(self) -> None:
        with mock.patch.object(workspace_template_commands.os, "name", "nt"):
            web = workspace_business_templates.build_template("backoffice_web", "admin", "admin", framework="vue")
            server = workspace_business_templates.build_template("game_server", "server", "server", language="node")

        self.assertEqual(web["commands"]["admin_lint"]["argv"][0], "npm.cmd")
        self.assertEqual(web["commands"]["admin_test"]["argv"][0], "npm.cmd")
        self.assertEqual(web["commands"]["admin_build"]["argv"][0], "npm.cmd")
        self.assertEqual(web["commands"]["admin_lint"]["argv"], ["npm.cmd", "run", "lint"])
        self.assertEqual(web["commands"]["admin_test"]["argv"], ["npm.cmd", "test"])
        self.assertEqual(web["commands"]["admin_build"]["argv"], ["npm.cmd", "run", "build"])
        self.assertEqual(server["commands"]["server_node_unit"]["argv"][0], "npm.cmd")
        self.assertEqual(server["commands"]["server_node_integration"]["argv"][0], "npm.cmd")
        self.assertEqual(server["commands"]["server_node_release"]["argv"][0], "npm.cmd")
        self.assertEqual(server["commands"]["server_node_unit"]["argv"], ["npm.cmd", "test"])
        self.assertEqual(server["commands"]["server_node_integration"]["argv"], ["npm.cmd", "run", "test:integration"])
        self.assertEqual(server["commands"]["server_node_release"]["argv"], ["npm.cmd", "run", "build"])

    def test_java_template_generates_windows_runnable_maven_argv(self) -> None:
        with mock.patch.object(workspace_template_commands.os, "name", "nt"):
            server = workspace_business_templates.build_template("game_server", "server", "server", language="java")

        self.assertEqual(server["commands"]["server_java_unit"]["argv"], ["mvn.cmd", "test"])
        self.assertEqual(server["commands"]["server_java_integration"]["argv"], ["mvn.cmd", "verify", "-DskipITs=false"])
        self.assertEqual(server["commands"]["server_java_release"]["argv"], ["mvn.cmd", "verify"])

    def test_generated_docs_link_check_skips_dependency_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "README.md", "[ok](guide.md)\n")
            _write_text(root / "guide.md", "# Guide\n")
            _write_text(root / "node_modules" / "package" / "README.md", "[bad](missing.md)\n")
            command = [sys.executable, "-X", "utf8", "-c", workspace_business_templates.DOCS_LINK_SCRIPT]

            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("local markdown links ok", completed.stdout)

    def test_generated_docs_link_check_accepts_parentheses_in_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "README.md", "[guide](foo_(bar).md)\n")
            _write_text(root / "foo_(bar).md", "# Guide\n")
            command = [sys.executable, "-X", "utf8", "-c", workspace_business_templates.DOCS_LINK_SCRIPT]

            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("local markdown links ok", completed.stdout)

    def test_generated_docs_link_check_accepts_link_titles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "README.md", '[guide](guide.md "Guide")\n')
            _write_text(root / "guide.md", "# Guide\n")
            command = [sys.executable, "-X", "utf8", "-c", workspace_business_templates.DOCS_LINK_SCRIPT]

            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("local markdown links ok", completed.stdout)

    def test_generated_art_release_check_skips_generated_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "Textures" / "hero.png", "asset")
            _write_text(root / "Library" / "placeholder.tmp", "")
            _write_text(root / "node_modules" / "package" / "placeholder.tmp", "")
            command = [sys.executable, "-X", "utf8", "-c", workspace_business_templates.ART_RELEASE_SCRIPT]

            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("asset release check ok: 1 files", completed.stdout)

    def test_generated_art_release_check_rejects_source_zero_byte_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "Textures" / "empty.png", "")
            command = [sys.executable, "-X", "utf8", "-c", workspace_business_templates.ART_RELEASE_SCRIPT]

            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("zero-byte asset files:", completed.stdout)

    def test_non_ascii_prefix_and_project_id_are_schema_safe(self) -> None:
        template = workspace_business_templates.build_template(
            "game_server",
            "server",
            "服务端",
            project_id="我的 服务器",
            language="go",
        )

        project_id = template["workspace_project"]["id"]
        self.assertRegex(project_id, r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
        self.assertTrue(all(ord(ch) < 128 for ch in project_id))
        self.assertTrue(project_id.startswith("server-game-"))


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
