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


class WorkspaceBusinessTemplateRegressionTests(unittest.TestCase):
    def test_init_rejects_normalized_project_id_collision_for_distinct_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "server a")
            _mkdir(root / "server-a")
            workspace_business_templates.init_template(root, "game_server", "server a", "", overwrite=False, language="go")

            with self.assertRaisesRegex(ValueError, "command id collision"):
                workspace_business_templates.init_template(root, "game_server", "server-a", "", overwrite=False, language="go")

    def test_init_rejects_profile_prefix_collision_for_distinct_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "server-a")
            _mkdir(root / "server-b")
            workspace_business_templates.init_template(root, "game_server", "server-a", "server", overwrite=False, language="go")

            with self.assertRaisesRegex(ValueError, "command id collision"):
                workspace_business_templates.init_template(
                    root,
                    "game_server",
                    "server-b",
                    "server",
                    overwrite=False,
                    project_id="server-b-game",
                    language="go",
                )

    def test_cli_default_ids_are_unique_for_localized_project_cwds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _mkdir(root / "服务端一")
            _mkdir(root / "服务端二")

            for project_cwd in ("服务端一", "服务端二"):
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
        self.assertEqual(len(project_ids), 2)
        self.assertEqual(len(set(project_ids)), 2)
        self.assertEqual(len(commands["commands"]), 6)

    def test_generated_docs_link_check_accepts_angle_wrapped_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "README.md", "[guide](<guide.md#intro>)\n")
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

    def test_generated_docs_link_check_preserves_angle_wrapped_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "README.md", "[guide](<my guide.md>)\n")
            _write_text(root / "my guide.md", "# Guide\n")
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

    def test_generated_docs_link_check_skips_codex_runtime_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "README.md", "[ok](guide.md)\n")
            _write_text(root / "guide.md", "# Guide\n")
            _write_text(root / ".codex" / "memories" / "README.md", "[bad](missing.md)\n")
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


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
