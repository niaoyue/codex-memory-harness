from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"

for path in (PLUGIN_SCRIPTS_DIR, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import hook_runner
import memory_store
import unfinished_task_summary
from workspace_test_helpers import MemoryEnv


CANONICAL_TASK_LIST = Path(".codex/specs/backlog-governance/tasks.md")
LEGACY_TASK_LIST = Path("docs/codex-memory-plugin-task-list.md")

TASK_LIST = """# Tasks

| ID | 阶段 | 任务 | 产出物 | 依赖 | 状态 |
|---|---|---|---|---|---|
| T01 | 1 | Done task | `done.md` | 无 | done |
| T02 | 1 | Build progress reporter | `report.md` | T01 | todo |
| T03 | 1 | Wire response hook | hook result includes unfinished task summary | T02 | doing |
| T04 | 1 | Blocked integration | waiting for host API | T03 | blocked |

## 3. 当前推荐执行步

- Step 42 待办：实现 T02。未完成 Task 汇总必须输出状态、最近进展、剩余验收、阻塞点、下一步和证据来源。
- Step 43 进行中：实现 T03。当前已完成 parser，剩余 before_response 接入。
"""

LEGACY_ONLY_TASK_LIST = """# Legacy Tasks

| ID | 阶段 | 任务 | 产出物 | 依赖 | 状态 |
|---|---|---|---|---|---|
| T90 | 1 | Legacy fallback task | `legacy.md` | 无 | todo |
"""

TASK_LIST_WITH_PROGRESS = TASK_LIST + """

## Current Progress

### T02 - Build progress reporter

- status: todo
- recent_checkpoint_or_update: 2026-05-13T09:57:14+00:00
- completed_acceptance: parser reads canonical task rows
- remaining_acceptance: before_response should include progress fields
- blockers: waiting for final review
- next_step: run targeted tests
- evidence_sources: tests/test_unfinished_task_summary.py
"""


def write_task_list(project_root: Path, relative_path: Path, content: str = TASK_LIST) -> Path:
    task_list = project_root / relative_path
    task_list.parent.mkdir(parents=True, exist_ok=True)
    task_list.write_text(content, encoding="utf-8")
    return task_list


class UnfinishedTaskSummaryTests(unittest.TestCase):
    def test_build_unfinished_progress_summary_uses_evidence_and_unknowns(self) -> None:
        with MemoryEnv() as temp_dir:
            project_root = Path(temp_dir)
            task_list = write_task_list(project_root, LEGACY_TASK_LIST)

            store = memory_store.MemoryStore()
            store.upsert_task_state(
                "T03",
                {
                    "objective": "Wire response hook",
                    "status": "open",
                    "recent_findings": ["parser returns unfinished rows"],
                    "next_step": "Add before_response payload support",
                    "metadata": {"acceptance": ["before_response returns summary"]},
                },
            )
            store.write_task_summary("T03", "# Progress\n\n- before_response test is still red.")

            summary = unfinished_task_summary.build_unfinished_task_summary(
                project_root=project_root,
                task_list_path=task_list,
                store=store,
            )

        tasks = {item["task_id"]: item for item in summary["tasks"]}
        self.assertEqual(set(tasks), {"T02", "T03", "T04"})
        self.assertEqual(summary["task_list_path"], str(task_list))
        self.assertEqual(tasks["T02"]["status"], "todo")
        self.assertEqual(tasks["T02"]["recent_checkpoint_or_update"], "unknown")
        self.assertEqual(tasks["T02"]["completed_acceptance"], ["unknown"])
        self.assertIn("report.md", tasks["T02"]["remaining_acceptance"][0])
        self.assertEqual(tasks["T02"]["blockers"], ["unknown"])
        self.assertIn("Step 42", tasks["T02"]["next_step"])
        self.assertTrue(any(source.startswith("task_list:") for source in tasks["T02"]["evidence_sources"]))

        self.assertNotEqual(tasks["T03"]["recent_checkpoint_or_update"], "unknown")
        self.assertIn("parser returns unfinished rows", tasks["T03"]["completed_acceptance"])
        self.assertEqual(tasks["T03"]["next_step"], "Add before_response payload support")
        self.assertTrue(any(source.startswith("task_state:T03") for source in tasks["T03"]["evidence_sources"]))
        self.assertTrue(any(source.startswith("task_summary:T03") for source in tasks["T03"]["evidence_sources"]))

        rendered = unfinished_task_summary.render_markdown(summary)
        self.assertIn("T02", rendered)
        self.assertIn("recent_checkpoint_or_update", rendered)
        self.assertIn("unknown", rendered)
        self.assertNotIn("%", rendered)

    def test_default_task_list_prefers_codex_specs_backlog_governance(self) -> None:
        with MemoryEnv() as temp_dir:
            project_root = Path(temp_dir)
            canonical = write_task_list(project_root, CANONICAL_TASK_LIST)
            write_task_list(project_root, LEGACY_TASK_LIST, LEGACY_ONLY_TASK_LIST)

            summary = unfinished_task_summary.build_unfinished_task_summary(project_root=project_root)

        self.assertEqual(summary["task_list_path"], str(canonical))
        self.assertEqual([item["task_id"] for item in summary["tasks"]], ["T02", "T03", "T04"])
        self.assertIn(str(project_root / CANONICAL_TASK_LIST), summary["task_list_candidates"])
        self.assertIn(str(project_root / LEGACY_TASK_LIST), summary["task_list_candidates"])

    def test_default_task_list_falls_back_to_legacy_docs_path(self) -> None:
        with MemoryEnv() as temp_dir:
            project_root = Path(temp_dir)
            legacy = write_task_list(project_root, LEGACY_TASK_LIST, LEGACY_ONLY_TASK_LIST)

            summary = unfinished_task_summary.build_unfinished_task_summary(project_root=project_root)

        self.assertEqual(summary["task_list_path"], str(legacy))
        self.assertEqual([item["task_id"] for item in summary["tasks"]], ["T90"])
        self.assertTrue(any("task list not found" in warning for warning in summary["warnings"]))

    def test_task_progress_uses_snapshot_fields_from_canonical_task_list(self) -> None:
        with MemoryEnv() as temp_dir:
            project_root = Path(temp_dir)
            write_task_list(project_root, CANONICAL_TASK_LIST, TASK_LIST_WITH_PROGRESS)

            summary = unfinished_task_summary.build_unfinished_task_summary(
                project_root=project_root,
                task_ids=["T02"],
            )

        task = summary["tasks"][0]
        self.assertEqual(task["recent_checkpoint_or_update"], "2026-05-13T09:57:14+00:00")
        self.assertEqual(task["completed_acceptance"], ["parser reads canonical task rows"])
        self.assertEqual(task["remaining_acceptance"], ["before_response should include progress fields"])
        self.assertEqual(task["blockers"], ["waiting for final review"])
        self.assertEqual(task["next_step"], "run targeted tests")
        self.assertTrue(any(source.startswith("progress_snapshot:") for source in task["evidence_sources"]))

    def test_before_response_can_include_unfinished_task_summary(self) -> None:
        with MemoryEnv() as temp_dir:
            project_root = Path(temp_dir)
            write_task_list(project_root, CANONICAL_TASK_LIST)

            runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
            runner.run_event("before_task", {"task_id": "current", "objective": "Summarize unfinished tasks"})
            result = runner.run_event(
                "before_response",
                {
                    "task_id": "current",
                    "include_unfinished_tasks": True,
                    "unfinished_task_ids": ["T02"],
                },
            )

        unfinished = result["result"]["unfinished_task_summary"]
        self.assertEqual([item["task_id"] for item in unfinished["tasks"]], ["T02"])
        self.assertTrue(
            result["result"]["unfinished_task_summary_markdown"].startswith("# Unfinished Task Progress Summary")
        )

    def test_default_store_uses_supplied_project_root(self) -> None:
        with MemoryEnv() as first_dir, MemoryEnv() as second_dir:
            first_root = Path(first_dir)
            second_root = Path(second_dir)
            write_task_list(first_root, CANONICAL_TASK_LIST)

            old_cwd = os.environ.get("CODEX_MEMORY_CWD")
            try:
                os.environ["CODEX_MEMORY_CWD"] = str(first_root)
                memory_store.MemoryStore().upsert_task_state(
                    "T03",
                    {
                        "objective": "Wire response hook",
                        "status": "open",
                        "recent_findings": ["from first project"],
                        "next_step": "Continue first project",
                    },
                )
                os.environ["CODEX_MEMORY_CWD"] = str(second_root)

                summary = unfinished_task_summary.build_unfinished_task_summary(project_root=first_root)
            finally:
                if old_cwd is None:
                    os.environ.pop("CODEX_MEMORY_CWD", None)
                else:
                    os.environ["CODEX_MEMORY_CWD"] = old_cwd

        tasks = {item["task_id"]: item for item in summary["tasks"]}
        self.assertIn("from first project", tasks["T03"]["completed_acceptance"])
        self.assertEqual(tasks["T03"]["next_step"], "Continue first project")

    def test_markdown_renders_warnings_when_task_list_is_missing(self) -> None:
        with MemoryEnv() as temp_dir:
            summary = unfinished_task_summary.build_unfinished_task_summary(project_root=Path(temp_dir))

        rendered = unfinished_task_summary.render_markdown(summary)
        self.assertIn("## Warnings", rendered)
        self.assertIn("task list not found", rendered)
        self.assertIn(".codex", rendered)
        self.assertIn("No unfinished tasks found.", rendered)
