from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from workspace_template_commands import mvn_argv, npm_argv, python_argv


COMMANDS_FILE = ".codex/harness/commands.json"
PROFILE_FILE = ".codex/harness/project_profile.json"
WORKSPACE_ROUTING_FILE = ".codex/harness/workspace-routing.json"
SCHEMA_URI = "local://codex-memory-harness/schemas/workspace_routing_config.schema.json"
DOMAINS = ("game_server", "backoffice_web", "design_docs", "art_pipeline")
SERVER_LANGUAGES = ("go", "java", "csharp", "node")
WEB_FRAMEWORKS = ("vue", "react", "next", "angular", "generic")
ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def build_template(
    domain: str,
    project_cwd: str,
    prefix: str,
    *,
    project_id: str | None = None,
    language: str | None = None,
    framework: str | None = None,
) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise ValueError(f"Unsupported domain: {domain}")
    fallback_prefix = default_prefix(domain, project_cwd)
    prefix = normalize_id(prefix or fallback_prefix, fallback=fallback_prefix)
    project_id = normalize_id(
        project_id or default_project_id(domain, prefix),
        fallback=default_project_id(domain, prefix),
        hash_invalid=bool(project_id),
    )
    builder = {
        "game_server": server_template,
        "backoffice_web": web_template,
        "design_docs": docs_template,
        "art_pipeline": art_template,
    }[domain]
    commands, profiles, project = builder(project_cwd, prefix, project_id, language, framework)
    return {"commands": commands, "profiles": profiles, "workspace_project": project}


def server_template(
    project_cwd: str,
    prefix: str,
    project_id: str,
    language: str | None,
    framework: str | None,
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, Any]]:
    selected = language or "go"
    if selected not in SERVER_LANGUAGES:
        raise ValueError(f"Unsupported game_server language: {selected}")
    unit, integration, release = server_commands(selected, prefix, project_cwd)
    commands = {item["id"]: command_payload(item, project_cwd) for item in (unit, integration, release)}
    profiles = {
        f"{prefix}_quick": [unit["id"]],
        f"{prefix}_integration": [integration["id"]],
        f"{prefix}_release": [unit["id"], release["id"]],
    }
    project = project_config(
        project_id,
        project_cwd,
        "game_server",
        ["workspace/base", "game_server/base", f"server/{selected}"],
        {"quick": f"{prefix}_quick", "integration": f"{prefix}_integration", "release": f"{prefix}_release"},
        language=selected,
    )
    return commands, profiles, project


def web_template(
    project_cwd: str,
    prefix: str,
    project_id: str,
    language: str | None,
    framework: str | None,
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, Any]]:
    selected = framework or "vue"
    if selected not in WEB_FRAMEWORKS:
        raise ValueError(f"Unsupported backoffice_web framework: {selected}")
    items = [
        cmd(f"{prefix}_lint", "Run frontend lint checks.", npm_argv("run", "lint"), 180),
        cmd(f"{prefix}_test", "Run frontend tests.", npm_argv("test"), 240),
        cmd(f"{prefix}_build", "Build the backoffice frontend.", npm_argv("run", "build"), 600),
    ]
    commands = {item["id"]: command_payload(item, project_cwd) for item in items}
    profiles = {
        f"{prefix}_quick": [items[0]["id"], items[1]["id"]],
        f"{prefix}_release": [items[0]["id"], items[1]["id"], items[2]["id"]],
    }
    project = project_config(
        project_id,
        project_cwd,
        "backoffice_web",
        ["workspace/base", "backoffice/base", f"web/{selected}" if selected != "generic" else "web/base"],
        {"quick": f"{prefix}_quick", "release": f"{prefix}_release"},
        framework=selected,
    )
    return commands, profiles, project


