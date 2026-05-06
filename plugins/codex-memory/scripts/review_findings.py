from __future__ import annotations

import json
import re
from typing import Any


PARTIAL_TAIL_CHARS = 8192
REVIEW_FINDING_PATTERN = re.compile(r"(?im)^\s*(?:[-*]|\d+[.)])\s*\[(P\d+)\](?=\s|:|-|$)")
REVIEW_FINDING_INLINE_PATTERN = re.compile(r"(?i)\[(P\d+)\](?=\s|:|-|$)")
REVIEW_COMMENTS_MARKER_PATTERN = re.compile(r"(?im)^\s*Full review comments:\s*$")


class ReviewFindingsTracker:
    def __init__(self) -> None:
        self._partials: dict[str, str] = {}
        self._text: dict[str, list[str]] = {}
        self._priorities: list[str] = []
        self._sources: list[str] = []
        self._count = 0
        self._marker_found = False
        self._structured_recorded = False

    def append(self, source: str, text: str) -> None:
        if not text:
            return
        self._append_text(source, text)
        partial = self._partials.get(source, "") + text
        while "\n" in partial:
            line, partial = partial.split("\n", 1)
            self._record_line(source, line.rstrip("\r"))
        self._partials[source] = partial[-PARTIAL_TAIL_CHARS:]

    def append_lines(self, source: str, lines: list[str]) -> None:
        self._append_text(source, "\n".join(lines))
        for line in lines:
            self._record_line(source, line.rstrip("\r"))

    def summary(self) -> dict[str, Any]:
        for source, partial in list(self._partials.items()):
            if not partial:
                continue
            self._record_line(source, partial.rstrip("\r"))
            self._partials[source] = ""
        self._record_structured_json()
        findings_found = self._count > 0
        return {
            "review_findings_found": findings_found,
            "blocking_findings_found": findings_found,
            "review_findings_count": self._count,
            "review_finding_priorities": list(self._priorities),
            "review_findings_sources": list(self._sources),
            "review_findings_marker_found": self._marker_found,
        }

    def _record_line(self, source: str, line: str) -> None:
        self._marker_found = self._marker_found or REVIEW_COMMENTS_MARKER_PATTERN.match(line) is not None
        matches = REVIEW_FINDING_PATTERN.findall(line)
        if matches:
            self._record_matches(source, len(matches), matches)

    def _append_text(self, source: str, text: str) -> None:
        if text:
            self._text.setdefault(source, []).append(text)

    def _record_structured_json(self) -> None:
        if self._structured_recorded:
            return
        self._structured_recorded = True
        for source, chunks in self._text.items():
            for count, priorities in _json_finding_groups("".join(chunks)):
                self._record_matches(source, count, priorities)

    def _record_matches(self, source: str, count: int, priorities: list[str]) -> None:
        if count <= 0:
            return
        self._count += count
        if source not in self._sources:
            self._sources.append(source)
        for priority in priorities:
            normalized = priority.upper()
            if normalized not in self._priorities:
                self._priorities.append(normalized)


def detect_review_findings(stdout_lines: list[str], stderr_lines: list[str]) -> dict[str, Any]:
    tracker = ReviewFindingsTracker()
    for source, lines in (("stdout_tail", stdout_lines), ("stderr_tail", stderr_lines)):
        tracker.append_lines(source, lines)
    return tracker.summary()


def _json_finding_groups(text: str) -> list[tuple[int, list[str]]]:
    groups: list[tuple[int, list[str]]] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        start = _next_json_start(text, index)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        count, priorities = _findings_from_json(payload)
        if count:
            groups.append((count, priorities))
        index = end if end > start else start + 1
    return groups


def _next_json_start(text: str, index: int) -> int:
    candidates = [position for position in (text.find("{", index), text.find("[", index)) if position >= 0]
    return min(candidates) if candidates else -1


def _findings_from_json(value: Any) -> tuple[int, list[str]]:
    count = 0
    priorities: list[str] = []
    if isinstance(value, dict):
        findings = value.get("findings")
        if isinstance(findings, list):
            count += len(findings)
            for finding in findings:
                priorities.extend(_priorities_from_json(finding))
        for item in value.values():
            child_count, child_priorities = _findings_from_json(item)
            count += child_count
            priorities.extend(child_priorities)
    elif isinstance(value, list):
        for item in value:
            child_count, child_priorities = _findings_from_json(item)
            count += child_count
            priorities.extend(child_priorities)
    return count, priorities


def _priorities_from_json(value: Any) -> list[str]:
    results: list[str] = []
    if isinstance(value, dict):
        for key in ("title", "message", "body", "description", "priority", "severity"):
            results.extend(_priority_values(value.get(key)))
    elif isinstance(value, list):
        for item in value:
            results.extend(_priorities_from_json(item))
    return results


def _priority_values(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, int):
        return [f"P{value}"] if value >= 0 else []
    text = str(value)
    bracketed = REVIEW_FINDING_INLINE_PATTERN.findall(text)
    if bracketed:
        return bracketed
    match = re.fullmatch(r"(?i)P(\d+)", text.strip())
    if match:
        return [f"P{match.group(1)}"]
    return []
