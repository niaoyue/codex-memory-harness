# Codex Memory Plugin

这是 Codex Memory Harness 的核心插件目录，面向本地外部记忆、检索、上下文编排、Harness 任务生命周期、验证回写和蒸馏沉淀。

## 核心入口

- `scripts/install_codex_memory.py`：用户级安装、检查、卸载和旧安装迁移。
- `scripts/codexm.ps1`：PowerShell 启动 wrapper。
- `scripts/codex_bootstrap.py`：项目识别、doctor、自初始化。
- `scripts/hook_runner.py`：任务生命周期 hook。
- `scripts/harness_controller.py`：`start` / `checkpoint` / `complete` 任务运行时。
- `scripts/verification_runner.py`：配置化验证 runner。
- `mcp/memory_server.py`：最小 MCP stdio 服务入口。

## 安装

推荐从项目根目录安装：

```powershell
.\install.ps1
```

也可以直接调用插件安装器：

```powershell
py -X utf8 plugins\codex-memory\scripts\install_codex_memory.py
```

如果已有旧安装指向其他项目：

```powershell
py -X utf8 plugins\codex-memory\scripts\install_codex_memory.py --replace-existing
```

只读检查：

```powershell
py -X utf8 plugins\codex-memory\scripts\install_codex_memory.py --check
```

## 记忆存储分层

默认项目级 memory：

```text
<项目根目录>/.codex/memories
```

全局 memory：

```text
C:\Users\<你>\.codex\memories
```

使用原则：

- 普通任务、项目决策、项目上下文默认写项目 memory。
- 跨项目偏好、长期通用规则、用户明确要求全局沉淀时写全局 memory。
- PowerShell 中优先使用 `--payload-file`，避免内联 JSON 转义问题。

## Harness

```powershell
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\harness_controller.py --project-root <项目目录> start --task-file task.json
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\harness_controller.py --project-root <项目目录> checkpoint --task-id <task-id> --result-file result.json
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\harness_controller.py --project-root <项目目录> complete --task-id <task-id> --summary-file summary.md
```

## Bootstrap / Doctor

```powershell
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\codex_bootstrap.py --cwd <项目目录> --doctor
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\codex_bootstrap.py --cwd <项目目录> --init-project
```

`--doctor` 只检查状态，`--init-project` 只创建缺失的 `.codex/memories` 和 `.codex/harness` 配置，不覆盖已有配置。

## PowerShell Launcher

安装后可用：

```powershell
codex
codexm
codex-memory-doctor
codex-raw
```

`codex-raw` 和 `CODEX_MEMORY_DISABLE_WRAPPER=1` 是回退入口。插件不改写真正的 Codex CLI 文件。
