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
LEGACY_AGENTS_HEADING = "## Codex Memory 全局无感使用"
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
STALE_REVIEW_GATE_REPLACEMENT = (
    "- 代码审核采用候选提交后 Review a commit：验证通过并确认提交边界后，"
    "先创建只包含本轮相关文件的 candidate commit，再运行 "
    "`codex xhigh review --commit <commit-sha>` 审核该提交；SubAgent reviewer "
    "只做窄范围专题/旁路审查，不替代最终代码审核。"
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


def replace_legacy_agents_block(text: str, block: str) -> tuple[str, str]:
    if AGENTS_START in text or LEGACY_AGENTS_HEADING not in text:
        return text, "missing"

    lines = text.splitlines(keepends=True)
    start_index = -1
    for index, line in enumerate(lines):
        if line.startswith(LEGACY_AGENTS_HEADING):
            start_index = index
            break
    if start_index == -1:
        return text, "missing"

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        line = lines[index]
        if line.startswith("## ") or line.startswith("--- project-doc"):
            end_index = index
            break

    prefix = "".join(lines[:start_index]).rstrip()
    suffix = "".join(lines[end_index:]).lstrip()
    normalized_block = block.strip()
    parts = [part for part in [prefix, normalized_block, suffix] if part]
    return "\n\n".join(parts) + "\n", "legacy_unmarked_updated"


def stale_uncommitted_review_gate_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if _is_stale_uncommitted_review_gate_line(line)
    ]


