from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from bootstrap_openspec import ensure_default_openspec_upstream
from init_storage import PROJECT_MARKERS, ensure_storage_layout, resolve_storage_paths
from codex_config_status import inspect_codex_config
from custom_agents_templates import ensure_project_agents
from official_memory_status import codex_home, inspect_official_memory


PLUGIN_NAME = "codex-memory"
HOME = Path.home()
HOME_PLUGIN = HOME / "plugins" / PLUGIN_NAME
HOME_AGENTS = HOME / ".codex" / "AGENTS.md"
HOME_MARKETPLACE = HOME / ".agents" / "plugins" / "marketplace.json"
GLOBAL_MEMORY = HOME / ".codex" / "codex-memory-harness" / "memories"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_OUTPUT_CHARS = 1200
PROJECT_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
SHARED_MEMORY_DIRS = ("decisions", "facts", "workflows", "routes")
SHARED_MEMORY_README = """# Codex Shared Memory

This directory is the reviewable project shared memory layer.

Use it for stable, non-sensitive project facts, decisions, workflows, and routing summaries.
Do not put raw task state, logs, credentials, production endpoints, private repository URLs, or generated databases here.

Suggested folders:

- `decisions/`: accepted or deprecated architecture and product decisions.
- `facts/`: stable module boundaries, ownership, and implementation facts.
- `workflows/`: verification, release, rollback, and operational workflows.
- `routes/`: workspace routing summaries and project/domain scope notes.

Each shared memory entry should be a small Markdown file with front matter matching `schemas/shared_memory.schema.json` in the Codex Memory Harness package.
"""
SHARED_MEMORY_INDEX = {
    "version": 1,
    "description": "Reviewable project shared memory index. Rebuild when promote tooling is available.",
    "entries": [],
}
DEFAULT_SUBAGENT_RUNTIME_POLICY = {
    "execution_model": "host_subagent_or_manual",
    "autostart": False,
    "task_types": ["implementation"],
    "risk_levels": ["medium", "high"],
    "reason": (
        "Project policy authorizes Harness SubAgent dispatch for normal implementation tasks "
        "when the host supports it."
    ),
}
WORKSPACE_ROUTING_SCHEMA = "local://codex-memory-harness/schemas/workspace_routing_config.schema.json"


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _contains(path: Path, needle: str) -> bool:
    if not path.exists():
        return False
    return needle in path.read_text(encoding="utf-8", errors="replace")


def _home_agents_path() -> Path:
    if os.environ.get("CODEX_HOME", "").strip():
        return codex_home(HOME) / "AGENTS.md"
    return HOME_AGENTS


def _harness_global_memory_path() -> Path:
    if os.environ.get("CODEX_HOME", "").strip():
        return codex_home(HOME) / "codex-memory-harness" / "memories"
    return GLOBAL_MEMORY


def _has_marketplace_entry(path: Path) -> bool:
    payload = _read_json(path)
    plugins = payload.get("plugins") if isinstance(payload.get("plugins"), list) else []
    return any(item.get("name") == PLUGIN_NAME for item in plugins if isinstance(item, dict))


def _resolve_existing(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return str(path.resolve())
    except OSError:
        return "unresolved"


def _points_to(path: Path, target: Path) -> bool:
    if not path.exists() or not target.exists():
        return False
    try:
        return path.resolve() == target.resolve()
    except OSError:
        return False


def _codexm_argv(script_root: Path, *args: str) -> list[str]:
    posix_launcher = script_root / "codexm.sh"
    if posix_launcher.exists() and os.name != "nt":
        return [
            shutil.which("sh") or "sh",
            str(posix_launcher),
            *args,
        ]
    windows_powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return [
        shutil.which("pwsh") or shutil.which("powershell") or str(windows_powershell),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_root / "codexm.ps1"),
        *args,
    ]


def _find_project_root(start: Path) -> tuple[Path | None, list[str]]:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        matched = [marker for marker in PROJECT_MARKERS if (candidate / marker).exists()]
        if (candidate / ".codex").is_dir():
            matched.append(".codex")
        if matched:
            return candidate, sorted(set(matched))
    return None, []


