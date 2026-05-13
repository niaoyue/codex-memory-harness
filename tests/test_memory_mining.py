from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import context_builder  # noqa: E402
import memory_mining  # noqa: E402
from memory_store import MemoryStore  # noqa: E402


def restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


class MemoryMiningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        self.old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        (Path(self.temp_dir.name) / ".codex").mkdir()
        os.environ["CODEX_MEMORY_SCOPE"] = "project"
        os.environ["CODEX_MEMORY_CWD"] = self.temp_dir.name

    def tearDown(self) -> None:
        restore_env("CODEX_MEMORY_SCOPE", self.old_scope)
        restore_env("CODEX_MEMORY_CWD", self.old_cwd)
        self.temp_dir.cleanup()

    def _append_repeated_verification_events(self) -> None:
        for index in range(3):
            memory_mining.append_history_event(
                "after_tool",
                {
                    "task_id": "mine-task",
                    "session_id": f"session-{index}",
                    "project_id": "plugin-runtime",
                    "scope": "project",
                    "summary": "verification tests passed",
                    "command": "py -X utf8 -m unittest tests/test_memory_mining.py",
                    "ok": True,
                },
            )

    def test_mines_low_risk_repeated_events_into_accepted_context(self) -> None:
        self._append_repeated_verification_events()

        result = memory_mining.mine_candidates()
        accepted = memory_mining.accepted_context(
            project_id="plugin-runtime",
            scope="project",
            working_set=["tests/test_memory_mining.py"],
        )

        self.assertEqual(result["accepted"], 1)
        self.assertEqual(accepted[0]["status"], "accepted")
        self.assertEqual(accepted[0]["confidence"], "high")
        self.assertIn("tests/test_memory_mining.py", accepted[0]["statement"])

    def test_candidate_status_update_rewrites_accepted_context(self) -> None:
        self._append_repeated_verification_events()
        memory_mining.mine_candidates()
        candidate = memory_mining.accepted_context()[0]

        result = memory_mining.update_candidate(candidate["candidate_id"], "rejected")

        self.assertTrue(result["ok"])
        self.assertEqual(memory_mining.accepted_context(), [])
        rejected = memory_mining.list_candidates(status="rejected")["candidates"]
        self.assertEqual(rejected[0]["candidate_id"], candidate["candidate_id"])

    def test_context_pack_includes_accepted_learned_preferences(self) -> None:
        self._append_repeated_verification_events()
        memory_mining.mine_candidates()
        store = MemoryStore()
        store.upsert_task_state(
            "mine-task",
            {
                "objective": "run verification tests",
                "status": "open",
                "working_set": ["tests/test_memory_mining.py"],
                "metadata": {
                    "workspace_routing": {
                        "route_plan": {
                            "primary_project": "plugin-runtime",
                        }
                    }
                },
            },
        )

        pack = context_builder.ContextBuilder(memory_store=store).build_context_pack(
            task_id="mine-task",
            queries=[],
        )

        rendered = pack["rendered_context"]
        self.assertIn("## Learned Preferences", rendered)
        self.assertIn("tests/test_memory_mining.py", rendered)


if __name__ == "__main__":
    unittest.main()
