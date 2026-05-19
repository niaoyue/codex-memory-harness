from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_unittest_modules


class RunUnittestModulesTests(unittest.TestCase):
    def test_discovers_test_modules_in_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "test_b.py").write_text("import unittest\n", encoding="utf-8")
            (root / "test_a.py").write_text("import unittest\n", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "test_cached.py").write_text("", encoding="utf-8")

            modules = run_unittest_modules.discover_modules(root, "test*.py")

        self.assertEqual(modules, ["test_a", "test_b"])

    def test_parse_unittest_counts_reads_tests_and_skips(self) -> None:
        output = "Ran 710 tests in 102.856s\n\nOK (skipped=12)\n"

        counts = run_unittest_modules.parse_unittest_counts(output)

        self.assertEqual(counts, {"tests": 710, "skipped": 12})

    def test_runs_modules_from_custom_start_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "test_sample.py").write_text(
                "import unittest\n\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            modules = run_unittest_modules.discover_modules(root, "test*.py")
            result = run_unittest_modules.run_modules(
                modules,
                jobs=1,
                timeout_seconds=30,
                start_dir=root,
                include_module_results=False,
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["tests"], 1)
        self.assertEqual(result["failed_modules"], [])


if __name__ == "__main__":
    unittest.main()
