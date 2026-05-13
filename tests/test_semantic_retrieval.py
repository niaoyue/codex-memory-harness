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


class SemanticRetrievalTests(unittest.TestCase):
    def test_local_semantic_provider_matches_related_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write(
                root / "notes" / "incidents.md",
                "The login bug happens when credential validation fails.\n",
            )
            _write(root / "notes" / "billing.md", "Invoice export settings live here.\n")

            result = retrieval_store.RetrievalEngine(root, semantic_provider="local").search(
                "auth error",
                mode="semantic",
                limit=3,
            )

        self.assertTrue(result["semantic"]["available"])
        self.assertEqual(result["semantic"]["provider"], "local")
        self.assertEqual(result["items"][0]["path"], "notes/incidents.md")
        self.assertEqual(result["items"][0]["match_type"], "semantic")

    def test_auto_mode_degrades_when_semantic_provider_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write(root / "README.md", "fallback-needle remains searchable.\n")

            result = retrieval_store.RetrievalEngine(root, semantic_provider="disabled").search(
                "fallback-needle",
                mode="auto",
                limit=5,
            )

        self.assertFalse(result["semantic"]["available"])
        self.assertIn("disabled", result["semantic"]["reason"])
        self.assertIn("README.md", [item["path"] for item in result["items"]])


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
