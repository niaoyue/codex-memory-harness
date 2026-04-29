from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
)
_AK_RE = re.compile(r"\bAK:[A-Za-z0-9_-]{8,}\b")
_JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b")
_AUTH_RE = re.compile(r"(?i)\b(authorization\s*[:=]\s*)[^\r\n]+")
_BEARER_RE = re.compile(r"(?i)(?<![-A-Za-z0-9_])bearer\s+[A-Za-z0-9._~+/=-]{12,}\b")
_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])(?P<key_quote>[\"']?)"
    r"(?P<key>[A-Za-z0-9_-]*(?:authorization|token|password|passwd|secret|credential|api[_-]?key|access[_-]?key|private[_-]?key|cookie)[A-Za-z0-9_-]*)"
    r"(?P=key_quote)\s*(?P<separator>[:=])\s*(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n,;}]+)"
)
_SENSITIVE_KEY_PARTS = (
    "token",
    "password",
    "passwd",
    "secret",
    "credential",
    "cookie",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "accesskey",
    "private_key",
)


@dataclass
class SensitiveFinding:
    category: str
    action: str
    path: str


@dataclass
class SanitizationResult:
    value: Any
    findings: list[SensitiveFinding] = field(default_factory=list)
    blocked: bool = False

    def report(self) -> dict[str, Any]:
        categories = sorted({item.category for item in self.findings})
        actions = sorted({item.action for item in self.findings})
        return {
            "redacted": any(item.action == "redact" for item in self.findings),
            "blocked": self.blocked,
            "finding_count": len(self.findings),
            "categories": categories,
            "actions": actions,
        }


def sanitize_for_persistence(value: Any) -> SanitizationResult:
    findings: list[SensitiveFinding] = []
    sanitized = _sanitize(value, "$", findings)
    blocked = any(item.action == "block" for item in findings)
    return SanitizationResult(value=sanitized, findings=findings, blocked=blocked)


def assert_safe_for_persistence(result: SanitizationResult, *, context: str) -> None:
    if result.blocked:
        categories = ", ".join(result.report()["categories"])
        raise ValueError(f"Blocked sensitive content before persisting {context}: {categories}")


def sanitized_payload(value: Any, *, context: str) -> Any:
    result = sanitize_for_persistence(value)
    assert_safe_for_persistence(result, context=context)
    sanitized = result.value
    if result.findings and isinstance(sanitized, dict):
        sanitized = dict(sanitized)
        sanitized["_sensitive_scan"] = result.report()
    return sanitized


def _sanitize(value: Any, path: str, findings: list[SensitiveFinding]) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_sensitive_key(key_text):
                _sanitize(item, child_path, findings)
                sanitized[key_text] = "[REDACTED]"
                findings.append(SensitiveFinding("sensitive_key", "redact", child_path))
                continue
            sanitized[key_text] = _sanitize(item, child_path, findings)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, f"{path}[{index}]", findings) for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return tuple(_sanitize(item, f"{path}[{index}]", findings) for index, item in enumerate(value))
    if isinstance(value, str):
        return _sanitize_text(value, path, findings)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _sanitize_text(value: str, path: str, findings: list[SensitiveFinding]) -> str:
    text = value
    if _PRIVATE_KEY_RE.search(text):
        findings.append(SensitiveFinding("private_key", "block", path))
        text = _PRIVATE_KEY_RE.sub("[BLOCKED_PRIVATE_KEY]", text)
    text = _replace(_AK_RE, text, "[REDACTED_AK]", "access_key", path, findings)
    text = _replace(_JWT_RE, text, "[REDACTED_JWT]", "jwt", path, findings)
    text = _AUTH_RE.sub(lambda match: _auth_replacement(match, path, findings), text)
    text = _BEARER_RE.sub(lambda match: _bearer_replacement(match, path, findings), text)
    text = _ASSIGNMENT_RE.sub(lambda match: _assignment_replacement(match, path, findings), text)
    return text


def _replace(
    pattern: re.Pattern[str],
    text: str,
    replacement: str,
    category: str,
    path: str,
    findings: list[SensitiveFinding],
) -> str:
    if pattern.search(text):
        findings.append(SensitiveFinding(category, "redact", path))
    return pattern.sub(replacement, text)


def _auth_replacement(match: re.Match[str], path: str, findings: list[SensitiveFinding]) -> str:
    header_value = match.group(0)[len(match.group(1)) :]
    if _is_redacted_placeholder(header_value):
        return match.group(0)
    findings.append(SensitiveFinding("authorization", "redact", path))
    return f"{match.group(1)}[REDACTED]"


def _bearer_replacement(match: re.Match[str], path: str, findings: list[SensitiveFinding]) -> str:
    findings.append(SensitiveFinding("bearer_token", "redact", path))
    return "Bearer [REDACTED]"


def _assignment_replacement(match: re.Match[str], path: str, findings: list[SensitiveFinding]) -> str:
    key = match.group("key")
    value = match.group("value")
    if _is_redacted_placeholder(value):
        return match.group(0)
    findings.append(SensitiveFinding(key.lower(), "redact", path))
    return _redacted_assignment(match)


def _redacted_assignment(match: re.Match[str]) -> str:
    key_quote = match.group("key_quote") or ""
    separator = match.group("separator")
    value = match.group("value")
    value_quote = value[0] if value.startswith(("\"", "'")) else ""
    redacted_value = f"{value_quote}[REDACTED]{value_quote}" if separator == ":" and value_quote else "[REDACTED]"
    spacer = " " if separator == ":" else ""
    return f"{key_quote}{match.group('key')}{key_quote}{separator}{spacer}{redacted_value}"


def _is_redacted_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").upper()
    return normalized in {
        "[REDACTED]",
        "[REDACTED_AK]",
        "[REDACTED_JWT]",
        "[BLOCKED_PRIVATE_KEY]",
    }
