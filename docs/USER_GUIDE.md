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
- `.codex/shared/README.md`
- `.codex/shared/index.json`
- `.codex/shared/decisions/`、`facts/`、`workflows/`、`routes/`

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

`.gitignore` 已放行 `.codex/shared/**`，同时继续忽略 `.codex/memories/`、`.codex/harness/tasks/`、数据库和 JSONL。提交共享记忆前仍必须人工 review。

把本地任务总结提升为项目共享记忆：

```powershell
codex memory promote --task-id <task-id> --kind fact
codex memory shared validate
codex memory shared index rebuild
```

完整分层、冲突处理和提升流程见：

```text
docs/MEMORY_LAYERING.md
```

当前记忆检索默认使用 SQLite、JSONL、Markdown summary 和本地 `rg` 检索，不依赖向量数据库。原因和后续可选接入路线见：

```text
docs/MEMORY_RETRIEVAL_STRATEGY.md
```

## Harness Engineering 对标

本项目已经具备本地 memory、harness 生命周期、验证回写、workspace routing、SubAgent binding/dispatch plan 和基础 release gate 的 MVP，但还没有内建真实 SubAgent 自动执行器、向量数据库或 eval replay 平台。

如果需要确认当前能力边界：

```text
docs/EXTERNAL_BENCHMARK.md
```

如果需要按多角色方式执行复杂任务，当前应按文档里的角色协议记录 artifact，并可用 `codex workspace schedule` 生成 dispatch plan；不要假设项目会自动启动多个真实 SubAgent：

```text
docs/SUBAGENT_WORKFLOW.md
```

代码变更的审核优先使用 Codex CLI 的专用 review 入口，而不是让通用 SubAgent 自行承担最终审核：

```powershell
codex xhigh review --uncommitted
```

SubAgent Reviewer 适合做窄范围专题审查，例如只看某个 route binding、某类安全风险或某组测试覆盖。最终提交或发布前，仍应以 `codex xhigh review --uncommitted` 作为代码审核 gate。

如果当前宿主支持 SubAgent，大 diff 或长耗时审查可以派发一个专门的 XHigh Review Runner。它只负责执行 `codex xhigh review --uncommitted`，必要时降级到 `codex-raw xhigh review --uncommitted`，并回传退出状态和 findings；它不是让通用 SubAgent 自己重新审查。

如果需要理解完整实现后的日常开发流程、自动路由、SubAgent、诊断日志、验证聚合和 memory 沉淀闭环，可先看完整流程图：

```text
docs/FULL_DEVELOPMENT_WORKFLOW.md
```

如果代码任务需要运行时反馈，可以临时开启 AI 诊断日志，但必须通过统一开关控制，并在发布前关闭：

```text
docs/AI_DIAGNOSTIC_LOGGING.md
```

如果当前项目是 Unity、LayaBox/LayaAir 或 Cocos Creator 游戏客户端，可参考游戏客户端专项工作流。该文档说明如何把玩法、UI、资源、性能、热更新和发版检查接入 harness：

```text
docs/GAME_CLIENT_WORKFLOW.md
```

如果 Codex 在一个 workspace 下运行，而该 workspace 同时包含客户端、服务器、后台、文档、美术工程或发布脚本，应优先参考 workspace 自适应路由。它说明如何自动识别子项目、给 SubAgent 绑定项目路由，并处理跨项目综合事务：

```text
docs/WORKSPACE_ADAPTIVE_ROUTING.md
```

当前仓库已经提供 workspace routing 的 schema 和项目配置模板：

```text
schemas/workspace_project_inventory.schema.json
schemas/workspace_routing_config.schema.json
schemas/workspace_route_plan.schema.json
schemas/subagent_route_binding.schema.json
schemas/verification_aggregation.schema.json
templates/project/.codex/harness/workspace-routing.json
```

这些文件是 SubAgent binding runtime、scope guard、coordinator 汇总、dispatch plan 和生命周期软集成的契约基础；scanner、route planner、最小 verification aggregation、binding/scope-check/summarize/schedule 都已有本地入口。

当前也已经提供只读 workspace scanner：

```powershell
codex workspace doctor
codex workspace scan
codex workspace route --task-file task.json
codex workspace route --changed
codex workspace verify --route-file route.json
codex workspace verify --task-file task.json --no-run
codex workspace bind --route-file route.json
codex workspace schedule --route-file route.json
codex workspace scope-check --binding-file binding.json --touched-path client/Assets/App.cs
codex workspace summarize --bindings-file bindings.json --artifact-file agent-result.json
codex workspace game-client init --engine unity --project-cwd client
```

`doctor/scan` 会读取 `.codex/harness/workspace-routing.json`，再扫描当前 workspace 中常见的 Unity、LayaBox/LayaAir、Cocos Creator、服务器、后台、文档、美术和发布工程信号，输出 project inventory。`route` 会根据任务文件、working set、cwd 或 `--changed` 的 Git diff 生成 route plan。`verify` 会按 route plan 聚合多项目 verification profile，缺失 profile 或 command 会记录 gap，release route 会执行基础 AI 诊断日志 gate。`bind/scope-check/summarize` 用于生成 SubAgent route binding、检查 touched paths 是否越权，并汇总冲突。`schedule` 用于生成 coordinator/specialist dispatch plan。`game-client init/template` 会写入或输出 Unity/Laya/Cocos verification profile 模板，是少数会按用户命令修改业务项目 `.codex/harness` 配置的 workspace 子命令。

在 memory 生命周期中，workspace routing 已做软集成：

- `before_task` 自动生成 route plan 和 SubAgent bindings，并写入 task metadata。
- `after_tool` 根据 touched paths 重算 route/bindings，并执行 scope guard；多项目时会按 specialist assigned scope 分发路径，避免误报未触达 specialist。
- `before_response` 输出 `workspace_routing_review`，报告低置信路由、routing 降级、verification gap 和 scope gap。

这仍不是真实 SubAgent 自动执行器。当前系统只准备 binding、scope guard、dispatch plan 和 review，是否实际启动多个 SubAgent 仍由 Codex 宿主能力或人工编排决定。

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
