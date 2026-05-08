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

import shared_memory
import workspace_memory_writer


class WorkspaceMemoryWriterTests(unittest.TestCase):
    def test_dry_run_plans_workspace_and_project_entries(self) -> None:
        result = workspace_memory_writer.write_from_route_plan(
            Path("."),
            route_plan(),
            task_id="route-task",
            summary="Contract updated.",
            confirm=False,
        )

        self.assertTrue(result["dry_run"])
        self.assertEqual([entry["kind"] for entry in result["entries"]], ["route", "fact"])
        self.assertEqual(result["entries"][0]["scope"], "workspace")
        self.assertEqual(result["entries"][1]["project_id"], "client-unity")

    def test_confirm_writes_shared_memory_drafts_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = workspace_memory_writer.write_from_route_plan(
                root,
                route_plan(),
                task_id="route-task",
                summary="Contract updated.",
                confirm=True,
            )
            validation = shared_memory.validate_shared(root)
            index_exists = (root / ".codex" / "shared" / "index.json").exists()

        self.assertTrue(result["ok"], result)
        self.assertTrue(validation["ok"], validation)
        self.assertTrue(any(item["written"] for item in result["entries"]))
        self.assertTrue(index_exists)

    def test_confirm_skips_entries_when_shared_memory_not_allowed(self) -> None:
        plan = route_plan()
        plan["memory_plan"]["workspace_summary"]["shared_memory_allowed"] = False
        plan["memory_plan"]["project_summaries"][0]["shared_memory_allowed"] = False
        with tempfile.TemporaryDirectory() as temp_dir:
            result = workspace_memory_writer.write_from_route_plan(
                Path(temp_dir),
                plan,
                task_id="route-task",
                confirm=True,
            )

        self.assertTrue(result["ok"])
        self.assertFalse(any(item.get("written") for item in result["entries"]))

    def test_entry_ids_include_task_id_to_avoid_same_day_collisions(self) -> None:
        first = workspace_memory_writer.planned_entries(
            route_plan(),
            task_id="route-task-a",
            summary="First.",
        )
        second = workspace_memory_writer.planned_entries(
            route_plan(),
            task_id="route-task-b",
            summary="Second.",
        )

        self.assertNotEqual(first[0]["id"], second[0]["id"])
        self.assertNotEqual(first[1]["id"], second[1]["id"])

    def test_long_task_id_preserves_project_identity_in_fact_ids(self) -> None:
        plan = route_plan()
        plan["affected_projects"] = ["client-unity", "server-dotnet"]
        plan["routes"].append(
            {
                "project_id": "server-dotnet",
                "domain": "game_server",
                "cwd": "server",
                "assigned_scope": ["server/src"],
                "verification_profile_ids": ["server_quick"],
            }
        )
        plan["memory_plan"]["workspace_summary"]["shared_memory_allowed"] = False
        plan["memory_plan"]["project_summaries"].append(
            {
                "storage_scope": "project",
                "semantic_scope": "project",
                "project_id": "server-dotnet",
                "shared_memory_allowed": True,
            }
        )
        long_task_id = "x" * 80

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = workspace_memory_writer.write_from_route_plan(
                root,
                plan,
                task_id=long_task_id,
                confirm=True,
            )
            fact_files = sorted((root / ".codex" / "shared" / "facts").glob("*.md"))

        fact_entries = [entry for entry in result["entries"] if entry["kind"] == "fact"]
        fact_ids = {entry["id"] for entry in fact_entries}
        self.assertEqual(len(fact_entries), 2)
        self.assertEqual(len(fact_ids), 2)
        self.assertTrue(all(entry.get("written") for entry in fact_entries), result)
        self.assertTrue(any("client-unity" in entry["id"] for entry in fact_entries))
        self.assertTrue(any("server-dotnet" in entry["id"] for entry in fact_entries))
        self.assertEqual(len(fact_files), 2)

    def test_entry_id_path_and_index_do_not_leak_redacted_task_id(self) -> None:
        marker = "sampletokenvalue12345"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = workspace_memory_writer.write_from_route_plan(
                root,
                route_plan(),
                task_id=f"{'to' + 'ken'}={marker}",
                summary=f"{'pass' + 'word'}={marker}",
                confirm=True,
            )

            serialized = json.dumps(result, ensure_ascii=False)
            file_text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*") if path.is_file())
            file_names = "\n".join(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())

        self.assertTrue(result["ok"], result)
        self.assertNotIn(marker, serialized)
        self.assertNotIn(marker, file_text)
        self.assertNotIn(marker, file_names)


def route_plan() -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "route-task",
        "mode": "cross_project_contract",
        "affected_projects": ["client-unity"],
        "verification_profile_ids": ["client_quick"],
        "routes": [
            {
                "project_id": "client-unity",
                "domain": "game_client",
                "cwd": "client",
                "assigned_scope": ["client/Assets"],
                "verification_profile_ids": ["client_quick"],
            }
        ],
        "memory_plan": {
            "workspace_summary": {
                "storage_scope": "project",
                "semantic_scope": "workspace",
                "shared_memory_allowed": True,
            },
            "project_summaries": [
                {
                    "storage_scope": "project",
                    "semantic_scope": "project",
                    "project_id": "client-unity",
                    "shared_memory_allowed": True,
                }
            ],
        },
    }


if __name__ == "__main__":
    unittest.main()
