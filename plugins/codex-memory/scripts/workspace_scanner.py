from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


WORKSPACE_CONFIG = ".codex/harness/workspace-routing.json"
GAME_CLIENT_CONFIG = ".codex/harness/game-client.json"
SKIP_DIRS = {
    ".git",
    ".codex",
    ".idea",
    ".vscode",
    "__pycache__",
    "Library",
    "Temp",
    "Logs",
    "obj",
    "node_modules",
    "dist",
}
PROJECT_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


@dataclass
class ProjectCandidate:
    id: str
    path: str
    cwd: str
    domain: str
    confidence: float
    signals: list[str] = field(default_factory=list)
    source: str = "scanner"
    engine: str | None = None
    language: str | None = None
    framework: str | None = None
    verification_cwd: str | None = None
    rules: list[str] = field(default_factory=list)
    verification_profiles: dict[str, str] = field(default_factory=dict)
    memory_binding: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value not in (None, [], {})}


def scan_workspace(workspace_root: Path, max_depth: int = 2) -> dict[str, Any]:
    root = workspace_root.resolve()
    config = load_workspace_config(root)
    projects = configured_projects(root, config)
    seen_paths = {project.cwd.replace("\\", "/").strip("/") for project in projects}

    for candidate in iter_candidate_dirs(root, max_depth=max_depth):
        detected = detect_project(root, candidate)
        if detected is None:
            continue
        normalized = detected.cwd.replace("\\", "/").strip("/")
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        projects.append(detected)

    source = "scanner"
    if config and projects:
        source = "merged"
    elif config:
        source = "explicit_config"

    return {
        "version": 1,
        "workspace": {
            "name": config.get("workspace", {}).get("name") if config else root.name,
            "root": str(root),
            "source": source,
        },
        "projects": [project.to_json() for project in projects],
        "config_path": str(root / WORKSPACE_CONFIG),
        "config_loaded": bool(config),
    }


def load_workspace_config(root: Path) -> dict[str, Any]:
    path = root / WORKSPACE_CONFIG
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Workspace routing config root must be an object: {path}")
    return value


def configured_projects(root: Path, config: dict[str, Any]) -> list[ProjectCandidate]:
    raw_projects = config.get("projects") if isinstance(config.get("projects"), list) else []
    projects: list[ProjectCandidate] = []
    for item in raw_projects:
        if not isinstance(item, dict):
            continue
        project_id = str(item.get("id") or "").strip()
        path = normalize_config_path(root, str(item.get("path") or item.get("cwd") or ""))
        cwd = normalize_config_path(root, str(item.get("cwd") or path or ""))
        has_verification_cwd = bool(str(item.get("verification_cwd") or "").strip())
        verification_cwd = normalize_config_path(root, str(item.get("verification_cwd") or ""))
        domain = str(item.get("domain") or "unknown").strip()
        if not project_id or not cwd or has_verification_cwd and verification_cwd is None:
            continue
        profiles = configured_verification_profiles(root, cwd, domain, item)
        projects.append(
            ProjectCandidate(
                id=project_id,
                path=path or cwd,
                cwd=cwd,
                domain=domain,
                confidence=1.0,
                signals=[relative(root, root / WORKSPACE_CONFIG)],
                source="explicit_config",
                engine=_optional_str(item.get("engine")),
                language=_optional_str(item.get("language")),
                framework=_optional_str(item.get("framework")),
                verification_cwd=verification_cwd or None,
                rules=string_list(item.get("rules")),
                verification_profiles=profiles,
                memory_binding=runtime_memory_binding(item.get("memory_binding"), project_id),
            )
        )
    return projects


def configured_verification_profiles(root: Path, cwd: str, domain: str, item: dict[str, Any]) -> dict[str, str]:
    profiles: dict[str, str] = {}
    if domain == "game_client":
        path = (root / cwd).resolve(strict=False) if cwd != "." else root.resolve(strict=False)
        profiles.update(game_client_profiles(root, path, cwd, include_local=path == root.resolve(strict=False)))
    profiles.update({str(key): str(value) for key, value in dict_value(item.get("verification_profiles")).items()})
    return {key: value for key, value in profiles.items() if value.strip()}


def runtime_memory_binding(value: Any, project_id: str) -> dict[str, Any]:
    binding = dict_value(value)
    if not binding:
        return {}
    allowed = {"storage_scope", "semantic_scope", "project_id", "shared_memory_allowed"}
    runtime_binding = {key: binding[key] for key in allowed if key in binding}
    runtime_binding.setdefault("storage_scope", "project")
    runtime_binding.setdefault("semantic_scope", "project")
    runtime_binding.setdefault("project_id", project_id)
    return runtime_binding


def iter_candidate_dirs(root: Path, max_depth: int) -> list[Path]:
    candidates = [root]
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        try:
            children = sorted(path for path in current.iterdir() if path.is_dir())
        except OSError:
            continue
        for child in children:
            if child.name in SKIP_DIRS or child.name.startswith(".") and child.name != ".github":
                continue
            candidates.append(child)
            queue.append((child, depth + 1))
    return candidates


