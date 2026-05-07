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

import api_authority_router


class ApiAuthorityRouterTests(unittest.TestCase):
    def test_unity_plan_uses_official_docs_local_manifest_and_batchmode_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")

            plan = api_authority_router.build_authority_plan(
                root,
                {"task_id": "unity-api", "working_set": ["client/Assets/Login.cs"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        self.assertFalse(plan["network_used"])
        self.assertFalse(plan["auto_install_performed"])
        project = plan["projects"][0]
        self.assertEqual(project["ecosystem"], "unity")
        self.assertEqual(project["detected_version"], "2022.3.37f1")
        self.assertIn("UnityEngine", project["api_surfaces"])
        self.assertIn("Addressables", project["api_surfaces"])
        self.assertIn("TMP", project["api_surfaces"])
        self.assertIn("official_docs", project["authority_channels"])
        self.assertIn("client/ProjectSettings/ProjectVersion.txt", project["locators"])
        self.assertIn("unity_batchmode_compile", project["verification"])
        self.assertFalse(project["mcp"]["auto_install"])

    def test_openai_task_requires_official_docs_mcp_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {"objective": "Update OpenAI Responses API docs usage"},
                max_depth=0,
                installed_mcp_servers=["openai-docs"],
            )

        openai = next(item for item in plan["global_authorities"] if item["ecosystem"] == "openai")
        self.assertIn("official_mcp", openai["authority_channels"])
        self.assertEqual(openai["mcp"]["missing"], [])
        self.assertEqual(openai["mcp"]["installed"], ["openai-docs"])

    def test_openai_task_does_not_treat_generic_docs_mcp_as_official(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {"objective": "Update OpenAI Responses API docs usage"},
                max_depth=0,
                installed_mcp_servers=["docs"],
            )

        openai = next(item for item in plan["global_authorities"] if item["ecosystem"] == "openai")
        self.assertEqual(openai["mcp"]["missing"], ["openai-docs"])
        self.assertEqual(openai["mcp"]["installed"], [])
        self.assertEqual(openai["mcp"]["next_action"], "record_install_plan_and_use_fallback_authority")

    def test_text_only_task_preserves_global_authority_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {"text": "OpenAI Responses API"},
                max_depth=0,
                installed_mcp_servers=[],
            )

        ecosystems = [item["ecosystem"] for item in plan["global_authorities"]]
        self.assertIn("openai", ecosystems)

    def test_missing_context7_is_advisory_and_does_not_auto_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "admin" / "package.json", {"dependencies": {"vue": "^3.4.0"}})
            _mkdir(root / "admin" / "src" / "views")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["admin/src/views/App.vue"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["domain"], "backoffice_web")
        self.assertIn("context7", project["authority_channels"])
        self.assertEqual(project["mcp"]["missing"], ["context7"])
        self.assertTrue(project["mcp"]["optional"])
        self.assertFalse(project["mcp"]["auto_install"])
        self.assertIn("Missing MCP servers are advisory", " ".join(plan["recommendations"]))

    def test_web_plan_pins_dependency_versions_instead_of_app_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / "admin" / "package.json",
                {"version": "9.9.9", "dependencies": {"react": "18.3.1", "vite": "^5.0.0"}},
            )
            _mkdir(root / "admin" / "src" / "views")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["admin/src/views/App.tsx"]},
                max_depth=1,
                installed_mcp_servers=["context7"],
            )

        project = plan["projects"][0]
        self.assertEqual(project["detected_version"], "dependency_versions")
        self.assertEqual(project["dependency_versions"]["react"], "18.3.1")
        self.assertIn("react@18.3.1", project["api_surfaces"])
        self.assertNotEqual(project["detected_version"], "9.9.9")

    def test_web_plan_preserves_framework_version_before_dependency_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dependencies = {f"@a/pkg{i:02d}": "1.0.0" for i in range(20)}
            dependencies["react"] = "18.3.1"
            _write_json(root / "admin" / "package.json", {"dependencies": dependencies})
            _mkdir(root / "admin" / "src" / "views")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["admin/src/views/App.tsx"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["api_surfaces"][0], "react@18.3.1")
        self.assertIn("react@18.3.1", project["api_surfaces"])

    def test_next_web_plan_prioritizes_next_over_react_before_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dependencies = {f"@a/pkg{i:02d}": "1.0.0" for i in range(20)}
            dependencies.update({"next": "14.2.0", "react": "18.3.1", "react-dom": "18.3.1"})
            _write_json(root / "admin" / "package.json", {"dependencies": dependencies})
            _mkdir(root / "admin" / "src" / "views")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["admin/src/views/App.tsx"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["api_surfaces"][0], "next@14.2.0")
        self.assertIn("next@14.2.0", project["api_surfaces"])

    def test_next_prefixed_package_does_not_trigger_next_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dependencies = {"@nextui-org/react": "2.0.0", "react": "18.3.1", "vite": "5.0.0"}
            _write_json(root / "admin" / "package.json", {"dependencies": dependencies})
            _mkdir(root / "admin" / "src" / "views")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["admin/src/views/App.tsx"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["api_surfaces"][0], "react@18.3.1")
        self.assertNotIn("next", project["api_surfaces"])

    def test_sveltekit_scoped_package_is_prioritized_as_framework_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dependencies = {"@sveltejs/kit": "2.16.0", "vite": "6.0.0"}
            _write_json(root / "admin" / "package.json", {"dependencies": dependencies})
            _mkdir(root / "admin" / "src" / "views")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["admin/src/views/App.svelte"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["api_surfaces"][0], "@sveltejs/kit@2.16.0")
        self.assertNotEqual(project["api_surfaces"][0], "web")
        self.assertEqual(project["dependency_versions"]["@sveltejs/kit"], "2.16.0")

    def test_laya_game_client_uses_engine_dependency_version_not_app_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / "client" / "package.json",
                {"version": "9.9.9", "dependencies": {"layaair": "^2.13.0"}},
            )
            _mkdir(root / "client" / "src")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["client/src/Main.ts"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["ecosystem"], "laya")
        self.assertEqual(project["detected_version"], "layaair@^2.13.0")
        self.assertNotEqual(project["detected_version"], "9.9.9")
        self.assertIn("layaair@^2.13.0", project["api_surfaces"])
        self.assertEqual(project["engine_dependency_versions"], {"layaair": "^2.13.0"})

    def test_go_server_plan_includes_schema_and_contract_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "server" / "go.mod", "module sample\n\ngo 1.22\n")
            _mkdir(root / "server" / "cmd")
            _write_text(root / "server" / "api" / "login.proto", "syntax = \"proto3\";\n")

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["server/api/login.proto"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["ecosystem"], "go")
        self.assertEqual(project["detected_version"], "1.22")
        self.assertIn("server/api/login.proto", project["locators"])
        self.assertIn("schema", project["authority_channels"])
        self.assertIn("schema_codegen_or_contract_test", project["verification"])

    def test_configured_backoffice_service_uses_server_authority_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "admin-service" / "go.mod", "module admin\n\ngo 1.22\n")
            _write_text(root / "admin-service" / "api" / "admin.proto", "syntax = \"proto3\";\n")
            _write_json(
                root / ".codex" / "harness" / "workspace-routing.json",
                {
                    "version": 1,
                    "workspace": {"name": "sample"},
                    "projects": [
                        {
                            "id": "admin-service",
                            "path": "admin-service",
                            "cwd": "admin-service",
                            "domain": "backoffice_service",
                            "rules": [],
                            "verification_profiles": {},
                        }
                    ],
                    "fallback": {"rules": [], "verification_profiles": []},
                },
            )

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["admin-service/api/admin.proto"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["domain"], "backoffice_service")
        self.assertEqual(project["ecosystem"], "go")
        self.assertEqual(project["detected_version"], "1.22")
        self.assertIn("admin-service/api/admin.proto", project["locators"])
        self.assertIn("schema", project["authority_channels"])
        self.assertIn("schema_codegen_or_contract_test", project["verification"])

    def test_dotnet_server_plan_reads_multi_target_frameworks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "server" / "Game.Server.csproj",
                "<Project><PropertyGroup><TargetFrameworks>net8.0;net9.0</TargetFrameworks></PropertyGroup></Project>\n",
            )

            plan = api_authority_router.build_authority_plan(
                root,
                {"working_set": ["server/Game.Server.csproj"]},
                max_depth=1,
                installed_mcp_servers=[],
            )

        project = plan["projects"][0]
        self.assertEqual(project["ecosystem"], "dotnet")
        self.assertEqual(project["detected_version"], "net8.0;net9.0")
        self.assertIn("https://learn.microsoft.com/dotnet/api/", project["locators"])

    def test_unity_global_authority_is_kept_with_context7_or_mcp_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {"objective": "Check Unity Context7 MCP docs"},
                max_depth=0,
                installed_mcp_servers=[],
            )

        ecosystems = [item["ecosystem"] for item in plan["global_authorities"]]
        self.assertIn("context7", ecosystems)
        self.assertIn("mcp", ecosystems)
        self.assertIn("unity", ecosystems)

    def test_generic_tmp_text_does_not_trigger_unity_global_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {"objective": "Clean tmp/cache files"},
                max_depth=0,
                installed_mcp_servers=[],
            )

        ecosystems = [item["ecosystem"] for item in plan["global_authorities"]]
        self.assertNotIn("unity", ecosystems)

    def test_local_codex_memory_path_does_not_trigger_openai_global_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {
                    "objective": "Update Codex Memory Harness docs",
                    "working_set": ["plugins/codex-memory/scripts/hook_runner.py"],
                },
                max_depth=0,
                installed_mcp_servers=[],
            )

        self.assertEqual(plan["global_authorities"], [])
        self.assertFalse(plan["blocked"])

    def test_openai_codex_api_context_triggers_openai_global_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            _workspace_meta(root)

            plan = api_authority_router.build_authority_plan(
                root,
                {"objective": "Update OpenAI Codex API docs usage"},
                max_depth=0,
                installed_mcp_servers=[],
            )

        ecosystems = [item["ecosystem"] for item in plan["global_authorities"]]
        self.assertIn("openai", ecosystems)

    def test_cli_rejects_malformed_task_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_meta(root)
            task_file = root / "task.json"
            task_file.write_text("{bad json", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(PLUGIN_SCRIPTS_DIR / "api_authority_router.py"),
                    "--workspace-root",
                    str(root),
                    "--task-file",
                    str(task_file),
                    "plan",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("not valid JSON", payload["error"])

    def test_cli_outputs_readonly_json_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _workspace_meta(root)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(PLUGIN_SCRIPTS_DIR / "api_authority_router.py"),
                    "--workspace-root",
                    str(root),
                    "--objective",
                    "Check Context7 MCP plan",
                    "--mcp-server",
                    "context7",
                    "plan",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["command"], "plan")
        self.assertFalse(payload["network_used"])
        self.assertFalse(payload["auto_install_performed"])
        context7 = next(item for item in payload["global_authorities"] if item["ecosystem"] == "context7")
        self.assertEqual(context7["mcp"]["installed"], ["context7"])


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