def repair_stale_review_gate_guidance(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return text, False
    changed = False
    repaired: list[str] = []
    for line in lines:
        if _is_stale_uncommitted_review_gate_line(line):
            newline = "\n" if line.endswith("\n") else ""
            repaired.append(STALE_REVIEW_GATE_REPLACEMENT + newline)
            changed = True
        else:
            repaired.append(line)
    return "".join(repaired), changed


def _is_stale_uncommitted_review_gate_line(line: str) -> bool:
    normalized = line.lower()
    if "--uncommitted" not in normalized:
        return False
    return (
        "最终 review gate" in normalized
        or "final review gate" in normalized
        or "代码审核优先使用" in line
    )


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
- 本包默认随安装写入 `bundled-skills.json` 登记的所有可用治理技能，覆盖安全、GitHub、CLI、迁移、release gate、需求澄清、接口设计、TDD、提交、review、PRD、重构、文档、图像、OpenAI docs、plugin/skill 创建等场景；目标位置为 `~/.agents/skills`。
- 默认采用 skill-first 工作流：任务开始先匹配可用技能；需求/策划文档用 `grill-me` 风格提出不确定、逻辑混乱和逻辑错误清单，能通过本地代码和文档自答的先补齐，不能自答的反馈用户；创建接口、协议、schema、CLI 或跨模块契约前优先用 `design-an-interface` 形成多个接口方向。
- 持久规格与 change contract 默认遵循 OpenSpec 最新 `spec-driven` 结构：新变更写入 `openspec/changes/<change-id>/proposal.md`、`specs/<capability>/spec.md`、`design.md`、`tasks.md`；稳定行为规格写入 `openspec/specs/<capability>/spec.md`。Harness 执行衔接写入同一 change 下的 `harness.json` / `harness.md`；官方 OpenSpec schema/templates/license/package metadata 由 Codex Memory Harness 通过 `codex openspec upstream sync` 从 `@fission-ai/openspec` 同步到目标项目的 `openspec/upstream/openspec/` 并用 manifest 哈希校验；`.codex/specs` 已退役，不再作为正式 spec 层。`docs/` 只放用户可读或长期公开项目文档，`.codex/memories`、`.codex/harness/tasks` 和事件/数据库/缓存仍为运行态，不提交。
- 每个 Codex 窗口启动或进入项目后，默认先执行由 Codex Memory Harness 提供的启动自检；自检会检测或补齐目标项目的 memory/init、OpenSpec upstream snapshot 同步与校验、安装状态检查。这些是 Harness 对目标项目的接入能力与运行前检查，不代表目标项目自身已经实现 memory、harness 或 OpenSpec 业务能力。
- OpenSpec upstream snapshot 是 Codex Memory Harness 提供的项目初始化/自检步骤；默认流程必须先运行 `codex openspec upstream sync --version 1.3.1`，随后运行 `codex openspec upstream verify`。该 snapshot 仅固定官方 schema/templates/license/package metadata，不等同于目标项目已经完成 OpenSpec 规格层或相关功能实现。只有当用户显式禁用 OpenSpec、当前任务为只读/不写文件、网络或 upstream 不可用，或类似无法安全同步的情况，才允许降级；降级必须在 checkpoint、最终答复或工具调用简报中报告原因、影响和下一步。
- 输出未完成 Task 汇总时，必须为每个未完成 Task 附带进度：状态、最近 checkpoint 或更新时间、已完成/剩余验收、阻塞点、下一步和证据来源；缺证据时标记 `unknown`，不得猜测百分比。
- 需求被拆成多任务时，先分析依赖、决策、环境、接口和验证卡点；除非所有任务都被同一类阻塞卡住，否则按依赖关系使用多 SubAgent 并行推进。每个 SubAgent 必须有明确 scope、cwd、规则、验收和 forbidden paths，并按 harness checkpoint 回写结果。
- 策划需求默认进入完整性审查：目标、状态、边界、异常、验收、多语言、多平台、WebGL/小游戏、性能、包体、安全、迁移和回滚缺口都要列出。技术选择默认支持多语言和全平台，重点考虑 WebGL/小游戏兼容、性能和包体；优先现有约定和官方库，但如果官方方案在关键指标上比第三方稳定方案差约 20% 以上且第三方 license/安全/维护可接受，应优先第三方。避免为抽象而过度封装，模块要可拆卸、可选择性编译和容易裁剪。
- 游戏/客户端资源管理默认限制依赖扩散：一个业务预制体优先只依赖本模块 AB 包，最多再依赖一个公共 AB 包；跨模块公共资源必须有 owner、版本、影响范围和回滚策略。
- 不要求用户手动调用记忆命令；官方 hooks 可用时自动桥接 `UserPromptSubmit`、`PostToolUse`、`Stop`，不可用时代理应在任务生命周期内自动调用 `before_task`、`after_tool`、`before_response`、`on_task_complete`。
- `codex memory doctor` 会检查 `features.hooks`、sandbox/approval、AGENTS.override、官方 Memories 和插件 hook 覆盖情况。
- 插件不可用时必须降级为普通无记忆模式，并在最终答复的工具调用简报中说明局限。
- 不得把敏感信息、密钥、令牌或内部链接写入记忆；写入前应做最小化摘要。
- 涉及 OpenSpec change/spec 执行的写入、实现、对齐、归档或 apply 类任务必须强制走 SubAgent：当 working set、touched paths、route scope 或任务文本命中 `openspec/changes/`、`openspec/specs/`、OpenSpec `harness.json` / `harness.md` 或 OpenSpec change contract 时，运行时必须输出 `execution_model=host_subagent_required`、`dispatch_required=true`、`autostart=true`，MainAgent 必须先按 `subagent_dispatch_plan.host_spawn_requests` 真实派发 SubAgent，再做协调、集成、验证和 review gate。
- 用户明确选择 SubAgent、分角色或并行代理，任务属于复杂/应用级/多阶段实现，项目 `.codex/harness/project_profile.json` / `.codex/harness/workspace-routing.json` 的 `subagent_runtime_policy` 授权正式 implementation 任务，或通用 planner 基于 `task_intent/task_type/risk_level/complexity` 判定需要派发时，代理必须读取 `metadata.workspace_routing.subagent_runtime` 与 `subagent_dispatch_plan.host_spawn_requests`。当 `subagent_runtime.recommended=true`、`host_dispatch_allowed=true`、`host_spawn_requests` 非空，且当前宿主提供并允许 `spawn_agent` 或等价 SubAgent 工具时，MainAgent 必须在继续实现前按每个 request 的 `agent_type`、`fork_context`、`message`、`assigned_scope`、`forbidden_paths` 真实派发 SubAgent；不得只生成 dispatch plan 后继续由 MainAgent 串行吞掉所有实现。
- 本条是用户对本安装环境的长期明确授权：凡 `subagent_runtime_policy`、OpenSpec 强制规则、通用 planner 或 review gate 产出 `host_dispatch_allowed=true` / `dispatch_required=true` 且 `subagent_dispatch_plan.host_spawn_requests` 非空，即视为用户已经明确要求使用指定 role 的 SubAgent。MainAgent 不得以“当前 prompt 未再次写 SubAgent”为由跳过派发、要求用户重复确认或串行吞掉实现。
- `host_spawn_requests` 必须使用指定角色 SubAgent：`agent_type` 应映射到 `Implementation Specialist`、`Workspace Coordinator`、`Route Review Specialist` 或 `XHigh Review Runner`；`worker` / `default` 只能在宿主没有对应 custom agent 时作为显式降级，并记录 `dispatch_required`、`host_spawn_request_count`、`actual_subagents=0`、`downgrade_reason` 和未执行的 `dispatch_id`。
- 只有在宿主缺少 SubAgent 工具、上层系统策略禁止调用、requirements gate 阻塞、所有任务被同一类外部阻塞卡住，或 scope 无法安全拆分时，才允许 MainAgent 串行降级；降级必须写入 checkpoint/最终答复，至少包含 `dispatch_required`、`host_spawn_request_count`、`actual_subagents=0`、`downgrade_reason`、未执行的 `dispatch_id`，并说明是否构成 blocking gap。复杂/多 scope implementation 中出现 `recommended_not_started` 且 `actual_subagents=0` 时，默认按流程缺口处理，不能静默视为正常完成。
- 所有 SubAgent 都不得设置固定总时长；宿主 `wait_agent` 或类似 API 的 timeout 只能作为本次观察窗口，窗口到期后继续观察，不得仅因观察窗口到期而中断、关闭或判失败。只要 SubAgent 有输出、checkpoint、状态更新或可见进度，就视为仍在运行。
- 验证、提交边界确认、candidate commit 和最终 review gate 是代码/规格变更的默认收尾流程；进入收尾阶段后不需要用户额外明确要求，除非用户明确要求暂停、只分析或不提交。
- 代码审核采用候选提交后 review：验证通过并确认提交边界后，先在本地创建一个只包含本轮相关文件的 candidate commit，并立即记录被审提交 SHA（通常是 `git rev-parse HEAD`）。最终 gate 使用 Review a commit：`codex xhigh review --commit <commit-sha>`，只审核该提交引入的变更，不能用 `--base` 把整个候选范围反复送审；大 diff 或长耗时审查优先派发 XHigh Review Runner SubAgent 作为并行命令执行器运行该 gate，等待策略按 stdout/stderr 进度输出观察，不使用固定总时长超时，也不得再用 10 分钟外层总时长包住 runner。runner 遇到模型容量、429、5xx 或超时类基础设施错误时，如果宿主持有仍活跃的 runner session，必须先按类型退避并对同一 session 发送继续指令：容量/429 退避 20 秒且只要 session 活跃就可继续，5xx/超时退避 2 秒且最多续跑一次；只有 session 已关闭、无句柄、不可恢复或被审提交 ref 变化时，才重新启动同一个 review gate。通用 SubAgent reviewer 只做限定 scope 的专题/旁路审查。
- 如果 review 本次提交发现阻断问题，必须修复后创建新的本地提交（或在尚未 push 前重做候选提交），再 review 新提交本身；重复“提交 -> review 该提交 -> 修复 -> 再提交 -> review 新提交”，直到 review 没有新的阻断问题后才允许 push。若工作树包含用户无关改动，必须只提交本轮相关文件或先说明无法安全提交。

### 常用入口
```powershell
codex
codexm
codex memory doctor
codex memory init
codex memory install
codex memory update
codex memory check-install
codex memory migrate-legacy-global --dry-run
codex harness verify list
codex harness verify run --profile primary
codex openspec upstream sync --version 1.3.1
codex openspec upstream verify
codex package verify
codex-memory-doctor
codex-raw
```

### 常用验证
```powershell
python -X utf8 -m unittest discover -s tests
python -X utf8 scripts/verify_project.py
python -X utf8 plugins/codex-memory/scripts/install_codex_memory.py --check
$commitSha = git rev-parse HEAD
codex xhigh review --commit $commitSha
```

### 启动自检
```powershell
codex memory doctor
codex memory init
codex openspec upstream sync --version 1.3.1
codex openspec upstream verify
codex memory check-install
```

### 任务生命周期
稳定入口直接调用 hook launcher 的 `--event` 模式，不依赖 shell profile wrapper；launcher 会自行解析 `py` / `python` / `python3`，并把 `--payload-file` 原样交给 `hook_runner.py`。`codex memory hook ...` 只是已加载 wrapper 时的便利别名，`codex-raw` 和真实 Codex CLI 不支持该子命令。

```powershell
$HOOK_LAUNCHER = "{home_plugin / "scripts" / "hook_launcher.ps1"}"
$POWERSHELL = Get-Command pwsh -ErrorAction SilentlyContinue
if (-not $POWERSHELL) {{ $POWERSHELL = Get-Command powershell -ErrorAction Stop }}
$POWERSHELL = $POWERSHELL.Source
& $POWERSHELL -NoProfile -ExecutionPolicy Bypass -File $HOOK_LAUNCHER --event before_task --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
& $POWERSHELL -NoProfile -ExecutionPolicy Bypass -File $HOOK_LAUNCHER --event after_tool --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
& $POWERSHELL -NoProfile -ExecutionPolicy Bypass -File $HOOK_LAUNCHER --event before_response --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
& $POWERSHELL -NoProfile -ExecutionPolicy Bypass -File $HOOK_LAUNCHER --event on_task_complete --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
```

```sh
HOOK_LAUNCHER="$HOME/plugins/codex-memory/scripts/hook_launcher.sh"
sh "$HOOK_LAUNCHER" --event before_task --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
sh "$HOOK_LAUNCHER" --event after_tool --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
sh "$HOOK_LAUNCHER" --event before_response --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
sh "$HOOK_LAUNCHER" --event on_task_complete --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
```

### Harness 与打包
```powershell
codex harness start --task-file task.json
codex harness checkpoint --task-id <task-id> --result-file result.json
codex harness complete --task-id <task-id> --summary-file summary.md
codex harness verify run --profile primary
codex package build
codex package verify
$commitSha = git rev-parse HEAD
codex xhigh review --commit $commitSha
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
    block = agents_block(home_plugin)
    updated, status = replace_legacy_agents_block(current, block)
    if status == "missing":
        updated, status = replace_marked_block(current, AGENTS_START, AGENTS_END, block)
    updated, stale_repaired = repair_stale_review_gate_guidance(updated)
    if updated != current:
        write_text(path, updated)
    if stale_repaired:
        status = f"{status}+stale_review_gate_repaired"
    return {"path": str(path), "status": status, "stale_review_gate_repaired": stale_repaired}


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
