from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def _append_repeated_events_for_command(
        self,
        command: str,
        *,
        project_id: str = "plugin-runtime",
        ok: bool = True,
    ) -> None:
        for index in range(3):
            memory_mining.append_history_event(
                "after_tool",
                {
                    "task_id": f"mine-task-{index}",
                    "session_id": f"session-{index}-{command}",
                    "project_id": project_id,
                    "scope": "project",
                    "summary": "verification tests passed" if ok else "verification tests failed",
                    "command": command,
                    "ok": ok,
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

    def test_failed_repeated_events_are_not_auto_promoted(self) -> None:
        for index in range(3):
            memory_mining.append_history_event(
                "after_tool",
                {
                    "task_id": "mine-task",
                    "session_id": f"session-{index}",
                    "project_id": "plugin-runtime",
                    "scope": "project",
                    "summary": "verification tests failed",
                    "command": "py -X utf8 -m unittest tests/test_memory_mining.py",
                    "ok": False,
                },
            )

        result = memory_mining.mine_candidates()
        candidates = memory_mining.list_candidates()["candidates"]

        self.assertEqual(result["accepted"], 0)
        self.assertEqual(candidates[0]["status"], "needs_review")
        self.assertFalse(candidates[0]["auto_promoted"])
        self.assertEqual(candidates[0]["successful_outcome_count"], 0)
        self.assertEqual(candidates[0]["contradiction_count"], 3)

    def test_candidate_status_update_rewrites_accepted_context(self) -> None:
        self._append_repeated_verification_events()
        memory_mining.mine_candidates()
        candidate = memory_mining.accepted_context()[0]

        result = memory_mining.update_candidate(candidate["candidate_id"], "rejected")

        self.assertTrue(result["ok"])
        self.assertEqual(memory_mining.accepted_context(), [])
        rejected = memory_mining.list_candidates(status="rejected")["candidates"]
        self.assertEqual(rejected[0]["candidate_id"], candidate["candidate_id"])

    def test_recent_filter_and_show_candidate_match_cli_contract(self) -> None:
        self._append_repeated_verification_events()
        paths = memory_mining.history_paths()
        events = memory_mining.read_jsonl(paths["events"])
        events[0]["created_at"] = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        memory_mining.write_jsonl(paths["events"], events)

        result = memory_mining.mine_candidates(recent="90d")
        candidate = memory_mining.list_candidates()["candidates"][0]
        shown = memory_mining.show_candidate(candidate["candidate_id"])

        self.assertEqual(result["events"], 2)
        self.assertEqual(result["total_events"], 3)
        self.assertEqual(shown["candidate"]["candidate_id"], candidate["candidate_id"])
        self.assertFalse(memory_mining.show_candidate("missing")["ok"])

    def test_recent_mining_preserves_existing_accepted_candidates(self) -> None:
        self._append_repeated_events_for_command("py -X utf8 -m unittest tests/test_old_memory.py")
        memory_mining.mine_candidates()
        old_accepted_id = memory_mining.accepted_context()[0]["candidate_id"]
        paths = memory_mining.history_paths()
        events = memory_mining.read_jsonl(paths["events"])
        for event in events:
            event["created_at"] = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        memory_mining.write_jsonl(paths["events"], events)

        self._append_repeated_events_for_command("py -X utf8 -m unittest tests/test_memory_mining.py")
        result = memory_mining.mine_candidates(recent="90d")
        accepted_ids = {item["candidate_id"] for item in memory_mining.read_jsonl(paths["accepted"])}

        self.assertEqual(result["mined_candidates"], 1)
        self.assertEqual(result["accepted"], 2)
        self.assertIn(old_accepted_id, accepted_ids)

    def test_recent_mining_downgrades_candidate_with_recent_failures(self) -> None:
        command = "py -X utf8 -m unittest tests/test_memory_mining.py"
        self._append_repeated_events_for_command(command)
        memory_mining.mine_candidates()
        paths = memory_mining.history_paths()
        events = memory_mining.read_jsonl(paths["events"])
        for event in events:
            event["created_at"] = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        memory_mining.write_jsonl(paths["events"], events)

        self._append_repeated_events_for_command(command, ok=False)
        result = memory_mining.mine_candidates(recent="90d")
        candidates = memory_mining.list_candidates()["candidates"]

        self.assertEqual(result["mined_candidates"], 1)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(candidates[0]["status"], "needs_review")
        self.assertEqual(candidates[0]["contradiction_count"], 3)

    def test_recent_mining_preserves_manual_rejection(self) -> None:
        command = "py -X utf8 -m unittest tests/test_memory_mining.py"
        self._append_repeated_events_for_command(command)
        memory_mining.mine_candidates()
        paths = memory_mining.history_paths()
        candidate_id = memory_mining.list_candidates()["candidates"][0]["candidate_id"]
        memory_mining.update_candidate(candidate_id, "rejected")
        events = memory_mining.read_jsonl(paths["events"])
        for event in events:
            event["created_at"] = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        memory_mining.write_jsonl(paths["events"], events)

        self._append_repeated_events_for_command(command)
        result = memory_mining.mine_candidates(recent="90d")
        candidate = memory_mining.show_candidate(candidate_id)["candidate"]

        self.assertEqual(result["mined_candidates"], 1)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(candidate["status"], "rejected")
        self.assertEqual(memory_mining.accepted_context(), [])

    def test_full_mining_preserves_manual_rejection(self) -> None:
        command = "py -X utf8 -m unittest tests/test_memory_mining.py"
        self._append_repeated_events_for_command(command)
        memory_mining.mine_candidates()
        candidate_id = memory_mining.list_candidates()["candidates"][0]["candidate_id"]
        memory_mining.update_candidate(candidate_id, "rejected")

        result = memory_mining.mine_candidates()
        candidate = memory_mining.show_candidate(candidate_id)["candidate"]

        self.assertEqual(result["mined_candidates"], 1)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(candidate["status"], "rejected")
        self.assertEqual(memory_mining.accepted_context(), [])

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
