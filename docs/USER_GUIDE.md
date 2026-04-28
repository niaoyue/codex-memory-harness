# 用户指南

## 一句话说明

Codex Memory Harness 让 Codex 在本机获得可控的外部记忆和任务运行时能力。用户正常使用时只需要继续输入 `codex`，不需要手动维护记忆。

## 首次安装

```powershell
cd H:\dev\company\codex-memory-harness
.\install.ps1
```

如果已经安装的是当前版本，安装器会提示 `already_installed`，不会重新安装插件。

如果机器上已经有旧版本或其他项目安装的 `codex-memory`，默认安装不会覆盖它。需要更新到当前包时显式运行：

```powershell
.\install.ps1 -UpdateExisting
```

这会把 `~/plugins/codex-memory` 更新到当前包。它不会修改真实 Codex CLI 文件。`-ReplaceExisting` 仍可作为兼容别名使用，但推荐新命令写法 `-UpdateExisting`。

## 日常使用

```powershell
codex
```

`codex` 会先经过 PowerShell profile 注册的 wrapper，执行 bootstrap/doctor，然后启动真实 Codex。

可用入口：

- `codex`：普通无感入口。
- `codexm`：显式 memory wrapper 入口。
- `codex memory doctor`：诊断当前项目 memory/harness 状态。
- `codex memory init`：初始化缺失的项目 `.codex` memory/harness 配置。
- `codex memory install/update/check-install`：安装、更新或检查插件接入。
- `codex harness ...`：运行 harness 任务生命周期命令。
- `codex harness verify ...`：运行当前项目配置化验证。
- `codex package build/verify`：维护者打包和项目健康检查入口。
- `codex-memory-doctor`：只检查当前窗口接入状态，不启动 Codex。
- `codex-raw`：绕过 memory wrapper，直接启动真实 Codex。

## 项目接入

进入任意项目目录后运行：

```powershell
codex memory doctor
```

如果项目缺少 `.codex/memories` 或 `.codex/harness`，正常启动 `codex` 时 wrapper 会自动初始化。也可以显式执行：

```powershell
codex memory init
```

项目会获得：

- `.codex/memories/`
- `.codex/harness/commands.json`
- `.codex/harness/project_profile.json`

## 记忆分层

Codex Memory 分三层：

| 层级 | 位置 | 是否提交 | 适合内容 |
|---|---|---|---|
| 用户全局层 | `C:\Users\<你>\.codex\memories` | 不提交 | 跨项目长期偏好、通用工作流、用户明确要求全局沉淀的非敏感规则 |
| 项目私有层 | `<项目根目录>/.codex/memories` | 不提交 | 当前项目的本地任务状态、工具事件、summary、distilled 草稿 |
| 项目共享层 | `<项目根目录>/.codex/shared` | 可提交，需审查 | 团队确认的项目事实、架构决策、流程、路由和验证规则摘要 |

默认写项目私有层：

```text
<项目根目录>/.codex/memories
```

只有这些内容才应写用户全局层：

- 跨项目长期偏好。
- 反复复用的个人工作流。
- 用户明确要求全局沉淀的规则。

用户全局层位置：

```text
C:\Users\<你>\.codex\memories
```

项目共享层不能直接提交 `.codex/memories`。应先从本地 summary、decision、verification 中提取稳定、脱敏、可审查的 Markdown，再放入 `.codex/shared`。

完整分层、冲突处理和提升流程见：

```text
docs/MEMORY_LAYERING.md
```

当前记忆检索默认使用 SQLite、JSONL、Markdown summary 和本地 `rg` 检索，不依赖向量数据库。原因和后续可选接入路线见：

```text
docs/MEMORY_RETRIEVAL_STRATEGY.md
```

## Harness Engineering 对标

本项目已经具备本地 memory、harness 生命周期和验证回写的 MVP，但还没有内建 SubAgent 调度器、向量数据库或 eval replay 平台。

如果需要确认当前能力边界：

```text
docs/EXTERNAL_BENCHMARK.md
```

如果需要按多角色方式执行复杂任务，当前应按文档里的角色协议记录 artifact，而不是假设项目会自动启动多个 SubAgent：

```text
docs/SUBAGENT_WORKFLOW.md
```

如果当前项目是 Unity、LayaBox/LayaAir 或 Cocos Creator 游戏客户端，可参考游戏客户端专项工作流。该文档说明如何把玩法、UI、资源、性能、热更新和发版检查接入 harness：

```text
docs/GAME_CLIENT_WORKFLOW.md
```

如果 Codex 在一个 workspace 下运行，而该 workspace 同时包含客户端、服务器、后台、文档、美术工程或发布脚本，应优先参考 workspace 自适应路由。它说明如何自动识别子项目、给 SubAgent 绑定项目路由，并处理跨项目综合事务：

```text
docs/WORKSPACE_ADAPTIVE_ROUTING.md
```

Workspace routing 的实现拆分和当前进度见：

```text
docs/WORKSPACE_ROUTING_TASK_LIST.md
```

## 打包给别人

维护者在项目根目录运行：

```powershell
codex package build
```

把 `dist/codex-memory-harness-0.1.0.zip` 发给用户。用户解压后运行：

```powershell
.\install.ps1
```

发布包不会包含维护者本机的根目录 `.codex` 运行态；用户项目的 `.codex/memories` 和 `.codex/harness` 由 bootstrap 在目标机器上初始化。

## 验证安装

```powershell
codex memory check-install
codex memory doctor
codex-memory-doctor
```

`check-install` 和 `doctor` 都是只读检查，不会写文件。

验证当前仓库健康状态：

```powershell
codex package verify
```

验证当前项目 harness 配置：

```powershell
codex harness verify run --profile primary
```

## 回退

临时绕过：

```powershell
codex-raw
```

禁用当前命令中的 wrapper：

```powershell
$env:CODEX_MEMORY_DISABLE_WRAPPER = "1"
codex
```

卸载 profile 和 marketplace 接入：

```powershell
.\uninstall.ps1
```

卸载不会删除项目 memory。需要删除某个项目的 memory 时，由用户手动处理对应项目的 `.codex/memories`，不要由自动脚本递归删除。