def detect_project(root: Path, path: Path) -> ProjectCandidate | None:
    detectors = [
        detect_unity,
        detect_laya,
        detect_cocos,
        detect_game_server,
        detect_backoffice_web,
        detect_design_docs,
        detect_art_pipeline,
        detect_build_release,
        detect_workspace_meta,
    ]
    matches = [item for detector in detectors if (item := detector(root, path)) is not None]
    if not matches:
        return None
    return select_project_match(root, path, matches)


def select_project_match(root: Path, path: Path, matches: list[ProjectCandidate]) -> ProjectCandidate:
    if path.resolve() == root.resolve():
        business = [item for item in matches if item.domain not in {"workspace_meta", "build_release"}]
        if business:
            return sorted(business, key=lambda item: item.confidence, reverse=True)[0]
        workspace_meta = next((item for item in matches if item.domain == "workspace_meta"), None)
        if workspace_meta is not None:
            return workspace_meta
    return sorted(matches, key=lambda item: item.confidence, reverse=True)[0]


def detect_unity(root: Path, path: Path) -> ProjectCandidate | None:
    signals = existing(root, path, ["Assets", "ProjectSettings", "Packages/manifest.json"])
    if len(signals) < 2:
        return None
    return candidate(root, path, "game_client", 0.95, signals, engine="unity")


def detect_laya(root: Path, path: Path) -> ProjectCandidate | None:
    signals = existing(root, path, [".laya", "bin", "src", "release"])
    package = path / "package.json"
    package_has_laya = package_has_laya_metadata(package)
    if package_has_laya:
        signals.append(relative(root, package))
    if not (path / ".laya").exists() and not package_has_laya:
        return None
    if len(signals) < 2:
        return None
    return candidate(root, path, "game_client", 0.86, signals, engine="laya")


def package_has_laya_metadata(package_json: Path) -> bool:
    try:
        payload = json.loads(read_small_text(package_json, max_chars=20000))
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    name = str(payload.get("name") or "")
    if "laya" in {part for part in re.split(r"[^a-z0-9]+", name.lower()) if part}:
        return True
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        dependencies = payload.get(section)
        if isinstance(dependencies, dict) and any(is_laya_package_name(str(item)) for item in dependencies):
            return True
    return False


def is_laya_package_name(value: str) -> bool:
    lowered = value.lower()
    return lowered in {"laya", "layaair", "layaair-cmd", "layaair2-cmd"} or lowered.startswith("@laya/")


def detect_cocos(root: Path, path: Path) -> ProjectCandidate | None:
    signals = existing(root, path, ["assets", "settings", "profiles", "project.json"])
    package = path / "package.json"
    if package.exists() and "cocos" in read_small_text(package).lower():
        signals.append(relative(root, package))
    if len(signals) < 2:
        return None
    return candidate(root, path, "game_client", 0.84, signals, engine="cocos")


def detect_game_server(root: Path, path: Path) -> ProjectCandidate | None:
    signals = existing(root, path, ["go.mod", "pom.xml", "cmd", "proto", "api"])
    csproj = list(path.glob("*.csproj"))
    if csproj:
        signals.append(relative(root, csproj[0]))
    if "server" not in path.name.lower() and len(signals) < 2:
        return None
    if not signals:
        return None
    language = "go" if (path / "go.mod").exists() else None
    return candidate(root, path, "game_server", 0.82, signals, language=language)


def detect_backoffice_web(root: Path, path: Path) -> ProjectCandidate | None:
    name = path.name.lower()
    signals = existing(root, path, ["package.json", "src/views", "src/router", "vite.config.ts"])
    if name not in {"admin", "gm", "ops", "dashboard", "backoffice"} and len(signals) < 2:
        return None
    if not signals:
        return None
    framework = detect_framework(path / "package.json")
    return candidate(root, path, "backoffice_web", 0.78, signals, framework=framework)


def detect_design_docs(root: Path, path: Path) -> ProjectCandidate | None:
    name = path.name.lower()
    if name not in {"docs", "design", "gdd", "策划"}:
        return None
    md_files = list(path.glob("*.md"))[:2]
    signals = [relative(root, item) for item in md_files] or [relative(root, path)]
    return candidate(root, path, "design_docs", 0.72, signals)


def detect_art_pipeline(root: Path, path: Path) -> ProjectCandidate | None:
    name = path.name.lower()
    signals = existing(root, path, ["Art", "Spine", "Textures", "Shaders", "Effects"])
    if name in {"art", "assets-art", "asset-pipeline"}:
        signals.append(relative(root, path))
    if not signals:
        return None
    return candidate(root, path, "art_pipeline", 0.7, signals)


