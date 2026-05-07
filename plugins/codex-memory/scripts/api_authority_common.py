from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any


AUTO_INSTALL_POLICY = "disabled_readonly_phase1"
FRAMEWORK_PACKAGE_NAMES = {
    "next": ("next",),
    "vue": ("vue", "@vue/core"),
    "react": ("react",),
    "angular": ("angular", "@angular/core"),
    "svelte": ("svelte", "@sveltejs/kit"),
}
MCP_ALIASES = {
    "openai-docs": {"openai-docs", "openai_docs", "openai-docs-mcp", "docs-openai"},
    "context7": {"context7", "context7-mcp", "@upstash/context7-mcp"},
}


def detect_codex_mcp_servers(codex_home: Path) -> list[str]:
    config_path = codex_home / "config.toml"
    if not config_path.exists():
        return []
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    servers = payload.get("mcp_servers")
    if not isinstance(servers, dict):
        return []
    return sorted(str(name) for name in servers if str(name).strip())


def mcp_status(required: list[str], installed: list[str], *, optional: bool) -> dict[str, Any]:
    installed_matches: list[str] = []
    missing: list[str] = []
    normalized_installed = {normalize_name(item): item for item in installed}
    for server in required:
        aliases = MCP_ALIASES.get(server, {server})
        match = next(
            (
                normalized_installed[normalize_name(alias)]
                for alias in aliases
                if normalize_name(alias) in normalized_installed
            ),
            "",
        )
        if match:
            installed_matches.append(match)
        else:
            missing.append(server)
    next_action = "use_installed_mcp" if not missing else "record_install_plan_and_use_fallback_authority"
    return {
        "required": required,
        "installed": unique(installed_matches),
        "missing": missing,
        "optional": optional,
        "auto_install": False,
        "install_policy": AUTO_INSTALL_POLICY,
        "next_action": next_action,
    }


def base_project_payload(
    project: dict[str, Any],
    *,
    ecosystem: str,
    detected_version: str,
    api_surfaces: list[str],
    authority_channels: list[str],
    locators: list[str],
    verification: list[str],
    mcp: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "project_id": project.get("id"),
        "domain": project.get("domain"),
        "cwd": project.get("cwd") or ".",
        "ecosystem": ecosystem,
        "detected_version": detected_version or "n/a",
        "api_surfaces": unique(api_surfaces),
        "authority_channels": unique(authority_channels),
        "locators": unique([item for item in locators if item]),
        "verification": unique(verification),
        "mcp": mcp,
        "status": "plan_ready",
    }
    if extra:
        payload.update(extra)
    return payload


def read_unity_version(project_root: Path) -> str:
    text = read_text(project_root / "ProjectSettings" / "ProjectVersion.txt")
    for line in text.splitlines():
        if line.strip().startswith("m_EditorVersion:"):
            return line.split(":", 1)[1].strip()
    return "n/a"


def read_go_version(path: Path) -> str:
    text = read_text(path)
    for line in text.splitlines():
        if line.strip().startswith("go "):
            return line.strip().split(maxsplit=1)[1]
    return "n/a"


def read_csproj_target_framework(project_root: Path) -> str:
    for path in project_root.glob("*.csproj"):
        text = read_text(path)
        match = re.search(r"<TargetFramework>([^<]+)</TargetFramework>", text)
        if match:
            return match.group(1)
        match = re.search(r"<TargetFrameworks>([^<]+)</TargetFrameworks>", text)
        if match:
            return match.group(1)
    return "n/a"


def read_pyproject_version(path: Path) -> str:
    text = read_text(path)
    match = re.search(r"(?m)^version\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1) if match else "n/a"


def read_package_version(path: Path) -> str:
    payload = read_json_object(path)
    return str(payload.get("version") or "n/a")


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def package_dependencies(package: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = package.get(key)
        if isinstance(section, dict):
            merged.update(section)
    return merged


def detect_web_framework(dependencies: dict[str, Any]) -> str | None:
    names = {str(name).lower() for name in dependencies}
    for framework, package_names in FRAMEWORK_PACKAGE_NAMES.items():
        if any(name in names for name in package_names):
            return framework
    return None


def find_schema_locators(workspace_root: Path, project_root: Path) -> list[str]:
    patterns = ["*.proto", "*openapi*.json", "*openapi*.yaml", "*openapi*.yml", "*.graphql"]
    result: list[str] = []
    for pattern in patterns:
        result.extend(
            relative(workspace_root, path)
            for path in project_root.rglob(pattern)
            if is_small_schema_path(path)
        )
    return sorted(unique(result))[:20]


def is_small_schema_path(path: Path) -> bool:
    blocked = {".git", ".codex", "node_modules", "dist", "bin", "obj", "__pycache__"}
    return not any(part in blocked for part in path.parts)


def existing_rel(workspace_root: Path, base: Path, names: list[str]) -> list[str]:
    return [relative(workspace_root, base / name) for name in names if (base / name).exists()]


def relative(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
    except (OSError, RuntimeError, ValueError):
        return str(path).replace("\\", "/")


def path_in_project(path: str, cwd: str) -> bool:
    normalized_path = normalize_path(path)
    normalized_cwd = normalize_path(cwd)
    if normalized_cwd in {"", "."}:
        return True
    comparable_path = normalized_path.casefold()
    comparable_cwd = normalized_cwd.casefold()
    return comparable_path == comparable_cwd or comparable_path.startswith(f"{comparable_cwd}/")


def normalize_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip().strip("/")
    while text.startswith("./"):
        text = text[2:]
    return text or "."


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


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


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
