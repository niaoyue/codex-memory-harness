from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIRED = [
    Path("docs/LLM_AGENT_MEMORY_HANDBOOK.md"),
    Path("docs/GROUNDED_FACT_WORKFLOW.md"),
]

ENGLISH_HIGH_RISK_RE = re.compile(
    r"(?i)\b(?:"
    r"OpenAI|ChatGPT|Responses API|Agents SDK|Codex Memories|Chronicle|"
    r"Prompt Caching|RAG|Retrieval-Augmented|vector database|embedding|"
    r"hallucination|confabulation|grounding|citation|source_id|"
    r"MCP|Context7|Unity|Unreal|OpenAPI|protobuf|GraphQL|SDK|CLI|"
    r"API authority|authority plan|official docs|local SDK|batchmode|contract test|"
    r"pricing|security|privacy|SubAgent|review gate|codex xhigh|"
    r"already implemented|currently implemented|officially supports"
    r")\b"
)
CHINESE_HIGH_RISK_TERMS = (
    "已经实现",
    "当前实现",
    "官方",
    "模型",
    "价格",
    "安全",
    "隐私",
    "不会",
    "保证",
    "发布级",
    "完整验证平台",
    "自动执行器",
    "向量数据库",
    "官方文档",
    "本地SDK",
    "版本识别",
    "权威来源",
    "权威资料",
    "Unity官方",
    "脚本API",
    "接口契约",
    "本节校正依据",
    "资料核验记录",
)
EVIDENCE_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{2,6}\s*)?(?:\d+(?:\.\d+)*[.、]?\s*)?"
    r"(本节校正依据|资料核验记录|官方参考|References|参考资料|权威资料基线)"
)
URL_RE = re.compile(r"https?://[^\s`)>\]]+")
LOCAL_EVIDENCE_RE = re.compile(
    r"`(?:docs|scripts|tests|plugins|templates|README\.md|AGENTS\.md|\.codex)/[^`]+`|"
    r"`(?:README\.md|AGENTS\.md)`|"
    r"`(?:py|python|codex|pwsh|powershell)[^`]+`"
)
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
SKIP_SECTION_RE = re.compile(r"(页面定位|页面版阅读结构建议|常见误区|逐点核对清单|继续阅读)")


@dataclass(frozen=True)
class Section:
    title: str
    level: int
    start_line: int
    end_line: int
    text: str
    ancestor_has_evidence: bool = False


def _display(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_doc(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _split_sections(text: str) -> list[Section]:
    lines = text.splitlines()
    starts: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line)
        if match:
            starts.append((index, len(match.group(1)), match.group(2).strip()))
    if not starts:
        return [Section("document", 1, 1, len(lines), text)]

    sections: list[Section] = []
    first_line = starts[0][0]
    if first_line > 1:
        preamble = "\n".join(lines[: first_line - 1])
        if preamble.strip():
            sections.append(Section("document preamble", 1, 1, first_line - 1, preamble))
    ancestors: list[tuple[int, bool]] = []
    for offset, (line_no, level, title) in enumerate(starts):
        while ancestors and ancestors[-1][0] >= level:
            ancestors.pop()
        end = starts[offset + 1][0] - 1 if offset + 1 < len(starts) else len(lines)
        body = "\n".join(lines[line_no - 1 : end])
        sections.append(
            Section(
                title=title,
                level=level,
                start_line=line_no,
                end_line=end,
                text=body,
                ancestor_has_evidence=any(has_evidence for _, has_evidence in ancestors),
            )
        )
        ancestors.append((level, _has_evidence(body)))
    return sections


def _evidence_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        if not EVIDENCE_HEADING_RE.search(lines[index]):
            index += 1
            continue
        block_lines = [lines[index]]
        index += 1
        while index < len(lines):
            line = lines[index]
            if HEADING_RE.match(line) and not EVIDENCE_HEADING_RE.search(line):
                break
            block_lines.append(line)
            index += 1
        blocks.append("\n".join(block_lines))
    return blocks


def _has_evidence(text: str) -> bool:
    for block in _evidence_blocks(text):
        if URL_RE.search(block) or LOCAL_EVIDENCE_RE.search(block):
            return True
    return False


def _has_any_evidence(text: str) -> bool:
    return bool(URL_RE.search(text) or LOCAL_EVIDENCE_RE.search(text))


def _has_high_risk(text: str) -> bool:
    return bool(ENGLISH_HIGH_RISK_RE.search(text)) or any(term in text for term in CHINESE_HIGH_RISK_TERMS)


def check_document(path: Path, required: bool) -> dict[str, object]:
    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    resolved = _resolve_doc(path)
    display_path = _display(resolved)

    if not resolved.exists():
        target = failures if required else warnings
        target.append({"path": display_path, "line": 1, "message": "document is missing"})
        return {
            "path": display_path,
            "required": required,
            "sections": 0,
            "failures": failures,
            "warnings": warnings,
        }

    text = resolved.read_text(encoding="utf-8")
    if required and not _has_any_evidence(text):
        failures.append({"path": display_path, "line": 1, "message": "required document has no evidence"})

    sections = _split_sections(text)
    for section in sections:
        if SKIP_SECTION_RE.search(section.title):
            continue
        if not _has_high_risk(section.text):
            continue
        if _has_evidence(section.text) or section.ancestor_has_evidence:
            continue
        item = {
            "path": display_path,
            "line": section.start_line,
            "section": section.title,
            "message": "high-risk section has no section-level evidence block",
        }
        if required:
            failures.append(item)
        else:
            warnings.append(item)

    return {
        "path": display_path,
        "required": required,
        "sections": len(sections),
        "failures": failures,
        "warnings": warnings,
    }


def iter_docs(docs_dir: Path) -> list[Path]:
    resolved = _resolve_doc(docs_dir)
    if not resolved.exists():
        return []
    return sorted(path for path in resolved.glob("*.md") if path.is_file())


def run(required_paths: list[Path], docs_dir: Path | None, scan_all: bool) -> dict[str, object]:
    required = {_resolve_doc(path).resolve() for path in required_paths}
    candidates: set[Path] = set(required)
    if scan_all and docs_dir is not None:
        candidates.update(path.resolve() for path in iter_docs(docs_dir))

    documents = [
        check_document(path, path.resolve() in required)
        for path in sorted(candidates, key=lambda item: _display(item))
    ]
    failures = [failure for document in documents for failure in document["failures"]]
    warnings = [warning for document in documents for warning in document["warnings"]]
    return {
        "ok": not failures,
        "checked_files": [document["path"] for document in documents],
        "failures": failures,
        "warnings": warnings,
        "documents": documents,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify grounded evidence blocks in high-risk docs.")
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"))
    parser.add_argument("--required", type=Path, action="append", default=[])
    parser.add_argument("--scan-all", action="store_true")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args()

    required = args.required or DEFAULT_REQUIRED
    result = run(required, args.docs_dir, args.scan_all)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
