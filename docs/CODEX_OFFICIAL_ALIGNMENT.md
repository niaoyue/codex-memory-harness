# 官方 Codex 使用建议对齐与安装传播路线

## 1. 文档目的

本文评估 OpenAI 官方 Codex 文档中的建议是否适合本项目，并把合理项拆成可落地、可验证、可随安装传播的改造路线。

用户安装本项目后应该自动获得的优化，不能只写到维护者本机的 `~/.codex` 或根目录 `.codex` 里。凡是需要新环境同步的优化，必须落到以下可分发位置之一：

- 安装器写入的用户级位置：`~/.codex/AGENTS.md`、`~/.agents/skills`、`~/.agents/plugins/marketplace.json`、`$CODEX_HOME/config.toml`、PowerShell profile。
- 插件随包位置：`plugins/codex-memory/hooks.json`、`.mcp.json`、`scripts/`、`skills/`。
- 项目模板或 bootstrap 生成逻辑：`templates/project/.codex/...`、`codex_bootstrap.py`。
- 发布包内文档和 schema：`docs/`、`schemas/`、`templates/`。

只写入本仓库根目录 `.codex/harness` 的 dogfood 配置，最多改善维护者本仓库体验；由于发布包排除根 `.codex`，它不算“新环境安装后同步”的优化。

## 2. 官方参考

当前对齐的官方入口：

- `https://developers.openai.com/codex/learn/best-practices`
- `https://developers.openai.com/codex/guides/agents-md`
- `https://developers.openai.com/codex/hooks`
- `https://developers.openai.com/codex/agent-approvals-security`
- `https://developers.openai.com/codex/skills`
- `https://developers.openai.com/codex/subagents`
- `https://developers.openai.com/codex/mcp`

关键对齐点：

- 官方建议把项目约定写入 `AGENTS.md`，并支持全局、仓库根目录和子目录分层。
- 官方 skills 当前可发现位置包括仓库 `.agents/skills`、用户 `~/.agents/skills`、管理员目录和系统目录；本项目安装后的用户级 bundled skills 应写入 `~/.agents/skills`。
- 官方 hooks 是生命周期扩展点，但安全 guard 不能替代 sandbox、审批和最终 review。
- 官方 subagents/custom agents 适合复杂任务，但角色配置应保持窄职责和可验证输出。
- 官方安全建议的方向是最小权限；安装器可以检查和提示高风险配置，但不应未经用户确认强制改写用户已有 sandbox/approval 策略。

## 3. 当前对齐结论

本项目方向整体合理：已经把官方 config/hooks/MCP 作为主路径，PowerShell wrapper 作为兼容兜底；已经有全局 AGENTS 标记块、hook 桥接、MCP 配置、verification runner、workspace routing、SubAgent dispatch plan、xhigh review gate 和发布包排除边界。

需要修正的重点是“传播路径”：

- 合理但只改本机的优化，必须迁移到安装器、随包 skill、模板或 bootstrap。
- 不适合默认安装的高风险优化，例如改用户 sandbox 为 full access 或自动迁移旧 memory 文件，必须保持显式命令、dry-run 或提示。
- 官方路径和项目历史路径冲突时，以官方路径作为新安装主路径，旧路径只做兼容检查或迁移说明。

## 4. 优化项合理性矩阵

