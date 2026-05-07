from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROFILE_START = "# >>> codex-memory codexm launcher >>>"
PROFILE_END = "# <<< codex-memory codexm launcher <<<"
POSIX_PROFILE_START = "# >>> codex-memory posix launcher >>>"
POSIX_PROFILE_END = "# <<< codex-memory posix launcher <<<"
AGENTS_START = "<!-- >>> codex-memory-harness global >>> -->"
AGENTS_END = "<!-- <<< codex-memory-harness global <<< -->"
MIN_PYTHON_VERSION = (3, 11)
DEFAULT_PY_LAUNCHER_PREFIX_ARGS = ["-3"]
PYTHON_LAUNCHER_CANDIDATES = (
    ("py", list(DEFAULT_PY_LAUNCHER_PREFIX_ARGS)),
    ("python", []),
    ("python3", []),
    ("python3.14", []),
    ("python3.13", []),
    ("python3.12", []),
    ("python3.11", []),
)


def home_root() -> Path:
    configured = os.environ.get("CODEX_MEMORY_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home()


def codex_home_root() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return home_root() / ".codex"


def home_agents_path() -> Path:
    return codex_home_root() / "AGENTS.md"


def profile_paths(shells: str) -> list[Path]:
    documents = home_root() / "Documents"
    candidates = {
        "pwsh": documents / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
        "windows": documents / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
    }
    if shells == "none":
        return []
    if shells == "auto":
        return [candidates["pwsh"]]
    if shells == "all":
        return [candidates["pwsh"], candidates["windows"]]
    if shells in candidates:
        return [candidates[shells]]
    return []


def posix_profile_paths(shells: str = "auto") -> list[Path]:
    candidates = {
        "profile": home_root() / ".profile",
        "bash": home_root() / ".bashrc",
        "zsh": home_root() / ".zshrc",
    }
    if shells == "none":
        return []
    if shells in ("auto", "all"):
        return [candidates["profile"], candidates["bash"], candidates["zsh"]]
    if shells in candidates:
        return [candidates[shells]]
    return []


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def dependency_status() -> dict[str, Any]:
    python_ok = sys.version_info[:2] >= MIN_PYTHON_VERSION
    py_launcher_path = shutil.which("py")
    launchers = []
    seen: set[str] = set()
    for command, _prefix_args in PYTHON_LAUNCHER_CANDIDATES:
        path = shutil.which(command)
        if not path:
            continue
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        launchers.append({"command": command, "path": path})

    codex_path = shutil.which("codex")
    powershell_commands = []
    for command in ("pwsh", "powershell"):
        path = shutil.which(command)
        if path:
            powershell_commands.append({"command": command, "path": path})

    missing = []
    recommendations = []
    def _recommend(value: str) -> None:
        if value not in recommendations:
            recommendations.append(value)

    python_hint = (
        "Install Python 3.11+ and enable 'Add python.exe to PATH'; "
        "on Windows you can run: winget install --id Python.Python.3.12 -e --source winget"
    )
    py_hint = (
        "Optional Windows Python launcher. Codex Memory hooks, wrappers, and MCP launcher also support "
        "python or python3 when either command is on PATH."
    )
    if not python_ok:
        missing.append("python>=3.11")
        _recommend(python_hint)
    if not launchers:
        missing.append("python_launcher")
        _recommend(python_hint)
    if not codex_path:
        missing.append("codex_cli")
        _recommend("Install Codex CLI and make sure the codex command is on PATH.")
    return {
        "python": {
            "ok": python_ok,
            "required": ">=3.11",
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "executable": sys.executable,
            "launchers": launchers,
            "install_hint": python_hint,
        },
        "py_launcher": {
            "ok": bool(py_launcher_path),
            "path": py_launcher_path or "",
            "install_hint": py_hint,
        },
        "codex_cli": {
            "ok": bool(codex_path),
            "path": codex_path or "",
            "install_hint": "Install Codex CLI and make sure the codex command is on PATH.",
        },
        "powershell": {
            "ok": bool(powershell_commands),
            "required": False,
            "commands": powershell_commands,
            "install_hint": (
                "Optional for PowerShell profile wrappers. POSIX hooks and MCP launchers "
                "do not require a powershell command."
            ),
        },
        "missing": missing,
        "recommendations": recommendations,
    }


def select_mcp_python_runtime(
    command: str | None = None,
    prefix_args: list[str] | None = None,
) -> dict[str, Any]:
    if command:
        return {"command": command, "prefix_args": list(prefix_args or [])}
    for candidate, candidate_prefix_args in PYTHON_LAUNCHER_CANDIDATES:
        if shutil.which(candidate) and _python_runtime_ok(candidate, candidate_prefix_args):
            return {"command": candidate, "prefix_args": candidate_prefix_args}
    return {"command": sys.executable, "prefix_args": []}


def _python_runtime_ok(command: str, prefix_args: list[str]) -> bool:
    probe = [command, *prefix_args, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"]
    try:
        completed = subprocess.run(probe, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    parts = completed.stdout.strip().split(".")
    if len(parts) < 2:
        return False
    try:
        version = (int(parts[0]), int(parts[1]))
    except ValueError:
        return False
    return version >= MIN_PYTHON_VERSION


def replace_marked_block(
    text: str,
    start_marker: str,
    end_marker: str,
    block: str,
) -> tuple[str, str]:
    start = text.find(start_marker)
    end = text.find(end_marker)
    normalized_block = block.strip() + "\n"
    if start != -1 and end != -1 and end > start:
        end += len(end_marker)
        prefix = text[:start].rstrip()
        suffix = text[end:].lstrip()
        parts = [part for part in [prefix, normalized_block.rstrip(), suffix] if part]
        return "\n\n".join(parts) + "\n", "updated"
    if text.strip():
        return text.rstrip() + "\n\n" + normalized_block, "appended"
    return normalized_block, "created"


def agents_block(home_plugin: Path) -> str:
    official_memory = codex_home_root() / "memories"
    global_memory = codex_home_root() / "codex-memory-harness" / "memories"
    return f"""
{AGENTS_START}
## Codex Memory 全局无感使用（MUST）
- 所有 Codex 窗口默认启用本地外部记忆插件，统一入口为 `{home_plugin}`。
- 默认写入项目记忆：`<项目根目录>\\.codex\\memories`。
- 只有跨项目偏好、长期通用规则、用户明确要求全局沉淀时，才写入全局记忆：`{global_memory}`。
- 官方 Codex Memories 使用 `{official_memory}`；该目录保留给 Codex 官方自动记忆，不写入本插件的 SQLite/JSONL 运行态。
- 推荐优先通过官方 Codex config/hooks/MCP 接入；PowerShell/POSIX wrapper 作为兼容入口、诊断入口和旧环境兜底。
- 本包默认随安装写入 bundled Codex skills：安全最佳实践、威胁模型、CLI 创建、迁移到 Codex、GitHub CI 修复、PR 评论处理和 Harness release gate；目标位置为 `~/.agents/skills`。
- 不要求用户手动调用记忆命令；官方 hooks 可用时自动桥接 `UserPromptSubmit`、`PostToolUse`、`Stop`，不可用时代理应在任务生命周期内自动调用 `before_task`、`after_tool`、`before_response`、`on_task_complete`。
- `codex memory doctor` 会检查 `features.codex_hooks`、sandbox/approval、AGENTS.override、官方 Memories 和插件 hook 覆盖情况。
- 插件不可用时必须降级为普通无记忆模式，并在最终答复的工具调用简报中说明局限。
- 不得把敏感信息、密钥、令牌或内部链接写入记忆；写入前应做最小化摘要。
- 用户明确选择 SubAgent、分角色或并行代理，任务属于复杂/应用级/多阶段实现，项目 `.codex/harness/project_profile.json` / `.codex/harness/workspace-routing.json` 的 `subagent_runtime_policy` 授权正式 implementation 任务，或通用 planner 基于 `task_intent/task_type/risk_level/complexity` 判定需要派发时，代理必须读取 `metadata.workspace_routing.subagent_runtime` 与 `subagent_dispatch_plan.host_spawn_requests`；当 `host_dispatch_allowed=true` 且宿主提供 SubAgent 工具时，按请求派发宿主 SubAgent，否则记录降级原因并由主 Agent 串行执行。
- 所有 SubAgent 都不得设置固定总时长；宿主 `wait_agent` 或类似 API 的 timeout 只能作为本次观察窗口，窗口到期后继续观察，不得仅因观察窗口到期而中断、关闭或判失败。只要 SubAgent 有输出、checkpoint、状态更新或可见进度，就视为仍在运行。
- 代码审核优先使用 `codex xhigh review --uncommitted` 作为最终 review gate；大 diff 或长耗时审查优先派发 XHigh Review Runner SubAgent 作为并行命令执行器运行该 gate，等待策略按 stdout/stderr 进度输出观察，不使用固定总时长超时，也不得再用 10 分钟外层总时长包住 runner。runner 遇到模型容量、429、5xx 或超时类基础设施错误时，如果宿主持有仍活跃的 runner session，必须先按类型退避并对同一 session 发送继续指令：容量/429 退避 20 秒且只要 session 活跃就可继续，5xx/超时退避 2 秒且最多续跑一次；只有 session 已关闭、无句柄、不可恢复或 diff 已变化时，才重新启动同一个 review gate。通用 SubAgent reviewer 只做限定 scope 的专题/旁路审查。
- 代码 review findings 全部修复、最终 review gate 无阻断问题且验证通过后，必须在本地创建一个 git commit 记录当前版本；若工作树包含用户无关改动，必须只提交本轮相关文件或先说明无法安全提交。

### 常用入口
```powershell
codex
codexm
codex memory doctor
codex memory init
codex memory install
codex memory update
codex memory check-install
codex harness verify list
codex harness verify run --profile primary
codex package verify
codex-memory-doctor
codex-raw
```

### 常用验证
```powershell
python -X utf8 -m unittest discover -s tests
python -X utf8 scripts/verify_project.py
python -X utf8 plugins/codex-memory/scripts/install_codex_memory.py --check
codex xhigh review --uncommitted
```

### 启动自检
```powershell
codex memory doctor
codex memory init
codex memory check-install
```

### 任务生命周期
```powershell
codex memory hook before_task --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
codex memory hook after_tool --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
codex memory hook before_response --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
codex memory hook on_task_complete --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
```

### Harness 与打包
```powershell
codex harness start --task-file task.json
codex harness checkpoint --task-id <task-id> --result-file result.json
codex harness complete --task-id <task-id> --summary-file summary.md
codex harness verify run --profile primary
codex package build
codex package verify
codex xhigh review --uncommitted
```

PowerShell 中优先使用 `--payload-file`，避免内联 JSON 转义问题。
{AGENTS_END}
"""


def ensure_profile(home_plugin: Path, shells: str) -> list[dict[str, Any]]:
    from profile_blocks import profile_block

    results: list[dict[str, Any]] = []
    block = profile_block(home_plugin)
    for path in profile_paths(shells):
        current = read_text(path)
        updated, status = replace_marked_block(current, PROFILE_START, PROFILE_END, block)
        if updated != current:
            write_text(path, updated)
        results.append({"path": str(path), "status": status})
    return results


def ensure_posix_profile(home_plugin: Path, shells: str = "auto") -> list[dict[str, Any]]:
    from profile_blocks import posix_profile_block

    results: list[dict[str, Any]] = []
    block = posix_profile_block(home_plugin)
    for path in posix_profile_paths(shells):
        current = read_text(path)
        updated, status = replace_marked_block(
            current,
            POSIX_PROFILE_START,
            POSIX_PROFILE_END,
            block,
        )
        if updated != current:
            write_text(path, updated)
        results.append({"path": str(path), "status": status})
    return results


def ensure_agents(home_plugin: Path) -> dict[str, Any]:
    path = home_agents_path()
    current = read_text(path)
    if AGENTS_START not in current and "## Codex Memory 全局无感使用" in current:
        return {"path": str(path), "status": "existing_unmarked_kept"}
    updated, status = replace_marked_block(current, AGENTS_START, AGENTS_END, agents_block(home_plugin))
    if updated != current:
        write_text(path, updated)
    return {"path": str(path), "status": status}


def remove_marked_block(path: Path, start_marker: str, end_marker: str) -> dict[str, Any]:
    current = read_text(path)
    start = current.find(start_marker)
    end = current.find(end_marker)
    if start == -1 or end == -1 or end <= start:
        return {"path": str(path), "removed": False}
    end += len(end_marker)
    updated = (current[:start].rstrip() + "\n\n" + current[end:].lstrip()).strip()
    write_text(path, updated + ("\n" if updated else ""))
    return {"path": str(path), "removed": True}


def profile_statuses(shells: str) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path),
            "exists": path.exists(),
            "has_launcher": PROFILE_START in read_text(path),
        }
        for path in profile_paths(shells)
    ]


def posix_profile_statuses(shells: str = "auto") -> list[dict[str, Any]]:
    return [
        {
            "path": str(path),
            "exists": path.exists(),
            "has_launcher": POSIX_PROFILE_START in read_text(path),
        }
        for path in posix_profile_paths(shells)
    ]
