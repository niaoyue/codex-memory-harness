from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from semantic_retrieval import create_semantic_provider
except ImportError:  # pragma: no cover - exercised when optional module is absent in older installs.
    create_semantic_provider = None  # type: ignore[assignment]


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PLUGIN_ROOT.parent.parent

EVIDENCE_PACK_SCHEMA = {
    "type": "object",
    "required": ["query", "mode", "items"],
    "properties": {
        "query": {"type": "string"},
        "mode": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "path", "match_type", "query", "score", "snippet"],
                "properties": {
                    "title": {"type": "string"},
                    "path": {"type": "string"},
                    "match_type": {"type": "string"},
                    "query": {"type": "string"},
                    "score": {"type": "number"},
                    "line": {"type": ["integer", "null"]},
                    "column": {"type": ["integer", "null"]},
                    "snippet": {"type": "string"},
                    "source": {"type": "string"},
                },
            },
        },
        "semantic": {
            "type": "object",
            "properties": {
                "available": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        },
    },
}


RETRIEVAL_MODES = {
    "auto": "Combine exact and full-text retrieval, preferring exact matches first.",
    "exact": "Prefer exact path and exact content matches.",
    "fulltext": "Search textual content with smart case matching.",
    "semantic": "Search optional local semantic provider when available, with deterministic fallback.",
}


EXCLUDED_GLOBS = [
    "!.git",
    "!**/__pycache__/**",
    "!plugins/codex-memory/storage/**",
    "!.codex/memories/**",
    "!.codex/harness/tasks/**",
    "!.codex/harness/review/**",
]

CODE_PRIORITY_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".ps1",
    ".sh",
}


@dataclass
class EvidenceItem:
    title: str
    path: str
    match_type: str
    query: str
    score: float
    snippet: str
    line: int | None = None
    column: int | None = None
    source: str = "workspace"

    def dedupe_key(self) -> tuple[str, str, int | None, str]:
        return (self.path, self.match_type, self.line, self.snippet)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_query(query: Any) -> str:
    normalized = str(query or "").strip()
    if not normalized:
        raise ValueError("Search query must not be empty.")
    return normalized


def _rg_base_command() -> list[str]:
    cmd = ["rg", "--hidden"]
    for pattern in EXCLUDED_GLOBS:
        cmd.extend(["--glob", pattern])
    return cmd


def _run_rg(args: list[str], *, cwd: Path = WORKSPACE_ROOT) -> subprocess.CompletedProcess[str]:
    command = _rg_base_command() + args
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or f"ripgrep failed with exit {result.returncode}")
    return result