| 编号 | 原建议 | 合理性 | 安装后同步落点 | 结论 |
|---|---|---|---|---|
| A1 | 本仓库 dogfood `.codex/harness` | 部分合理 | `templates/project/.codex`、`codex_bootstrap.py`；根 `.codex` 只供维护者本地 | 不应作为 P0 安装同步项 |
| A2 | 根 `AGENTS.md` 加短命令入口 | 合理 | `install_support.agents_block()` 写入 `~/.codex/AGENTS.md` | 应执行 |
| A3 | 子目录级 `AGENTS.md` | 合理但只影响本仓库/发布包源码 | 当前仓库只有根 `AGENTS.md`；如后续确需分层，可新增 `docs/AGENTS.md`、`tests/AGENTS.md` 或具体插件子树 `AGENTS.md` | 计划项，不等价于用户全局同步 |
| A4 | 日常权限回到 workspace-write/on-request | 合理 | `codex memory doctor` 提示；文档说明 | 不应静默改用户配置 |
| A5 | 增加 PreToolUse/PermissionRequest guard | 合理但需先确认 hook event 与测试 | `plugins/codex-memory/hooks.json`、`hook_bridge.py`、测试 | 暂缓为单独任务 |
| A6 | xhigh review gate 沉淀为 skill | 合理 | bundled skill 安装到 `~/.agents/skills/harness-release-gate` | 应执行 |
| A7 | dispatch plan 对齐 custom agents | 合理 | 尚未存在 `.codex/agents` 模板；后续可由模板或显式 install 选项写入 `.codex/agents` / `~/.codex/agents` | 暂缓，避免默认侵入 |
| A8 | `.codex` 开发配置与发布边界分层 | 合理 | 文档、`build_release.py`、`verify_project.py` | 已基本具备，继续约束 |
| A9 | 官方 Memories 旧 runtime marker 迁移 | 合理但高风险 | 新增 dry-run/confirm 命令 | 暂缓为独立迁移功能 |
| A10 | 减少对 `powershell` 命令名依赖 | 合理但改动较大 | shell launcher 或 Python-first launcher | 暂缓为跨平台专项 |

## 5. 本轮执行范围

本轮只执行低风险、可安装传播的改动：

1. 将 bundled skills 的新安装目标对齐到官方用户技能目录 `~/.agents/skills`。
2. 保留 `$CODEX_HOME/skills` 作为 legacy 状态检查路径，不再作为新安装主目标。
3. 新增随包 local skill：`harness-release-gate`。
4. 在安装器写入的全局 AGENTS 标记块里补短验证入口，确保新环境安装后能同步。
5. 修正文档，把“本机 dogfood”与“安装后同步”拆开。

不在本轮执行：

- 自动新增根 `.codex/harness` 并提交；它不会进入 release zip，不能解决新环境同步。
- 自动改用户 sandbox/approval；这属于用户安全策略，只提示不强改。
- 新增危险命令 guard；需要单独设计 hook payload、事件兼容和测试。
- 旧 memory 迁移命令；需要 dry-run、manifest、checksum 和回滚设计。
- 跨平台 launcher；涉及 hook/MCP 命令结构调整，应单独验证。

## 6. 推荐后续落地顺序

### P0：安装传播闭环

目标：新机器运行 `install.bat` / `install.sh` 后，获得全局规则、bundled skills、hook/MCP 接入和可观测状态。

验收：

```powershell
python -X utf8 plugins\codex-memory\scripts\install_codex_memory.py --check
python -X utf8 scripts\verify_project.py
```

期望：

- `bundled_skills.target_root` 指向 `~/.agents/skills`。
- `harness-release-gate`、安全、迁移、GitHub CI/PR 等技能在状态中可见。
- 目标已存在时跳过，不覆盖用户版本。
- `verify_project.py` 会从 release package 解压后的目录运行隔离 `install.bat --mode copy`，校验普通首次安装的写入路径。

### P1：项目模板传播

目标：用户项目运行 `codex memory init` 后，获得可验证的 `.codex/harness` 和 `.codex/shared` 基础配置。

当前模板已经存在：

```text
templates/project/.codex/harness/commands.json
templates/project/.codex/harness/project_profile.json
templates/project/.codex/harness/workspace-routing.json
templates/project/.codex/shared/
```

后续要避免把维护者本仓库的根 `.codex/harness` 当作用户模板；真正的用户传播点是 `templates/project` 和 `codex_bootstrap.py`。

### P2：官方 hooks/config 安全增强

目标：wrapper 退回兼容兜底，官方 hooks/MCP 成为主路径。

