from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import retrieval_store


class RetrievalStoreTests(unittest.TestCase):
    def test_search_excludes_review_runtime_artifacts(self) -> None:
        old_root = retrieval_store.WORKSPACE_ROOT
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            try:
                retrieval_store.WORKSPACE_ROOT = root
                _write(root / "README.md", "review-runtime-needle kept\n")
                _write(root / ".codex" / "harness" / "review" / "final-xhigh" / "stderr.log", "review-runtime-needle leaked\n")
                _write(root / "plugins" / "codex-memory" / "scripts" / "__pycache__" / "cache.pyc", "review-runtime-needle leaked\n")

                result = retrieval_store.RetrievalEngine(root).search_fulltext("review-runtime-needle", limit=10)
            finally:
                retrieval_store.WORKSPACE_ROOT = old_root

        paths = [item.path for item in result]
        self.assertIn("README.md", paths)
        self.assertNotIn(".codex/harness/review/final-xhigh/stderr.log", paths)
        self.assertNotIn("plugins/codex-memory/scripts/__pycache__/cache.pyc", paths)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