def detect_build_release(root: Path, path: Path) -> ProjectCandidate | None:
    signals = existing(root, path, [".github", ".gitlab-ci.yml", "Jenkinsfile", "ci", "release"])
    if not signals:
        return None
    return candidate(root, path, "build_release", 0.68, signals)


def detect_workspace_meta(root: Path, path: Path) -> ProjectCandidate | None:
    if path.resolve() != root.resolve():
        return None
    signals = existing(root, path, ["AGENTS.md", "README.md", "pyproject.toml", "scripts", "plugins"])
    if len(signals) < 2:
        return None
    return candidate(root, path, "workspace_meta", 0.66, signals)


def candidate(
    root: Path,
    path: Path,
    domain: str,
    confidence: float,
    signals: list[str],
    *,
    engine: str | None = None,
    language: str | None = None,
    framework: str | None = None,
) -> ProjectCandidate:
    cwd = relative(root, path) or "."
    project_id = make_project_id(domain, path.name if cwd != "." else root.name, engine)
    profiles = game_client_profiles(root, path, cwd, include_local=path.resolve() == root.resolve()) if domain == "game_client" else {}
    return ProjectCandidate(
        id=project_id,
        path=cwd,
        cwd=cwd,
        domain=domain,
        confidence=confidence,
        signals=signals,
        engine=engine,
        language=language,
        framework=framework,
        verification_profiles=profiles,
    )


def game_client_profiles(root: Path, path: Path, cwd: str, *, include_local: bool) -> dict[str, str]:
    local_config = path / GAME_CLIENT_CONFIG
    candidates = ([local_config] if include_local else []) + [root / GAME_CLIENT_CONFIG]
    seen: set[str] = set()
    for config_path in candidates:
        key = config_path.resolve(strict=False).as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        payload = read_json_object(config_path)
        if not payload:
            continue
        project_cwd = normalize_config_path(root, str(payload.get("project_cwd") or ""))
        is_local = include_local and config_path.resolve(strict=False) == local_config.resolve(strict=False)
        if not (project_cwd == cwd or is_local and project_cwd in {"", "."}):
            continue
        profiles = dict_value(payload.get("verification_profiles"))
        if profiles:
            return {str(key): str(value) for key, value in profiles.items() if str(value).strip()}
    return {}


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def existing(root: Path, base: Path, names: list[str]) -> list[str]:
    return [relative(root, base / name) for name in names if (base / name).exists()]


def relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def normalize_config_path(root: Path, value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return ""
    path = Path(raw)
    candidate_path = path if path.is_absolute() else root / raw
    try:
        normalized = candidate_path.resolve(strict=False).relative_to(root.resolve()).as_posix().strip("/")
    except (OSError, RuntimeError, ValueError):
        return None
    return normalized or "."


def make_project_id(domain: str, name: str, engine: str | None) -> str:
    prefix = engine if domain == "game_client" and engine else domain
    value = PROJECT_ID_RE.sub("-", f"{prefix}-{name}".strip("-")).strip("-").lower()
    return value or "unknown-project"


def read_small_text(path: Path, max_chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return ""


def detect_framework(package_json: Path) -> str | None:
    dependencies = package_dependency_names(read_json_object(package_json))
    if "next" in dependencies:
        return "next"
    if "vue" in dependencies:
        return "vue"
    if "react" in dependencies:
        return "react"
    if "angular" in dependencies or "@angular/core" in dependencies:
        return "angular"
    return None


def package_dependency_names(package: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        dependencies = package.get(section)
        if isinstance(dependencies, dict):
            names.update(str(name).lower() for name in dependencies)
    return names


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only workspace scanner for Codex Memory Harness.")
    parser.add_argument("--workspace-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--max-depth", dest="root_max_depth", type=int)
    parser.set_defaults(command_max_depth=None)
    subparsers = parser.add_subparsers(dest="command")
    scan = subparsers.add_parser("scan")
    scan.add_argument("--max-depth", dest="command_max_depth", type=int)
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--max-depth", dest="command_max_depth", type=int)
    args = parser.parse_args()

    command = args.command or "doctor"
    max_depth = args.command_max_depth if args.command_max_depth is not None else args.root_max_depth
    inventory = scan_workspace(Path(args.workspace_root), max_depth=max(max_depth if max_depth is not None else 2, 0))
    result = {
        "ok": True,
        "mode": command,
        "inventory": inventory,
        "recommendations": recommendations(inventory),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def recommendations(inventory: dict[str, Any]) -> list[str]:
    items: list[str] = []
    if not inventory.get("config_loaded"):
        items.append("可选：创建 .codex/harness/workspace-routing.json 固化项目路由配置。")
    projects = inventory.get("projects") if isinstance(inventory.get("projects"), list) else []
    if not projects:
        items.append("未识别到子项目；可通过显式 workspace-routing.json 配置项目。")
    return items


if __name__ == "__main__":
    raise SystemExit(main())
