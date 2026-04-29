from __future__ import annotations

from pathlib import Path
from typing import Any


PROFILE_START = "# >>> codex-memory codexm launcher >>>"
PROFILE_END = "# <<< codex-memory codexm launcher <<<"
AGENTS_START = "<!-- >>> codex-memory-harness global >>> -->"
AGENTS_END = "<!-- <<< codex-memory-harness global <<< -->"


def home_root() -> Path:
    return Path.home()


def home_agents_path() -> Path:
    return home_root() / ".codex" / "AGENTS.md"


def profile_paths(shells: str) -> list[Path]:
    documents = home_root() / "Documents"
    candidates = {
        "pwsh": documents / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
        "windows": documents / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
    }
    if shells == "none":
        return []
    if shells == "all":
        return [candidates["pwsh"], candidates["windows"]]
    return [candidates[shells]]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


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


def profile_block(home_plugin: Path) -> str:
    launcher = home_plugin / "scripts" / "codexm.ps1"
    return f"""
{PROFILE_START}
function codexm {{
    & "{launcher}" @args
}}

function codex {{
    & "{launcher}" @args
}}

function codex-raw {{
    $env:CODEX_MEMORY_DISABLE_WRAPPER = "1"
    try {{
        & "{launcher}" -SkipBootstrap @args
    }} finally {{
        Remove-Item Env:\\CODEX_MEMORY_DISABLE_WRAPPER -ErrorAction SilentlyContinue
    }}
}}

function codex-memory-doctor {{
    & "{launcher}" memory doctor
}}
{PROFILE_END}
"""


def agents_block(home_plugin: Path) -> str:
    global_memory = home_root() / ".codex" / "memories"
    return f"""
{AGENTS_START}
## Codex Memory 全局无感使用（MUST）
- 所有 Codex 窗口默认启用本地外部记忆插件，统一入口为 `{home_plugin}`。
- 默认写入项目记忆：`<项目根目录>\\.codex\\memories`。
- 只有跨项目偏好、长期通用规则、用户明确要求全局沉淀时，才写入全局记忆：`{global_memory}`。
- 不要求用户手动调用记忆命令；代理应在任务生命周期内自动调用 `before_task`、`after_tool`、`before_response`、`on_task_complete`。
- 插件不可用时必须降级为普通无记忆模式，并在最终答复的工具调用简报中说明局限。
- 不得把敏感信息、密钥、令牌或内部链接写入记忆；写入前应做最小化摘要。
- 代码审核优先使用 `codex xhigh review --uncommitted` 作为最终 review gate；大 diff 可让 SubAgent 作为并行命令执行器运行该 gate。通用 SubAgent reviewer 只做限定 scope 的专题/旁路审查。

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
    results: list[dict[str, Any]] = []
    block = profile_block(home_plugin)
    for path in profile_paths(shells):
        current = read_text(path)
        updated, status = replace_marked_block(current, PROFILE_START, PROFILE_END, block)
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