def _command_config(plugin_root: Path, project_root: Path) -> dict[str, Any]:
    script_root = plugin_root / "scripts"
    return {
        "version": 1,
        "settings": {
            "default_timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
            "max_output_chars": DEFAULT_MAX_OUTPUT_CHARS,
        },
        "commands": {
            "memory_check": {
                "description": "校验全局 codex-memory 插件入口与 marketplace 接入。",
                "command": "codex memory check-install",
                "argv": _codexm_argv(script_root, "memory", "check-install"),
                "timeout_seconds": 60,
                "touched_paths": [
                    str(HOME_PLUGIN),
                    str(HOME_MARKETPLACE),
                ],
            },
            "bootstrap_doctor": {
                "description": "校验当前项目的 bootstrap、memory 与 harness 接入状态。",
                "command": "codex memory doctor",
                "argv": _codexm_argv(script_root, "memory", "doctor"),
                "timeout_seconds": 60,
                "touched_paths": [
                    ".codex/harness/commands.json",
                    ".codex/harness/project_profile.json",
                    ".codex/memories",
                ],
            },
        },
    }


def _profile_config(plugin_root: Path, project_root: Path) -> dict[str, Any]:
    return {
        "version": 1,
        "name": project_root.name,
        "project_root": str(project_root),
        "default_memory_scope": "project",
        "subagent_runtime_policy": dict(DEFAULT_SUBAGENT_RUNTIME_POLICY),
        "harness": {
            "task_spec_dir": ".codex/harness/tasks",
            "artifact_policy": "record structured tool summaries, not raw sensitive output",
            "distillation_policy": "project facts stay project-scoped; cross-project preferences go global",
        },
        "verification": {
            "default_profile": "primary",
            "runner": str(plugin_root / "scripts" / "verification_runner.py"),
            "primary": [
                "memory_check",
                "bootstrap_doctor",
            ],
        },
    }


def _project_id(prefix: str, name: str) -> str:
    normalized_prefix = PROJECT_ID_RE.sub("-", prefix).strip("-._").lower() or "project"
    normalized_name = PROJECT_ID_RE.sub("-", name).strip("-._").lower()
    if not normalized_name:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
        normalized_name = f"project-{digest}"
    return f"{normalized_prefix}-{normalized_name}"


def _workspace_routing_config(project_root: Path) -> dict[str, Any]:
    project_id = _project_id("workspace_meta", project_root.name)
    return {
        "$schema": WORKSPACE_ROUTING_SCHEMA,
        "version": 1,
        "workspace": {
            "name": project_root.name,
        },
        "routing_priority": [
            "user_explicit",
            "subagent_explicit",
            "explicit_config",
            "scanner",
            "fallback",
        ],
        "subagent_runtime_policy": dict(DEFAULT_SUBAGENT_RUNTIME_POLICY),
        "diagnostic_logging": {
            "default_allowed": False,
            "release_must_be_disabled": True,
            "allowed_scopes": [
                "flow",
                "state",
                "validation",
            ],
        },
        "projects": [
            {
                "id": project_id,
                "path": ".",
                "cwd": ".",
                "domain": "workspace_meta",
                "rules": [
                    "workspace/base",
                ],
                "verification_profiles": {
                    "quick": "primary",
                    "release": "primary",
                },
                "memory_binding": {
                    "storage_scope": "project",
                    "semantic_scope": "project",
                    "project_id": project_id,
                    "shared_memory_allowed": True,
                },
            }
        ],
        "fallback": {
            "rules": [
                "workspace/generic",
            ],
            "verification_profiles": [
                "primary",
            ],
        },
    }


