from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_INDEX_BYTES = 256 * 1024
MAX_INDEX_LINES_PER_FILE = 2000
MIN_SCORE = 0.08

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

CANONICAL_TOKENS = {
    "auth": {
        "authenticate",
        "authentication",
        "authorization",
        "credential",
        "credentials",
        "login",
        "signin",
        "signon",
        "password",
    },
    "error": {
        "bug",
        "crash",
        "exception",
        "fail",
        "failed",
        "fails",
        "failure",
        "fault",
        "issue",
        "problem",
    },
    "config": {
        "configuration",
        "configure",
        "option",
        "options",
        "setting",
        "settings",
    },
    "search": {
        "find",
        "lookup",
        "query",
        "recall",
        "retrieval",
        "retrieve",
    },
    "memory": {
        "context",
        "evidence",
        "history",
        "recall",
        "summary",
    },
    "test": {
        "check",
        "checks",
        "validate",
        "validation",
        "verify",
        "verification",
    },
}

TOKEN_ALIASES = {
    alias: canonical
    for canonical, aliases in CANONICAL_TOKENS.items()
    for alias in aliases | {canonical}
}


@dataclass(frozen=True)
class SemanticDocument:
    path: str
    line: int | None
    text: str
    weights: Counter[str]


@dataclass(frozen=True)
class SemanticMatch:
    path: str
    line: int | None
    score: float
    snippet: str


@dataclass(frozen=True)
class SemanticStatus:
    available: bool
    provider: str
    reason: str
    indexed_items: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "provider": self.provider,
            "reason": self.reason,
            "indexed_items": self.indexed_items,
        }


class DisabledSemanticProvider:
    def __init__(self, reason: str = "semantic provider disabled") -> None:
        self._status = SemanticStatus(False, "disabled", reason)

    def index(self, relative_paths: Iterable[str]) -> SemanticStatus:
        return self._status

    def rebuild(self, relative_paths: Iterable[str]) -> SemanticStatus:
        return self._status

    def search(self, query: str, limit: int = 10) -> list[SemanticMatch]:
        return []

    def status(self) -> SemanticStatus:
        return self._status


class LocalSemanticProvider:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self._documents: list[SemanticDocument] = []
        self._idf: dict[str, float] = {}
        self._status = SemanticStatus(False, "local", "index has not been built")

    def index(self, relative_paths: Iterable[str]) -> SemanticStatus:
        documents: list[SemanticDocument] = []
        for relative_path in relative_paths:
            documents.extend(self._documents_for_file(str(relative_path)))

        self._documents = documents
        self._idf = _build_idf(documents)
        self._status = SemanticStatus(
            bool(documents),
            "local",
            "local deterministic token provider ready" if documents else "no indexable text files",
            indexed_items=len(documents),
        )
        return self._status

    def rebuild(self, relative_paths: Iterable[str]) -> SemanticStatus:
        self._documents = []
        self._idf = {}
        return self.index(relative_paths)

    def search(self, query: str, limit: int = 10) -> list[SemanticMatch]:
        query_weights = _weighted_tokens(query)
        if not self._documents or not query_weights:
            return []

        scored: list[SemanticMatch] = []
        for document in self._documents:
            score = _score(query_weights, document.weights, self._idf)
            if score < MIN_SCORE:
                continue
            scored.append(
                SemanticMatch(
                    path=document.path,
                    line=document.line,
                    score=round(score * 100.0, 3),
                    snippet=_snippet(document.text),
                )
            )
        scored.sort(key=lambda item: (-item.score, item.path, item.line or 0, item.snippet))
        return scored[: max(1, min(int(limit), 50))]

    def status(self) -> SemanticStatus:
        return self._status

    def _documents_for_file(self, relative_path: str) -> list[SemanticDocument]:
        relative_path = relative_path.replace("\\", "/")
        absolute_path = self.workspace_root / relative_path
        if not absolute_path.is_file():
            return []
        try:
            if absolute_path.stat().st_size > MAX_INDEX_BYTES:
                return []
            text = absolute_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []

        documents: list[SemanticDocument] = []
        for index, line in enumerate(text.splitlines(), start=1):
            if index > MAX_INDEX_LINES_PER_FILE:
                break
            weights = _weighted_tokens(f"{relative_path} {line}")
            if not weights:
                continue
            documents.append(SemanticDocument(relative_path, index, line, weights))
        return documents


def create_semantic_provider(name: str, workspace_root: Path) -> DisabledSemanticProvider | LocalSemanticProvider:
    normalized = str(name or "auto").strip().lower()
    if normalized in {"", "auto", "local"}:
        return LocalSemanticProvider(workspace_root)
    if normalized in {"disabled", "none", "off", "false"}:
        return DisabledSemanticProvider("semantic provider disabled")
    return DisabledSemanticProvider(f"unsupported semantic provider: {name}")


def _weighted_tokens(text: str) -> Counter[str]:
    weights: Counter[str] = Counter()
    for raw in TOKEN_RE.findall(text.lower()):
        token = _normalize_token(raw)
        if len(token) <= 1:
            continue
        weights[token] += 1
        canonical = TOKEN_ALIASES.get(token)
        if canonical and canonical != token:
            weights[canonical] += 2
    return weights


def _normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 3 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _build_idf(documents: list[SemanticDocument]) -> dict[str, float]:
    document_count = max(1, len(documents))
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(document.weights.keys())
    return {
        token: math.log((1 + document_count) / (1 + frequency)) + 1.0
        for token, frequency in document_frequency.items()
    }


def _score(query: Counter[str], document: Counter[str], idf: dict[str, float]) -> float:
    shared = set(query) & set(document)
    if not shared:
        return 0.0

    weighted_overlap = sum(min(query[token], document[token]) * idf.get(token, 1.0) for token in shared)
    query_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in query.items()))
    document_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in document.items()))
    cosine = weighted_overlap / max(query_norm * document_norm, 1e-9)
    jaccard = len(shared) / max(len(set(query) | set(document)), 1)
    return (cosine * 0.82) + (jaccard * 0.18)


def _snippet(text: str, limit: int = 220) -> str:
    normalized = text.rstrip("\r\n")
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."