def _iter_json_events(output: str) -> Iterable[dict[str, Any]]:
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def _is_identifier_query(query: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", query))


def _path_score(relative_path: str, query: str) -> float:
    rel = relative_path.replace("\\", "/").lower()
    path_obj = Path(relative_path)
    basename = path_obj.name.lower()
    stem = path_obj.stem.lower()
    q = query.lower()

    if basename == q or stem == q:
        return 120.0
    if basename.startswith(q) or stem.startswith(q):
        return 108.0
    if f"/{q}/" in f"/{rel}/":
        return 84.0
    if q in basename:
        return 78.0
    if q in rel:
        return 70.0
    return 0.0


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _code_priority_bonus(path: str) -> float:
    suffix = Path(path).suffix.lower()
    return 10.0 if suffix in CODE_PRIORITY_SUFFIXES else 0.0


def _snippet(text: str, limit: int = 220) -> str:
    normalized = text.rstrip("\r\n")
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


class RetrievalEngine:
    def __init__(self, workspace_root: Path = WORKSPACE_ROOT, semantic_provider: str = "disabled") -> None:
        self.workspace_root = workspace_root
        self.semantic_provider_name = semantic_provider
        self._semantic_provider: Any | None = None
        self._semantic_status: dict[str, Any] | None = None

    def _list_workspace_files(self) -> list[str]:
        result = _run_rg(["--files"], cwd=self.workspace_root)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _path_matches(self, query: str) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for relative_path in self._list_workspace_files():
            normalized_path = _normalize_path(relative_path)
            score = _path_score(normalized_path, query)
            if score <= 0:
                continue
            items.append(
                EvidenceItem(
                    title=Path(normalized_path).name,
                    path=normalized_path,
                    match_type="path",
                    query=query,
                    score=score,
                    snippet=f"path match: {normalized_path}",
                )
            )
        return items

    def _exact_content_matches(self, query: str) -> list[EvidenceItem]:
        args = ["--json", "-n", "-F", "-m", "2", "--max-columns", "240"]
        if _is_identifier_query(query):
            args.append("-w")
        args.extend([query, "."])
        result = _run_rg(args, cwd=self.workspace_root)

        items: list[EvidenceItem] = []
        for event in _iter_json_events(result.stdout):
            if event.get("type") != "match":
                continue
            data = event["data"]
            path = _normalize_path(data["path"]["text"])
            line_number = data.get("line_number")
            lines_text = data["lines"]["text"]
            submatches = data.get("submatches", [])
            column = int(submatches[0]["start"]) + 1 if submatches else None
            items.append(
                EvidenceItem(
                    title=Path(path).name,
                    path=path,
                    match_type="exact_content",
                    query=query,
                    score=96.0 + _code_priority_bonus(path),
                    line=line_number,
                    column=column,
                    snippet=_snippet(lines_text),
                )
            )
        return items

    def search_exact(self, query: str, limit: int = 10) -> list[EvidenceItem]:
        normalized_query = _clean_query(query)
        items = self._dedupe_and_sort(
            self._path_matches(normalized_query) + self._exact_content_matches(normalized_query)
        )
        return items[:limit]

    def search_fulltext(self, query: str, limit: int = 10) -> list[EvidenceItem]:
        normalized_query = _clean_query(query)
        result = _run_rg(
            ["--json", "-n", "-F", "-m", "2", "--max-columns", "240", "--smart-case", normalized_query, "."],
            cwd=self.workspace_root,
        )

        items: list[EvidenceItem] = []
        for event in _iter_json_events(result.stdout):
            if event.get("type") != "match":
                continue
            data = event["data"]
            path = _normalize_path(data["path"]["text"])
            line_number = data.get("line_number")
            lines_text = data["lines"]["text"]
            basename_bonus = 8.0 if normalized_query.lower() in Path(path).name.lower() else 0.0
            items.append(
                EvidenceItem(
                    title=Path(path).name,
                    path=path,
                    match_type="fulltext",
                    query=normalized_query,
                    score=68.0 + basename_bonus + _code_priority_bonus(path),
                    line=line_number,
                    snippet=_snippet(lines_text),
                )
            )
        items = self._dedupe_and_sort(items)
        return items[:limit]

    def semantic_placeholder(self, query: str) -> dict[str, Any]:
        return self._semantic_status_dict(_clean_query(query))

    def search_semantic(self, query: str, limit: int = 10) -> tuple[list[EvidenceItem], dict[str, Any]]:
        normalized_query = _clean_query(query)
        provider = self._get_semantic_provider()
        status = self._semantic_status_dict(normalized_query)
        if not status["available"]:
            return [], status

        matches = provider.search(normalized_query, limit=limit)
        items = [
            EvidenceItem(
                title=Path(match.path).name,
                path=match.path,
                match_type="semantic",
                query=normalized_query,
                score=82.0 + float(match.score),
                line=match.line,
                snippet=match.snippet,
            )
            for match in matches
        ]
        return self._dedupe_and_sort(items)[:limit], status

    def search(self, query: str, mode: str = "auto", limit: int = 10) -> dict[str, Any]:
        normalized_query = _clean_query(query)
        normalized_mode = str(mode).strip().lower() or "auto"
        if normalized_mode not in RETRIEVAL_MODES:
            raise ValueError(f"Unsupported retrieval mode: {mode}")

        limit = max(1, min(int(limit), 50))

        if normalized_mode == "exact":
            items = self.search_exact(normalized_query, limit=limit)
            semantic = self.semantic_placeholder(normalized_query)
        elif normalized_mode == "fulltext":
            items = self.search_fulltext(normalized_query, limit=limit)
            semantic = self.semantic_placeholder(normalized_query)
        elif normalized_mode == "semantic":
            items, semantic = self.search_semantic(normalized_query, limit=limit)
            if not semantic["available"]:
                fallback = self.search_exact(normalized_query, limit=limit) + self.search_fulltext(
                    normalized_query,
                    limit=limit,
                )
                items = self._dedupe_and_sort(fallback)[:limit]
        else:
            combined = self.search_exact(normalized_query, limit=limit) + self.search_fulltext(
                normalized_query,
                limit=limit,
            )
            semantic_items, semantic = self.search_semantic(normalized_query, limit=limit)
            combined.extend(semantic_items)
            items = self._dedupe_and_sort(combined)[:limit]

        return {
            "query": normalized_query,
            "mode": normalized_mode,
            "workspace_root": str(self.workspace_root),
            "items": [item.to_dict() for item in items],
            "semantic": semantic,
        }

    def _dedupe_and_sort(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        deduped: dict[tuple[str, str, int | None, str], EvidenceItem] = {}
        for item in items:
            key = item.dedupe_key()
            existing = deduped.get(key)
            if existing is None or item.score > existing.score:
                deduped[key] = item
        return sorted(
            deduped.values(),
            key=lambda item: (-item.score, item.path, item.line or 0, item.match_type),
        )

    def _get_semantic_provider(self) -> Any:
        if self._semantic_provider is not None:
            return self._semantic_provider

        if create_semantic_provider is None:
            self._semantic_provider = _UnavailableSemanticProvider(
                "semantic provider module is unavailable",
            )
            self._semantic_status = self._semantic_provider.status().to_dict()
            return self._semantic_provider

        provider = create_semantic_provider(self.semantic_provider_name, self.workspace_root)
        status = provider.rebuild(self._list_workspace_files())
        self._semantic_provider = provider
        self._semantic_status = status.to_dict()
        return provider

    def _semantic_status_dict(self, query: str) -> dict[str, Any]:
        self._get_semantic_provider()
        status = dict(self._semantic_status or {})
        status["query"] = query
        status.setdefault("available", False)
        status.setdefault("provider", str(self.semantic_provider_name or "auto"))
        status.setdefault("reason", "semantic provider unavailable")
        return status


class _UnavailableSemanticStatus:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": False,
            "provider": "unavailable",
            "reason": self.reason,
            "indexed_items": 0,
        }


class _UnavailableSemanticProvider:
    def __init__(self, reason: str) -> None:
        self._status = _UnavailableSemanticStatus(reason)

    def rebuild(self, relative_paths: Iterable[str]) -> _UnavailableSemanticStatus:
        return self._status

    def search(self, query: str, limit: int = 10) -> list[Any]:
        return []

    def status(self) -> _UnavailableSemanticStatus:
        return self._status