def _ensure_file(path: Path, payload: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    if path.exists():
        actions.append({"action": "keep_existing", "path": str(path)})
        return
    _write_json(path, payload)
    actions.append({"action": "create_file", "path": str(path)})


def _ensure_profile_policy(path: Path, actions: list[dict[str, Any]]) -> None:
    if not path.exists():
        return
    try:
        profile = _read_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        actions.append({"action": "skip_invalid_json", "path": str(path)})
        return
    harness = profile.get("harness") if isinstance(profile.get("harness"), dict) else {}
    if isinstance(profile.get("subagent_runtime_policy"), dict) or isinstance(harness.get("subagent_runtime_policy"), dict):
        actions.append({"action": "keep_existing_subagent_runtime_policy", "path": str(path)})
        return
    profile["subagent_runtime_policy"] = dict(DEFAULT_SUBAGENT_RUNTIME_POLICY)
    _write_json(path, profile)
    actions.append({"action": "add_subagent_runtime_policy", "path": str(path)})


def _ensure_text_file(path: Path, content: str, actions: list[dict[str, Any]]) -> None:
    if path.exists():
        actions.append({"action": "keep_existing", "path": str(path)})
        return
    _write_text(path, content)
    actions.append({"action": "create_file", "path": str(path)})


def _ensure_shared_memory_template(project_root: Path, actions: list[dict[str, Any]]) -> None:
    shared_dir = project_root / ".codex" / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    actions.append({"action": "ensure_directory", "path": str(shared_dir)})
    _ensure_text_file(shared_dir / "README.md", SHARED_MEMORY_README, actions)
    _ensure_file(shared_dir / "index.json", SHARED_MEMORY_INDEX, actions)
    for name in SHARED_MEMORY_DIRS:
        directory = shared_dir / name
        directory.mkdir(parents=True, exist_ok=True)
        actions.append({"action": "ensure_directory", "path": str(directory)})
        _ensure_text_file(directory / ".gitkeep", "", actions)


def init_project(project_root: Path, plugin_root: Path, *, sync_openspec_upstream: bool = True) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    layout = ensure_storage_layout(scope="project", cwd=project_root)
    actions.append({"action": "ensure_memory_layout", "path": layout["storage_dir"]})

    harness_dir = project_root / ".codex" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    actions.append({"action": "ensure_directory", "path": str(harness_dir)})
    _ensure_file(harness_dir / "commands.json", _command_config(plugin_root, project_root), actions)
    profile_path = harness_dir / "project_profile.json"
    _ensure_file(profile_path, _profile_config(plugin_root, project_root), actions)
    _ensure_file(harness_dir / "workspace-routing.json", _workspace_routing_config(project_root), actions)
    _ensure_profile_policy(profile_path, actions)
    _ensure_shared_memory_template(project_root, actions)
    ensure_project_agents(project_root, actions)
    if sync_openspec_upstream:
        actions.extend(ensure_default_openspec_upstream(project_root))
    return actions


def inspect_state(cwd: Path, *, init: bool) -> dict[str, Any]:
    plugin_root = _plugin_root()
    start = cwd.resolve()
    project_root, markers = _find_project_root(start)
    if init and project_root and project_root.resolve() == HOME.resolve() and start != project_root.resolve():
        project_root, markers = None, []
    selected_project = project_root or (start if init else None)
    actions: list[dict[str, Any]] = []
    if init and selected_project:
        actions = init_project(selected_project, plugin_root)

    storage = resolve_storage_paths(
        scope="project" if selected_project else "global",
        cwd=selected_project or start,
    )
    project_memory = selected_project / ".codex" / "memories" if selected_project else None
    project_shared = selected_project / ".codex" / "shared" if selected_project else None
    harness_dir = selected_project / ".codex" / "harness" if selected_project else None

    official_memory = inspect_official_memory(HOME)
    codex_config = inspect_codex_config(HOME, plugin_root=plugin_root)
    home_agents = _home_agents_path()
    harness_global_memory = _harness_global_memory_path()

    checks = {
        "home_agents_exists": home_agents.exists(),
        "home_agents_mentions_memory": _contains(home_agents, "Codex Memory"),
        "home_agents_mentions_bootstrap": _contains(home_agents, "codex_bootstrap.py"),
        "home_agents_mentions_cli_entrypoints": _contains(home_agents, "codex memory doctor")
        or _contains(home_agents, "codex_bootstrap.py"),
        "home_plugin_exists": HOME_PLUGIN.exists(),
        "home_plugin_resolved_path": _resolve_existing(HOME_PLUGIN),
        "home_plugin_points_to_current": _points_to(HOME_PLUGIN, plugin_root),
        "home_marketplace_exists": HOME_MARKETPLACE.exists(),
        "home_marketplace_has_entry": _has_marketplace_entry(HOME_MARKETPLACE),
        "plugin_root_exists": plugin_root.exists(),
        "bootstrap_script_exists": (plugin_root / "scripts" / "codex_bootstrap.py").exists(),
        "harness_controller_exists": (plugin_root / "scripts" / "harness_controller.py").exists(),
        "verification_runner_exists": (plugin_root / "scripts" / "verification_runner.py").exists(),
        "global_memory_exists": harness_global_memory.exists(),
        "project_memory_exists": project_memory.exists() if project_memory else False,
        "project_shared_exists": project_shared.exists() if project_shared else False,
        "project_shared_index_exists": (project_shared / "index.json").exists() if project_shared else False,
        "project_commands_exists": (harness_dir / "commands.json").exists() if harness_dir else False,
        "project_profile_exists": (harness_dir / "project_profile.json").exists() if harness_dir else False,
        "project_workspace_routing_exists": (harness_dir / "workspace-routing.json").exists() if harness_dir else False,
    }
    ok = all(
        checks[key]
        for key in [
            "home_agents_exists",
            "home_plugin_exists",
            "home_plugin_points_to_current",
            "home_marketplace_has_entry",
            "bootstrap_script_exists",
            "harness_controller_exists",
            "verification_runner_exists",
        ]
    )
    if selected_project:
        ok = ok and checks["project_memory_exists"] and checks["project_commands_exists"] and checks["project_profile_exists"]

    recommendations = []
    if not checks["home_agents_mentions_cli_entrypoints"]:
        recommendations.append("更新全局 AGENTS.md，加入 codex memory doctor/init 启动自检入口。")
    if checks["home_plugin_exists"] and not checks["home_plugin_points_to_current"]:
        recommendations.append("重新运行当前包安装器；默认会让 home plugin 更新到当前插件版本。")
    if not selected_project:
        recommendations.append("当前目录未识别为项目；如需项目级记忆，请在项目根目录运行 codex memory init。")
    elif not checks["project_commands_exists"] or not checks["project_profile_exists"]:
        recommendations.append("运行 codex memory init 生成缺失的 .codex/harness 配置。")
    elif selected_project and not checks["project_workspace_routing_exists"]:
        recommendations.append("运行 codex memory init 生成缺失的 .codex/harness/workspace-routing.json 路由配置。")
    if selected_project and not checks["project_shared_exists"]:
        recommendations.append("运行 codex memory init 生成缺失的 .codex/shared 项目共享记忆模板。")
    if official_memory.get("legacy_harness_markers_in_official_dir"):
        recommendations.append(
            "检测到旧版 harness 全局记忆文件位于官方 Codex Memories 目录；请手动迁移到 "
            f"{official_memory['harness_global_memory_dir']}，避免污染官方自动记忆。"
        )
    if not official_memory.get("config_parse_ok", True):
        recommendations.append("官方 Codex config.toml 解析失败；doctor 已跳过官方 Memories 开关判断。")
    if not codex_config.get("config_parse_ok", True):
        recommendations.append("官方 Codex config.toml 解析失败；doctor 已跳过 native hooks/MCP/sandbox 对齐检查。")
    native_alignment = codex_config.get("native_alignment") if isinstance(codex_config.get("native_alignment"), dict) else {}
    if native_alignment.get("needs_hooks_feature"):
        recommendations.append("建议在官方 Codex config.toml 中启用 [features] hooks = true，让插件 hooks 走官方生命周期。")
    plugin_hooks = codex_config.get("plugin_hooks") if isinstance(codex_config.get("plugin_hooks"), dict) else {}
    if plugin_hooks.get("missing_recommended_events"):
        recommendations.append(
            "插件 hooks.json 缺少官方生命周期事件："
            + ", ".join(plugin_hooks["missing_recommended_events"])
            + "；请更新插件或重新安装。"
        )
    if native_alignment.get("high_risk_unattended_permissions"):
        recommendations.append(
            "当前 Codex sandbox_mode=danger-full-access 且 approval_policy=never；日常交互建议改为带审批的工作区写入配置。"
        )
    agents_override = codex_config.get("agents_override") if isinstance(codex_config.get("agents_override"), dict) else {}
    if agents_override.get("may_override_global_agents"):
        recommendations.append("检测到官方 AGENTS.override.md；它可能覆盖全局 Codex Memory 规则，请确认其中保留必要入口。")

    return {
        "ok": ok,
        "mode": "init-project" if init else "doctor",
        "cwd": str(start),
        "plugin_root": str(plugin_root),
        "project": {
            "detected": project_root is not None,
            "root": str(selected_project) if selected_project else "",
            "markers": markers,
            "used_cwd_as_project": init and project_root is None,
        },
        "memory": {
            "recommended_scope": "project" if selected_project else "global",
            "storage": storage.as_dict(),
            "official_codex": official_memory,
        },
        "codex": {
            "native_integration": codex_config,
        },
        "checks": checks,
        "actions": actions,
        "recommended_env": {
            "CODEX_MEMORY_SCOPE": "project" if selected_project else "global",
            "CODEX_MEMORY_CWD": str(selected_project or start),
        },
        "recommendations": recommendations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and diagnose Codex Memory for a Codex window.")
    parser.add_argument("--cwd", help="Directory used to resolve the current project.")
    parser.add_argument("--doctor", action="store_true", help="Inspect current state without creating project files.")
    parser.add_argument("--init-project", action="store_true", help="Create missing project memory and harness config.")
    args = parser.parse_args()

    cwd = Path(args.cwd or os.environ.get("CODEX_MEMORY_CWD") or Path.cwd())
    result = inspect_state(cwd, init=args.init_project)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