可做项：

- doctor 对 `features.codex_hooks`、MCP server、hook coverage、sandbox/approval 输出更明确分级。
- hooks 增加 timeout/degraded 输出。
- 单独实现最小危险命令 guard，并明确它不替代 sandbox/approval。

### P3：官方 custom agents

目标：让 `subagent_dispatch_plan.host_spawn_requests` 能映射到官方 custom agents。

当前尚未提供这些模板。建议后续先以模板形式提供，不默认写入用户全局：

```text
templates/project/.codex/agents/harness-explorer.toml
templates/project/.codex/agents/schema-reviewer.toml
templates/project/.codex/agents/docs-consistency-reviewer.toml
templates/project/.codex/agents/release-gate-runner.toml
```

### P4：迁移与跨平台专项

目标：降低旧环境和非 Windows 环境的安装摩擦。

可做项：

- `codex memory migrate-legacy-global --dry-run`
- `codex memory migrate-legacy-global --confirm`
- `hook_launcher.sh` / `mcp_launcher.sh`
- Python-first hook/MCP command

## 7. 文档维护规则

- 不把官方建议直接写成“已实现能力”。
- 每个优化项必须标注安装传播落点。
- 涉及安全边界时，必须说明不能保证什么。
- 涉及 SubAgent 时，不得设置固定总时长；timeout 只能作为观察窗口。
- 涉及发布包时，必须保持 `.codex/memories`、`.codex/harness/tasks`、数据库、JSONL、dist 和缓存排除。
- 若官方文档更新，先更新本文的参考链接、路径差异和传播落点，再改运行时代码。

## 8. 验证缺口复盘

这次 `install.bat` 问题暴露的核心不是单个脚本语法，而是验证矩阵缺了一条关键路径。

之前的验证偏向这些项目：

- `install_codex_memory.py --check`：只读检查当前环境状态，不会复制 home plugin、不写全局 AGENTS、不安装 bundled skills，也不碰 PowerShell profile。
- `install.sh` 语法和 `--check`：覆盖 shell 包装入口和依赖检查，但仍不是普通安装。
- Python 单元测试：主要 mock 安装函数和局部 helper，能证明函数契约，但不能证明 `install.bat`、release package、环境变量、真实文件写入组合起来一定可用。
- `codex xhigh review --uncommitted`：能审查代码风险，但不能替代缺失的动态 smoke gate。

因此，若普通首次安装路径里出现 batch 参数传递、home 目录解析、copy/junction、skills 复制、全局 AGENTS 写入或 marketplace 写入问题，旧 gate 不一定会发现。这属于验证设计缺陷，不应该只靠人工记得执行一次安装。

修复后的验证要求：

- `scripts/verify_project.py` 必须包含普通安装 smoke test。
- smoke test 必须从 release package 解压目录运行，而不是直接调用源码里的 Python installer。
- smoke test 必须使用临时 `CODEX_MEMORY_HOME`、`USERPROFILE`、`HOME` 和 `CODEX_HOME`，避免污染维护者真实用户目录。
- smoke test 必须运行 `cmd /c install.bat --mode copy`，覆盖 batch 入口、Python runtime 解析、home plugin 复制、Codex config、全局 AGENTS、home marketplace、PowerShell profile 和 bundled skills。
- smoke test 必须断言 `harness-release-gate` 等 7 个 bundled skills 完成首次安装。

`CODEX_MEMORY_HOME` 是安装器和验证用的高级覆盖变量，用于把用户级安装目标重定向到隔离目录；正常用户不需要设置它。`CODEX_HOME` 仍按 Codex 官方语义控制 Codex 配置根目录。

## 9. 当前结论

原文列出的优化大多方向合理，但优先级需要调整：最先做的不是把更多配置写到维护者本机，而是把合理优化沉淀进安装器、随包 skills、模板和 bootstrap。这样新环境安装项目后，才能同步获得相同的规则、技能和验证入口。
