from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_grounded_docs


class GroundedDocsTests(unittest.TestCase):
    def test_required_high_risk_section_without_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "draft.md"
            doc.write_text("## OpenAI 能力\n\nOpenAI 官方已经支持这个能力。\n", encoding="utf-8")

            result = verify_grounded_docs.run([doc], docs_dir, scan_all=False)

        self.assertFalse(result["ok"])
        self.assertIn("high-risk section has no section-level evidence block", json.dumps(result, ensure_ascii=False))

    def test_required_high_risk_section_with_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "draft.md"
            doc.write_text(
                "## OpenAI 能力\n\nOpenAI 官方文档需要逐项核验。\n\n"
                "本节校正依据（2026-05-06 只读核对）：\n\n"
                "- OpenAI：`https://platform.openai.com/docs`\n",
                encoding="utf-8",
            )

            result = verify_grounded_docs.run([doc], docs_dir, scan_all=False)

        self.assertTrue(result["ok"])

    def test_api_authority_section_without_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "api.md"
            doc.write_text(
                "## Unity API 调用\n\n"
                "Unity 官方 API 可以直接用模型记忆生成，Context7 会自动证明版本正确。\n",
                encoding="utf-8",
            )

            result = verify_grounded_docs.run([doc], docs_dir, scan_all=False)

        self.assertFalse(result["ok"])
        self.assertIn("high-risk section has no section-level evidence block", json.dumps(result, ensure_ascii=False))

    def test_contiguous_chinese_high_risk_assertion_without_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "platform.md"
            doc.write_text(
                "## 验证能力\n\n"
                "当前已经实现发布级完整验证平台。\n",
                encoding="utf-8",
            )

            result = verify_grounded_docs.run([doc], docs_dir, scan_all=False)

        self.assertFalse(result["ok"])
        self.assertIn("high-risk section has no section-level evidence block", json.dumps(result, ensure_ascii=False))

    def test_plain_section_without_high_risk_terms_passes_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "notes.md"
            doc.write_text(
                "## 日常记录\n\n"
                "这里记录普通项目背景和下一步整理事项。\n",
                encoding="utf-8",
            )

            result = verify_grounded_docs.run([], docs_dir, scan_all=True)

        self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False, indent=2))
        self.assertEqual(result["warnings"], [])

    def test_preamble_high_risk_assertion_without_section_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "intro.md"
            doc.write_text(
                "# 项目说明\n\n"
                "当前已经实现发布级完整验证平台。\n\n"
                "## 参考\n\n"
                "本节校正依据：`https://example.com/reference`\n",
                encoding="utf-8",
            )

            result = verify_grounded_docs.run([doc], docs_dir, scan_all=False)

        self.assertFalse(result["ok"])
        self.assertIn("document preamble", json.dumps(result, ensure_ascii=False))

    def test_nested_high_risk_assertion_is_not_covered_by_later_subsection_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "nested.md"
            doc.write_text(
                "## 平台能力\n\n"
                "### 能力声明\n\n"
                "当前已经实现发布级完整验证平台。\n\n"
                "### 参考资料\n\n"
                "本节校正依据：`https://example.com/reference`\n",
                encoding="utf-8",
            )

            result = verify_grounded_docs.run([doc], docs_dir, scan_all=False)

        self.assertFalse(result["ok"])
        self.assertIn("能力声明", json.dumps(result, ensure_ascii=False))

    def test_parent_section_evidence_covers_nested_subsections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_dir = Path(temp_dir)
            doc = docs_dir / "nested.md"
            doc.write_text(
                "## 平台能力\n\n"
                "本节校正依据：`https://example.com/reference`\n\n"
                "### 能力声明\n\n"
                "当前已经实现发布级完整验证平台。\n",
                encoding="utf-8",
            )

            result = verify_grounded_docs.run([doc], docs_dir, scan_all=False)

        self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False, indent=2))

    def test_current_required_docs_are_grounded(self) -> None:
        result = verify_grounded_docs.run(
            [
                PROJECT_ROOT / "docs" / "LLM_AGENT_MEMORY_HANDBOOK.md",
                PROJECT_ROOT / "docs" / "GROUNDED_FACT_WORKFLOW.md",
            ],
            PROJECT_ROOT / "docs",
            scan_all=False,
        )

        self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main()