def docs_template(
    project_cwd: str,
    prefix: str,
    project_id: str,
    language: str | None,
    framework: str | None,
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, Any]]:
    utf8 = cmd(f"{prefix}_markdown_utf8", "Read all Markdown files as UTF-8.", python_argv(DOCS_UTF8_SCRIPT), 120)
    links = cmd(f"{prefix}_local_link_check", "Check local Markdown links.", python_argv(DOCS_LINK_SCRIPT), 120)
    commands = {item["id"]: command_payload(item, project_cwd) for item in (utf8, links)}
    profiles = {f"{prefix}_quick": [utf8["id"], links["id"]]}
    project = project_config(
        project_id,
        project_cwd,
        "design_docs",
        ["workspace/base", "docs/design"],
        {"quick": f"{prefix}_quick"},
        semantic_scope="workspace",
    )
    return commands, profiles, project


def art_template(
    project_cwd: str,
    prefix: str,
    project_id: str,
    language: str | None,
    framework: str | None,
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, Any]]:
    manifest = cmd(f"{prefix}_asset_manifest_check", "Summarize asset files and manifest presence.", python_argv(ART_MANIFEST_SCRIPT), 180)
    release = cmd(f"{prefix}_asset_release_check", "Reject zero-byte asset files before release.", python_argv(ART_RELEASE_SCRIPT), 240)
    commands = {item["id"]: command_payload(item, project_cwd) for item in (manifest, release)}
    profiles = {
        f"{prefix}_quick": [manifest["id"]],
        f"{prefix}_release": [manifest["id"], release["id"]],
    }
    project = project_config(
        project_id,
        project_cwd,
        "art_pipeline",
        ["workspace/base", "art_pipeline/base", "game_client/assets"],
        {"quick": f"{prefix}_quick", "release": f"{prefix}_release"},
    )
    return commands, profiles, project


