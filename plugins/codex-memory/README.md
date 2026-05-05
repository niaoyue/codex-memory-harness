# Codex Memory Plugin

这是 Codex Memory Harness 的核心插件目录，面向本地外部记忆、检索、上下文编排、Harness 任务生命周期、验证回写和蒸馏沉淀。

## 核心入口

- `scripts/install_codex_memory.py`：用户级安装、检查、卸载和旧安装迁移。
- `scripts/skill_bundle.py`：随包 bundled skills 的状态检查和离线复制安装。
- `scripts/codexm.ps1`：PowerShell 启动 wrapper。
- `scripts/codex_bootstrap.py`：项目识别、doctor、自初始化。
- `scripts/hook_runner.py`：任务生命周期 hook。
- `scripts/harness_controller.py`：`start` / `checkpoint` / `complete` 任务运行时。
- `scripts/verification_runner.py`：配置化验证 runner。
- `scripts/shared_memory.py`：项目共享 memory promote、validate 和 index rebuild。
- `scripts/workspace_scanner.py`：只读 workspace scanner，输出 project inventory。
- `scripts/workspace_router.py`：只读 workspace route planner，输出 route plan。
- `scripts/workspace_verifier.py`：按 route plan 聚合多项目 verification profile。
- `scripts/workspace_subagents.py`：生成 SubAgent bindings、执行 scope-check 和 coordinator summary。
- `scripts/workspace_lifecycle.py`：把 workspace routing 接入 memory hook 生命周期。
- `mcp/memory_server.py`：最小 MCP stdio 服务入口。

## 安装

推荐从项目根目录安装：

```bat
install.bat
```

POSIX shell：

```sh
sh ./install.sh
```

`install.sh` 是 shell 入口包装；当前 hook/MCP 运行时仍依赖名为 `powershell` 的 PowerShell launcher，目标环境需要能调用 `powershell` 命令。

如果当前版本已经安装，安装器会提示 `already_installed`，不会重复安装。

如果已有旧安装指向其他项目，默认不会覆盖；显式更新到当前版本：

```bat
install.bat --update-existing
```

POSIX shell：

```sh
sh ./install.sh --update-existing
```

安装完成后，也可以通过 Codex 入口检查或修复当前安装：

```powershell
codex memory install
codex memory update
codex memory check-install
```

安装器默认会把随包附带的 openai/skills curated 技能和本项目 release gate 技能复制到 `~/.agents/skills`：

- `security-best-practices`
- `security-threat-model`
- `cli-creator`
- `migrate-to-codex`
- `gh-fix-ci`
- `gh-address-comments`
- `harness-release-gate`

这些技能位于 `skills/openai-curated/` 和 `skills/local/`，来源记录在 `skills/bundled-skills.json`。安装时不联网下载；如果 `~/.agents/skills/<skill-name>` 已存在，会跳过并保留用户已有版本。需要跳过技能安装时使用：

```bat
install.bat --skip-skills
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
codex harness start --task-file task.json
codex harness checkpoint --task-id <task-id> --result-file result.json
codex harness complete --task-id <task-id> --summary-file summary.md
codex harness verify run --profile primary
```

Harness Engineering 对标、向量检索策略和 SubAgent 角色协议在仓库根目录文档中维护：

```text
docs/EXTERNAL_BENCHMARK.md
docs/MEMORY_RETRIEVAL_STRATEGY.md
docs/SUBAGENT_WORKFLOW.md
```

当前插件不内建 SubAgent 调度器，也不默认依赖向量数据库。Workspace routing 已接入 hook 生命周期软集成：`before_task` 写 route plan/bindings，`after_tool` 执行 scope guard，`before_response` 输出 routing review。

## Bootstrap / Doctor

```powershell
codex memory doctor
codex memory init
```

`doctor` 只检查状态，`init` 只创建缺失的 `.codex/memories`、`.codex/harness` 和 `.codex/shared` 配置，不覆盖已有配置。

项目共享 memory：

```powershell
codex memory promote --task-id <task-id> --kind fact
codex memory shared validate
codex memory shared index rebuild
```

## PowerShell Launcher

安装后可用：

```powershell
codex
codexm
codex memory doctor
codex memory init
codex harness verify run --profile primary
codex workspace doctor
codex workspace scan
codex workspace route --task-file task.json
codex workspace verify --route-file route.json
codex workspace bind --route-file route.json
codex workspace scope-check --binding-file binding.json --touched-path client/Assets/App.cs
codex workspace summarize --bindings-file bindings.json --artifact-file agent-result.json
codex package verify
codex-memory-doctor
codex-raw
```

`codex-raw` 和 `CODEX_MEMORY_DISABLE_WRAPPER=1` 是回退入口。插件不改写真正的 Codex CLI 文件。
