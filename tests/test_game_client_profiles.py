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

import game_client_profiles
import workspace_router


class GameClientProfileTests(unittest.TestCase):
    def test_init_profiles_writes_unity_profiles_without_overwriting_existing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / ".codex" / "harness" / "commands.json", {"version": 1, "commands": {"keep": "ok"}})
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "verification": {}})

            result = game_client_profiles.init_profiles(root, "unity", "client", "client", overwrite=False)
            commands = _read_json(root / ".codex" / "harness" / "commands.json")
            profile = _read_json(root / ".codex" / "harness" / "project_profile.json")
            game_client = _read_json(root / ".codex" / "harness" / "game-client.json")

        self.assertTrue(result["ok"])
        self.assertIn("client_unity_quick", commands["commands"])
        self.assertNotIn("command", commands["commands"]["client_unity_quick"])
        self.assertEqual(commands["commands"]["keep"], "ok")
        self.assertEqual(profile["verification"]["client_release"], ["client_unity_release"])
        self.assertEqual(game_client["engine"], "unity")
        self.assertFalse(game_client["ai_diagnostics"]["enabled_by_default"])

    def test_template_uses_engine_specific_env_var(self) -> None:
        template = game_client_profiles.build_template("cocos", "client-cocos", "client")
        argv = template["commands"]["client_cocos_release"]["argv"]

        self.assertTrue(any("COCOS_CREATOR_EXE" in part for part in argv))
        self.assertIn("client_release", template["profiles"])

    def test_generated_script_uses_command_cwd_as_project_root(self) -> None:
        template = game_client_profiles.build_template("unity", "Client's Build", "client")
        command = template["commands"]["client_unity_quick"]
        script = command["argv"][-1]

        self.assertEqual(command["cwd"], "Client's Build")
        self.assertIn("Resolve-Path -LiteralPath '.'", script)
        self.assertNotIn("Client's Build", script)

    def test_init_profiles_feed_scanner_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")
            game_client_profiles.init_profiles(root, "unity", "client", "client", overwrite=False)

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "client-release",
                    "objective": "Release unity client",
                    "working_set": ["client/Assets/Scripts/Login.cs"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["routes"][0]["verification_profile_ids"], ["client_release"])
        self.assertEqual(plan["verification_plan"][0]["verification_profile_ids"], ["client_release"])

    def test_init_profiles_merge_into_configured_workspace_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")
            _workspace_client_config(root)
            game_client_profiles.init_profiles(root, "unity", "client", "client", overwrite=False)

            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "client-release", "objective": "Release unity client", "working_set": ["client/Assets/Login.cs"]},
                max_depth=1,
            )

        self.assertEqual(plan["routes"][0]["verification_profile_ids"], ["client_release"])

    def test_parent_workspace_ignores_child_local_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _unity_project(root / "client")
            game_client_profiles.init_profiles(root / "client", "unity", ".", "client", overwrite=False)

            plan = workspace_router.build_route_plan(
                root,
                {"task_id": "client-release", "objective": "Release unity client", "working_set": ["client/Assets/Login.cs"]},
                max_depth=1,
            )

        self.assertEqual(plan["routes"][0]["verification_profile_ids"], ["primary"])


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _unity_project(path: Path) -> None:
    (path / "Assets").mkdir(parents=True, exist_ok=True)
    (path / "ProjectSettings").mkdir(parents=True, exist_ok=True)
    _write_json(path / "Packages" / "manifest.json", {})


def _workspace_client_config(root: Path) -> None:
    _write_json(
        root / ".codex" / "harness" / "workspace-routing.json",
        {
            "version": 1,
            "workspace": {"name": "game"},
            "projects": [{"id": "client", "path": "client", "cwd": "client", "domain": "game_client", "engine": "unity"}],
        },
    )


if __name__ == "__main__":
    unittest.main()
