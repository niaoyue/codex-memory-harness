from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import requirements_conflict_scanner  # noqa: E402


class RequirementsConflictScannerTests(unittest.TestCase):
    def test_blocks_on_task_conflict_fields(self) -> None:
        result = requirements_conflict_scanner.scan(
            Path.cwd(),
            task={"logical_conflicts": ["UI says delete, API says archive"]},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["requirements_gate"]["status"], "blocked_by_conflict")
        self.assertIn("UI says delete", result["requirements_gate"]["logical_conflicts"][0])

    def test_scans_openspec_conflict_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            change = root / "openspec" / "changes" / "change-a"
            change.mkdir(parents=True)
            (change / "proposal.md").write_text(
                "# Proposal\n\nCONFLICT: existing task list marks the feature done.\n",
                encoding="utf-8",
            )

            result = requirements_conflict_scanner.scan(root, change_id="change-a")

        self.assertFalse(result["ok"])
        self.assertEqual(result["conflicts"][0]["source"], "openspec/changes/change-a/proposal.md:3")

    def test_passes_without_explicit_conflicts(self) -> None:
        result = requirements_conflict_scanner.scan(Path.cwd(), task={"task_intent": "docs"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "passed")


if __name__ == "__main__":
    unittest.main()
