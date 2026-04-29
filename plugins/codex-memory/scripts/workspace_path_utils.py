from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath


def normalize_many(values: list[str], *, project_root: Path | None = None) -> list[str]:
    return [path for value in values if (path := normalize_path(value, project_root=project_root))]


def normalize_path(value: str, *, project_root: Path | None = None) -> str:
    raw = str(value).replace("\\", "/").strip()
    if is_drive_relative(raw):
        return f"../{raw}"
    if is_drive_absolute(raw):
        relative = drive_absolute_to_project_relative(raw, project_root)
        if relative is None:
            return f"../{raw}"
        raw = relative
    if is_rooted_without_drive(raw):
        return f"../{raw.lstrip('/')}"
    text = raw.strip("/")
    if text in {"", "."}:
        return "."
    text = relative_to_project_root(raw, project_root).strip("/")
    parts: list[str] = []
    escaped = 0
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                escaped += 1
            continue
        parts.append(part)
    normalized = "/".join(parts)
    if escaped:
        prefix = "/".join(".." for _ in range(escaped))
        return f"{prefix}/{normalized}" if normalized else prefix
    return normalized or "."


def is_rooted_without_drive(value: str) -> bool:
    return value.startswith("/") and not Path(value).is_absolute()


def is_drive_relative(value: str) -> bool:
    return len(value) >= 2 and value[1] == ":" and value[0].isalpha() and not value.startswith(f"{value[:2]}/")


def is_drive_absolute(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[0].isalpha() and value[2] == "/"


def drive_absolute_to_project_relative(value: str, project_root: Path | None) -> str | None:
    if project_root is None:
        return None
    candidate = PureWindowsPath(value)
    root = PureWindowsPath(str(project_root))
    if not candidate.drive or candidate.drive.lower() != root.drive.lower():
        return None
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return None


def relative_to_project_root(value: str, project_root: Path | None = None) -> str:
    path = Path(value)
    if not path.is_absolute():
        return value
    root = project_root or Path(os.environ.get("CODEX_MEMORY_CWD") or Path.cwd())
    try:
        resolved = path.resolve(strict=False)
        return resolved.relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        external = str(path).replace("\\", "/").lstrip("/")
        return f"../{external}"


def first_parent_match(path: str, scopes: list[str]) -> str:
    if path == ".." or path.startswith("../"):
        return ""
    matches = [
        scope
        for scope in scopes
        if scope == "." or path == scope or path.startswith(f"{scope}/")
    ]
    if matches:
        return max(matches, key=lambda scope: len(scope.split("/")))
    return ""