def init_template(
    project_root: Path,
    domain: str,
    project_cwd: str,
    prefix: str,
    *,
    overwrite: bool,
    project_id: str | None = None,
    language: str | None = None,
    framework: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    project_cwd = normalize_project_cwd(project_root, project_cwd)
    template = build_template(domain, project_cwd, prefix, project_id=project_id, language=language, framework=framework)
    commands_path = project_root / COMMANDS_FILE
    profile_path = project_root / PROFILE_FILE
    workspace_path = project_root / WORKSPACE_ROUTING_FILE
    commands_payload = read_json(commands_path) or {"version": 1, "commands": {}}
    profile_payload = read_json(profile_path) or {"version": 1, "verification": {}}
    workspace_payload = read_json(workspace_path) or workspace_config(project_root.name)
    actions: list[dict[str, str]] = []

    reject_colliding_map(commands_payload.setdefault("commands", {}), template["commands"], overwrite, "command")
    reject_colliding_map(profile_payload.setdefault("verification", {}), template["profiles"], overwrite, "profile")
    merge_map(commands_payload.setdefault("commands", {}), template["commands"], overwrite, "command", actions)
    merge_map(profile_payload.setdefault("verification", {}), template["profiles"], overwrite, "profile", actions)
    project_id_written = merge_project(workspace_payload.setdefault("projects", []), template["workspace_project"], overwrite, actions)
    write_json(commands_path, commands_payload)
    write_json(profile_path, profile_payload)
    write_json(workspace_path, workspace_payload)
    return {"ok": True, "domain": domain, "project_cwd": project_cwd, "project_id": project_id_written, "actions": actions}


def merge_map(target: dict[str, Any], source: dict[str, Any], overwrite: bool, kind: str, actions: list[dict[str, str]]) -> None:
    for key, value in source.items():
        if overwrite or key not in target:
            target[key] = value
            actions.append({"action": f"write_{kind}", "id": key})
        else:
            actions.append({"action": f"keep_{kind}", "id": key})


def reject_colliding_map(target: dict[str, Any], source: dict[str, Any], overwrite: bool, kind: str) -> None:
    if overwrite:
        return
    collisions = [key for key, value in source.items() if key in target and target[key] != value]
    if collisions:
        raise ValueError(f"{kind} id collision for distinct template payload: {', '.join(collisions)}")


def merge_project(projects: list[Any], project: dict[str, Any], overwrite: bool, actions: list[dict[str, str]]) -> str:
    for index, item in enumerate(projects):
        if isinstance(item, dict) and item.get("id") == project["id"]:
            if not same_project_scope(item, project):
                raise ValueError(f"workspace project id collision for distinct project scope: {project['id']}")
            if overwrite:
                projects[index] = project
                actions.append({"action": "write_workspace_project", "id": project["id"]})
            else:
                actions.append({"action": "keep_workspace_project", "id": project["id"]})
            return str(project["id"])
    for index, item in enumerate(projects):
        if isinstance(item, dict) and same_project_scope(item, project):
            existing_id = str(item.get("id") or project["id"])
            if overwrite:
                replacement = dict(project)
                replacement["id"] = existing_id
                if isinstance(replacement.get("memory_binding"), dict):
                    replacement["memory_binding"] = dict(replacement["memory_binding"])
                    replacement["memory_binding"]["project_id"] = existing_id
                projects[index] = replacement
                actions.append({"action": "write_workspace_project", "id": existing_id})
            else:
                actions.append({"action": "keep_workspace_project", "id": existing_id})
            return existing_id
    projects.append(project)
    actions.append({"action": "write_workspace_project", "id": project["id"]})
    return str(project["id"])


def same_project_scope(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if str(left.get("domain") or "") != str(right.get("domain") or ""):
        return False
    left_paths = project_paths(left)
    right_paths = project_paths(right)
    return bool(left_paths.intersection(right_paths))


def project_paths(project: dict[str, Any]) -> set[str]:
    return {
        normalized_project_path(value)
        for value in (project.get("cwd"), project.get("path"))
        if str(value or "").strip()
    }


def normalized_project_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    parts = [part for part in text.strip("/").split("/") if part and part != "."]
    return "/".join(parts) or "."


def normalize_project_cwd(project_root: Path, value: str) -> str:
    raw = str(value or "").strip() or "."
    path = Path(raw)
    candidate = path if path.is_absolute() else project_root / raw
    try:
        normalized = candidate.resolve(strict=False).relative_to(project_root.resolve()).as_posix().strip("/")
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"project_cwd must stay inside project_root: {value}") from exc
    return normalized or "."


def project_config(
    project_id: str,
    project_cwd: str,
    domain: str,
    rules: list[str],
    profiles: dict[str, str],
    *,
    language: str | None = None,
    framework: str | None = None,
    semantic_scope: str = "project",
) -> dict[str, Any]:
    payload = {
        "id": project_id,
        "path": project_cwd,
        "cwd": project_cwd,
        "domain": domain,
        "language": language,
        "framework": framework,
        "rules": list(dict.fromkeys(rules)),
        "verification_profiles": profiles,
        "memory_binding": {
            "storage_scope": "project",
            "semantic_scope": semantic_scope,
            "project_id": project_id,
            "shared_memory_allowed": True,
        },
    }
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def workspace_config(name: str) -> dict[str, Any]:
    return {
        "$schema": SCHEMA_URI,
        "version": 1,
        "workspace": {"name": name},
        "routing_priority": ["user_explicit", "subagent_explicit", "explicit_config", "scanner", "fallback"],
        "subagent_runtime_policy": {
            "execution_model": "host_subagent_required",
            "autostart": True,
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Workspace policy is standing user authorization: implementation tasks require specified-role Harness SubAgent dispatch when the host supports it; if the host cannot dispatch, record a blocking downgrade instead of asking the user to repeat the SubAgent request.",
        },
        "diagnostic_logging": {"default_allowed": False, "release_must_be_disabled": True, "allowed_scopes": ["flow", "state", "validation"]},
        "projects": [],
        "fallback": {"rules": ["workspace/generic"], "verification_profiles": ["primary"]},
    }


def server_commands(language: str, prefix: str, project_cwd: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    mapping = {
        "go": (["go", "test", "./..."], ["go", "test", "./...", "-tags=integration"], ["go", "vet", "./..."]),
        "java": (mvn_argv("test"), mvn_argv("verify", "-DskipITs=false"), mvn_argv("verify")),
        "csharp": (["dotnet", "test"], ["dotnet", "test", "--filter", "Category=Integration"], ["dotnet", "build", "-c", "Release"]),
        "node": (npm_argv("test"), npm_argv("run", "test:integration"), npm_argv("run", "build")),
    }
    unit, integration, release = mapping[language]
    return (
        cmd(f"{prefix}_{language}_unit", f"Run {language} server unit tests.", unit, 240),
        cmd(f"{prefix}_{language}_integration", f"Run {language} server integration tests.", integration, 600),
        cmd(f"{prefix}_{language}_release", f"Run {language} server release checks.", release, 600),
    )


def cmd(command_id: str, description: str, argv: list[str], timeout: int) -> dict[str, Any]:
    return {"id": command_id, "description": description, "argv": argv, "timeout_seconds": timeout}


def command_payload(item: dict[str, Any], cwd: str) -> dict[str, Any]:
    return {
        "description": item["description"],
        "argv": item["argv"],
        "cwd": cwd,
        "timeout_seconds": item["timeout_seconds"],
        "touched_paths": [cwd],
    }


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_id(value: str, *, fallback: str, hash_invalid: bool = False) -> str:
    raw = value.strip()
    normalized = ID_RE.sub("-", raw).strip("-._").lower()
    if normalized:
        return normalized
    if not raw or not hash_invalid:
        return fallback
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{fallback}-{digest}"


def default_prefix(domain: str, project_cwd: str | None = None) -> str:
    base = {"game_server": "server", "backoffice_web": "admin", "design_docs": "docs", "art_pipeline": "art"}[domain]
    if not project_cwd:
        return base
    normalized_path = normalized_project_path(project_cwd)
    if normalized_path == ".":
        return base
    suffix = normalize_id(normalized_path.replace("/", "-"), fallback="path", hash_invalid=True)
    if suffix == base or suffix.startswith(f"{base}-"):
        return suffix
    return f"{base}-{suffix}"


def default_project_id(domain: str, prefix: str) -> str:
    return {"game_server": f"{prefix}-game", "backoffice_web": f"{prefix}-web", "design_docs": f"{prefix}-docs", "art_pipeline": f"{prefix}-pipeline"}[domain]


SKIP_DIR_NAMES = "{'.codex','node_modules','dist','build','coverage','.git','.next','.vite','.turbo','__pycache__','Library','Temp','Logs','obj'}"
FILE_SCAN_COMMON_SCRIPT = (
    "from pathlib import Path\n"
    f"SKIP={SKIP_DIR_NAMES}\n"
    "def source_files(pattern='*'):\n"
    " for p in Path('.').rglob(pattern):\n"
    "  if any(part in SKIP for part in p.parts): continue\n"
    "  if p.is_file(): yield p\n"
)
DOCS_COMMON_SCRIPT = FILE_SCAN_COMMON_SCRIPT + "def markdown_files():\n yield from source_files('*.md')\n"
DOCS_UTF8_SCRIPT = (
    DOCS_COMMON_SCRIPT
    + "files=list(markdown_files())\n"
    + "[p.read_text(encoding='utf-8') for p in files]\n"
    + "print(f'checked {len(files)} markdown files')"
)
DOCS_LINK_SCRIPT = (
    "import sys\n"
    + DOCS_COMMON_SCRIPT
    + "def link_targets(text):\n"
    + " i=0\n"
    + " while True:\n"
    + "  start=text.find('](', i)\n"
    + "  if start<0: return\n"
    + "  j=start+2; depth=0; target=[]; escape=False\n"
    + "  while j < len(text):\n"
    + "   ch=text[j]\n"
    + "   if escape:\n"
    + "    target.append(ch); escape=False; j+=1; continue\n"
    + "   if ch=='\\\\':\n"
    + "    escape=True; j+=1; continue\n"
    + "   if ch=='(':\n"
    + "    depth+=1\n"
    + "   elif ch==')':\n"
    + "    if depth==0: break\n"
    + "    depth-=1\n"
    + "   target.append(ch); j+=1\n"
    + "  if j < len(text): yield ''.join(target)\n"
    + "  i=j+1\n"
    + "def target_path(raw):\n"
    + " raw=raw.strip()\n"
    + " if raw.startswith('<') and '>' in raw: return raw[1:raw.find('>')].split('#',1)[0].strip()\n"
    + " raw=raw.split('#',1)[0].strip()\n"
    + " quote=None; escape=False; depth=0\n"
    + " for idx,ch in enumerate(raw):\n"
    + "  if escape:\n"
    + "   escape=False; continue\n"
    + "  if ch=='\\\\':\n"
    + "   escape=True; continue\n"
    + "  if quote:\n"
    + "   if ch==quote: quote=None\n"
    + "   continue\n"
    + "  if ch in {'\"',\"'\"}:\n"
    + "   quote=ch; continue\n"
    + "  if ch=='(':\n"
    + "   depth+=1; continue\n"
    + "  if ch==')' and depth>0:\n"
    + "   depth-=1; continue\n"
    + "  if ch.isspace() and depth==0:\n"
    + "   return raw[:idx].strip()\n"
    + " return raw\n"
    + "missing=[]\n"
    + "for p in markdown_files():\n"
    + " t=p.read_text(encoding='utf-8')\n"
    + " for raw in link_targets(t):\n"
    + "  target=target_path(raw)\n"
    + "  if not target or '://' in target or target.startswith(('mailto:','tel:')): continue\n"
    + "  if not (p.parent/target).exists(): missing.append(f'{p}:{raw}')\n"
    + "if missing:\n"
    + " print('\\n'.join(missing[:20])); sys.exit(1)\n"
    + "print('local markdown links ok')"
)
ART_MANIFEST_SCRIPT = FILE_SCAN_COMMON_SCRIPT + "files=list(source_files())\nmanifests=[p for p in files if p.name.lower() in {'asset_manifest.json','manifest.json','addressables.json'}]\nprint(f'asset files={len(files)} manifests={len(manifests)}')"
ART_RELEASE_SCRIPT = "import sys\n" + FILE_SCAN_COMMON_SCRIPT + "files=list(source_files())\nzero=[str(p) for p in files if p.stat().st_size==0]\nif zero:\n print('zero-byte asset files:\\n'+'\\n'.join(zero[:20])); sys.exit(1)\nprint(f'asset release check ok: {len(files)} files')"


def main_with_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate workspace business project templates.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("command", choices=["init", "template"])
    parser.add_argument("--domain", required=True, choices=DOMAINS)
    parser.add_argument("--project-cwd", default=".")
    parser.add_argument("--profile-prefix")
    parser.add_argument("--project-id")
    parser.add_argument("--language", choices=SERVER_LANGUAGES)
    parser.add_argument("--framework", choices=WEB_FRAMEWORKS)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    project_cwd = normalize_project_cwd(project_root, args.project_cwd)
    prefix = args.profile_prefix or default_prefix(args.domain, project_cwd)
    if args.command == "template":
        result = {"ok": True, "template": build_template(args.domain, project_cwd, prefix, project_id=args.project_id, language=args.language, framework=args.framework)}
    else:
        result = init_template(project_root, args.domain, project_cwd, prefix, overwrite=args.overwrite, project_id=args.project_id, language=args.language, framework=args.framework)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return main_with_args()


if __name__ == "__main__":
    raise SystemExit(main())
