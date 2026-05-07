from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from workspace_path_utils import normalize_path


RELEASE_TEXT_WORDS = ("release", "publish", "hotfix", "发版", "发布", "热更", "渠道包", "提包")
RELEASE_TEXT_PHRASES = (
    "release build",
    "build release",
    "production build",
    "hot update",
    "hot update release",
    "release hot update",
    "发版构建",
    "发布构建",
    "热更发布",
    "发布热更",
    "正式热更",
    "热更包",
)
RELEASE_PATH_TOKENS = {"release", "publish", "hotfix", "build"}


def normalize_signal_path(value: Any, workspace_root: Path) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    raw_path = text.replace("\\", "/")
    if text.startswith("\\") and not text.startswith("\\\\"):
        return f"../{raw_path.lstrip('/')}"
    if is_rooted_without_drive(raw_path):
        return f"../{raw_path.lstrip('/')}"
    if raw_path.strip("/") in {"", "."}:
        return "."
    candidate = normalize_relative_path(raw_path.strip("/"))
    try:
        path = Path(text)
        if path.is_absolute():
            try:
                return path.resolve(strict=False).relative_to(workspace_root).as_posix()
            except ValueError:
                return external_signal_path(path)
        root_text = workspace_root.as_posix().rstrip("/")
        if candidate.lower().startswith(f"{root_text.lower()}/"):
            return candidate[len(root_text) + 1 :].strip("/")
    except (OSError, RuntimeError, ValueError):
        return candidate
    return candidate


def external_signal_path(path: Path) -> str:
    try:
        text = path.resolve(strict=False).as_posix()
    except (OSError, RuntimeError, ValueError):
        text = str(path).replace("\\", "/")
    return f"../{text.lstrip('/')}"


def is_rooted_without_drive(value: str) -> bool:
    return value.startswith("/") and not Path(value).is_absolute()


def normalize_relative_path(value: str) -> str:
    return normalize_path(value)


def has_release_signal(signals: dict[str, Any]) -> bool:
    text = str(signals.get("text") or "")
    if any(word in text for word in RELEASE_TEXT_WORDS) or any(phrase in text for phrase in RELEASE_TEXT_PHRASES):
        return True
    paths = string_list(signals.get("paths"))
    cwd = str(signals.get("cwd") or "")
    return any(path_has_release_signal(path) for path in paths + ([cwd] if cwd else []))


def text_has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", lowered) if token}
    for keyword in keywords:
        normalized = keyword.lower()
        if not normalized:
            continue
        if re.search(r"[^a-z0-9]", normalized):
            if normalized in lowered:
                return True
        elif normalized in tokens:
            return True
    return False


def path_has_release_signal(path: str) -> bool:
    lowered = path.lower()
    if any(word in lowered for word in ("发版", "发布", "热更", "渠道包")):
        return True
    tokens = {token for token in re.split(r"[^a-z0-9]+", lowered) if token}
    return bool(tokens & RELEASE_PATH_TOKENS)


def git_changed_paths(workspace_root: Path) -> list[str]:
    paths = set(git_output_paths(workspace_root, ["git", "diff", "--name-only", "HEAD"]))
    paths.update(git_output_paths(workspace_root, ["git", "ls-files", "--others", "--exclude-standard"]))
    return sorted(paths)


def git_output_paths(workspace_root: Path, command: list[str]) -> list[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode not in (0, 1):
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def project_path_hits(project: dict[str, Any], all_projects: list[dict[str, Any]], paths: list[str]) -> list[str]:
    safe_paths = [path for path in paths if not is_escaping_path(path)]
    if paths and not safe_paths:
        return []
    cwd = str(project.get("cwd") or "").replace("\\", "/").strip("/")
    if cwd not in {"", "."}:
        return [path for path in safe_paths if path_in_scope(path, cwd)]
    child_scopes = [
        str(item.get("cwd") or "").replace("\\", "/").strip("/")
        for item in all_projects
        if item is not project and str(item.get("cwd") or "").replace("\\", "/").strip("/") not in {"", "."}
    ]
    return [path for path in safe_paths if not any(path_in_scope(path, scope) for scope in child_scopes)]


def path_in_scope(path: str, scope: str) -> bool:
    normalized_path = str(path).replace("\\", "/").strip("/")
    normalized_scope = str(scope).replace("\\", "/").strip("/")
    if normalized_scope in {"", "."}:
        return True
    return normalized_path == normalized_scope or normalized_path.startswith(f"{normalized_scope}/")


def is_escaping_path(path: str) -> bool:
    normalized = str(path).replace("\\", "/").strip()
    return (
        normalized in {".."}
        or normalized.startswith("../")
        or normalized.startswith("/")
        or (len(normalized) > 2 and normalized[1:3] == ":/" and normalized[0].isalpha())
    )


def fallback_profiles(inventory: dict[str, Any]) -> list[str]:
    config_path = Path(str(inventory.get("config_path") or ""))
    if inventory.get("config_loaded") and config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
        fallback = config.get("fallback") if isinstance(config, dict) else {}
        profiles = string_list(fallback.get("verification_profiles")) if isinstance(fallback, dict) else []
        if profiles:
            return profiles
    return ["primary"] if inventory else []


def diagnostic_logging_policy(
    workspace_policy: dict[str, Any] | None,
    project_policy: dict[str, Any] | None,
    task_type: str,
) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    policy.update(workspace_policy or {})
    policy.update(project_policy or {})
    default_allowed = policy.get("default_allowed")
    allowed = bool(default_allowed) if isinstance(default_allowed, bool) else task_type != "release"
    if task_type == "release":
        allowed = False
    required_scopes = ["flow", "state"] if task_type in {"ui", "contract"} else []
    allowed_scopes = string_list(policy.get("allowed_scopes"))
    if allowed_scopes:
        required_scopes = [scope for scope in required_scopes if scope in allowed_scopes]
    return {
        "allowed": allowed,
        "requested_scopes": [],
        "required_scopes": required_scopes,
        "release_must_be_disabled": bool(policy.get("release_must_be_disabled", True)),
    }


def project_diagnostic_policies(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in config.get("projects") if isinstance(config.get("projects"), list) else []:
        if not isinstance(item, dict):
            continue
        project_id = str(item.get("id") or "").strip()
        if project_id:
            result[project_id] = dict_value(item.get("diagnostic_logging"))
    return result


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
