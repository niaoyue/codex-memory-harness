# 用户指南

## 一句话说明

Codex Memory Harness 让 Codex 在本机获得可控的外部记忆和任务运行时能力。用户正常使用时只需要继续输入 `codex`，不需要手动维护记忆。

## 首次安装

```powershell
cd H:\dev\company\codex-memory-harness
.\install.bat
```

Linux/macOS shell，或 Git Bash、MSYS、Cygwin 等 POSIX shell 环境中运行：

```sh
sh ./install.sh
```

安装脚本会先检查 Python 3.11+。如果缺少 Python、版本过低或未加入 PATH，它会提示 `winget install --id Python.Python.3.12 -e --source winget`、Homebrew/apt/dnf 等常见安装命令、手动安装地址和重新运行方式。

`install.sh` 会在 Linux/macOS 默认写入 POSIX hook/MCP launcher，并向 `~/.profile`、`~/.bashrc`、`~/.zshrc` 写入带标记块的 `codex`/`codexm` shell wrapper；在 Windows POSIX shell 中如检测到 `powershell`，默认仍写入 PowerShell launcher。可用 `CODEX_MEMORY_LAUNCHER_FAMILY=posix|powershell` 显式指定。

如果希望脚本尝试代装 Python，可以显式运行：

```powershell
.\install.bat --install-python
```

或：

```sh
sh ./install.sh --install-python
```

这个能力只在用户显式传参时触发；Windows 使用 `winget`，POSIX shell 按可用包管理器尝试 Homebrew、apt、dnf、yum 或 pacman。默认安装不会静默修改系统环境。

安装器还会修复必要的官方 Codex 配置，确保 `$CODEX_HOME/config.toml` 中存在 `[features] hooks = true`，让插件 hooks 走官方生命周期。

安装器会默认离线安装 `plugins/codex-memory/skills/bundled-skills.json` 登记的所有随包技能到 `~/.agents/skills/<skill-name>`。当前 manifest 覆盖 security、GitHub、CLI、迁移、release gate、需求澄清、接口设计、TDD、提交、review、PRD、重构、文档、图像、OpenAI docs、plugin/skill 创建等场景。

这些技能已经 vendor 在发布包里，安装时不会联网拉取 GitHub。如果目标技能目录已存在且内容不同，安装器会先把旧目录移动到 `~/.agents/skills/.codex-memory-backups/`，再刷新为当前包版本。若只想安装 memory/harness 接入、不安装 bundled skills，可运行：

任务执行时还会按 skill-first 规则匹配当前可用技能。需求或策划文档不清时按 `grill-me` 风格列出问题；创建接口、协议、schema、CLI 或跨模块契约前优先使用 `design-an-interface` 比较多个方案；PRD、TDD、代码 review、Git 提交、安全审查和 GitHub CI 等场景按技能路由表触发。完整规则见：

- `docs/SKILL_ROUTING_AND_DEFAULT_GOVERNANCE.md`

```powershell
.\install.bat --skip-skills
```

POSIX shell：

```sh
sh ./install.sh --skip-skills
```

如果已经安装的是当前版本，安装器会提示 `already_installed`，不会重新安装插件，但仍会刷新全局 AGENTS 规则、hook/MCP、profile、marketplace 和 bundled skills。

如果机器上已经有旧版本或其他项目安装的 `codex-memory`，默认安装就是更新：`install.bat`、`install.ps1`、`install.sh` 和 `codex memory install` 都会把 `~/plugins/codex-memory` 更新到当前包。旧普通目录会先备份；junction 或 symlink 会重指向当前版本。它不会修改真实 Codex CLI 文件。`--update-existing` / `-UpdateExisting` 仍可显式写出，`--replace-existing` / `-ReplaceExisting` 仍可作为兼容别名使用。

如果只想保守检查、不替换旧 home plugin，可运行：

```powershell
.\install.bat --no-update-existing
```

POSIX shell：

```sh
sh ./install.sh --no-update-existing
```

## 日常使用

```powershell
codex
```

推荐主路径是官方 Codex config/hooks/MCP；PowerShell/POSIX shell profile 注册的 wrapper 负责兼容旧环境、诊断入口和命令分流。当前 shell 中输入 `codex` 仍会先经过 wrapper 执行 bootstrap/doctor，然后启动真实 Codex；不经过 wrapper 的 Codex 客户端应依赖官方 hooks/MCP。

可用入口：

- `codex`：普通无感入口。
- `codexm`：显式 memory wrapper 入口。
- `codex memory doctor`：诊断当前项目 memory/harness 状态，并检查官方 `features.hooks`、sandbox/approval、AGENTS.override、官方 Memories 和插件 hook 覆盖情况。
- `codex memory init`：初始化缺失的项目 `.codex` memory/harness 配置。
- `codex memory install/update/check-install`：安装、更新或检查插件接入。
- `codex memory mine status|run`：查看或执行自动历史记忆挖掘。
- `codex memory candidates list|accept|reject|deprecate`：治理自动挖掘出的记忆候选。
- `codex memory retention status|cleanup --task-id <task-id> [--confirm]`：查看记忆规模，或按任务精确归档/清理；默认 dry-run，只有 `--confirm` 执行写入。
- `codex memory eval create|list|run`：把失败或高价值 artifact 转为本地 deterministic eval replay，并执行无网络安全检查。
- `codex harness ...`：运行 harness 任务生命周期命令。
- `codex harness verify ...`：运行当前项目配置化验证。
- `codex review preflight/status/plan`：在最终 xhigh review 前执行确定性 preflight、查看 diff fingerprint 和 reviewable slices。
- `codex openspec upstream status|sync|verify`：查看、刷新或校验官方 OpenSpec schema/templates/license/package metadata 的 pinned upstream snapshot；这是 Harness 对目标项目提供的初始化/维护能力，默认顺序是 `sync --version 1.3.1` 后 `verify`，不代表目标项目自身已经实现 OpenSpec 业务能力。
- `codex package build/verify`：维护者打包和项目健康检查入口。
- `codex-memory-doctor`：只检查当前窗口接入状态，不启动 Codex。
- `codex-raw`：绕过 memory wrapper，直接启动真实 Codex。

`codex memory hook ...` 只是在当前 shell 已加载 memory wrapper 时可用的便利别名，不是官方 Codex CLI 子命令。自动化、hook 配置和不经过 wrapper 的客户端应直接调用 hook launcher 的 `--event` 模式，或依赖官方 `hooks.json` -> `hook_launcher.cmd` / `hook_launcher.sh` -> `hook_bridge.py` 链路。

## 项目接入

进入任意项目目录后运行：

```powershell
codex memory doctor
```

如果项目缺少 `.codex/memories` 或 `.codex/harness`，正常启动 `codex` 时 wrapper 会自动初始化。官方 hooks 可用时，插件会通过 `UserPromptSubmit`、`PostToolUse`、`Stop` 自动桥接生命周期；也可以显式执行：

```powershell
codex memory init
```

手动调试生命周期时使用稳定 launcher 入口；`<插件目录>` 通常是 `%USERPROFILE%\plugins\codex-memory` 或 `$HOME/plugins/codex-memory`，也可能是安装器输出的自定义位置。

```powershell
$HOOK_LAUNCHER = "$env:USERPROFILE\plugins\codex-memory\scripts\hook_launcher.ps1"
$POWERSHELL = Get-Command pwsh -ErrorAction SilentlyContinue
if (-not $POWERSHELL) { $POWERSHELL = Get-Command powershell -ErrorAction Stop }
$POWERSHELL = $POWERSHELL.Source
& $POWERSHELL -NoProfile -ExecutionPolicy Bypass -File $HOOK_LAUNCHER --event before_response --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
```

```sh
HOOK_LAUNCHER="$HOME/plugins/codex-memory/scripts/hook_launcher.sh"
sh "$HOOK_LAUNCHER" --event before_response --memory-scope project --memory-cwd <当前项目目录> --payload-file <payload.json>
```

项目会获得：

- `.codex/memories/`
- `.codex/harness/commands.json`
- `.codex/harness/project_profile.json`
- `.codex/harness/workspace-routing.json`
- `.codex/shared/README.md`
- `.codex/shared/index.json`
- `.codex/shared/decisions/`、`facts/`、`workflows/`、`routes/`
- `.codex/agents/`：项目级 Codex custom agents 模板，包括 Workspace Coordinator、Implementation Specialist、Route Review Specialist 和 XHigh Review Runner；不会默认写入用户全局 agents。

注意：当前 wrapper 的普通启动会在缺少项目 memory、`commands.json`、`project_profile.json`、`.codex/shared` 或 `.codex/shared/index.json` 时自动补齐项目配置；如果旧项目只缺 `.codex/harness/workspace-routing.json`，`codex memory doctor` 会提示，需显式运行 `codex memory init` 补齐。

## Review Gate 辅助命令

最终代码审核先创建本地 candidate commit，记录被审 commit SHA，再用 Review a commit 只审核该提交引入的变更：

```powershell
$commitSha = git rev-parse HEAD
codex xhigh review --commit $commitSha
```

辅助命令用于减少进入最终 gate 前的确定性失败：

```powershell
codex review preflight --mode uncommitted
codex review status --mode uncommitted
codex review plan --mode uncommitted
codex review ledger show
codex review findings list
codex review findings resolve <finding-id> --review-id <review-id>
```

`preflight` 会运行 `git diff --check`、敏感扫描、打包边界检查和验证配置摘要，并写入 `.codex/harness/review/preflight.json`。`status` 和 `record` 会把 review 结果绑定到 runner/preflight 已审 diff fingerprint；clean 结果缺少已审 fingerprint 或与当前 diff 不一致时会写入 invalidated。`findings resolve` 按 review/fingerprint 作用域记录修复证据，不代表 gate 通过，仍必须重新运行最终 xhigh review。

## 旧全局 Memory Marker 迁移

旧版本如果把 harness runtime marker 写在官方 `$CODEX_HOME/memories` 目录，先做 dry-run：

```powershell
codex memory migrate-legacy-global --dry-run
```

确认 manifest、checksum、backup 路径和 action 后，再显式执行：

```powershell
codex memory migrate-legacy-global --confirm
```

迁移工具不会静默覆盖 harness global 目录已有不同内容；冲突时会归档旧 source 并在 manifest 中给出手工回滚说明。

## 记忆分层

Codex Memory 分三层：

| 层级 | 位置 | 是否提交 | 适合内容 |
|---|---|---|---|
| 官方 Codex Memories | `C:\Users\<你>\.codex\memories` | 不提交 | 官方自动生成的个人长期记忆 |
| 用户全局层 | `C:\Users\<你>\.codex\codex-memory-harness\memories` | 不提交 | 跨项目长期偏好、通用工作流、用户明确要求全局沉淀的非敏感规则 |
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
C:\Users\<你>\.codex\codex-memory-harness\memories
```

官方 Codex Memories 的默认目录是：

```text
C:\Users\<你>\.codex\memories
```

本项目不会把 SQLite、JSONL 或 harness 运行态写入官方目录。兼容策略见：

```text
docs/OFFICIAL_CODEX_MEMORY_COMPATIBILITY.md
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

自动历史记忆挖掘的目标是让用户不需要每次手动整理习惯。设计方案要求系统从历史事件中自动发现重复的低风险工作流偏好、命令偏好和纠正模式；高置信低风险候选可自动进入当前用户的项目私有或全局私有记忆，高风险、冲突或证据不足的候选只进入待确认队列。当前这是计划中的 runtime 能力，方案见：

```text
docs/AUTOMATED_MEMORY_MINING.md
```

## Review Gate 优化

本节校正依据（2026-05-08 本地只读核对）：现有 review runner、SubAgent review 语义和最终 gate 边界见 `docs/SUBAGENT_WORKFLOW.md`、`plugins/codex-memory/scripts/review_gate_runner.py`、`plugins/codex-memory/scripts/xhigh_review_dispatch.py`。

代码变更的最终审核以被审提交 SHA 对应的 `codex xhigh review --commit <commit-sha>` 为准。第二个问题的优化方向不是跳过 review，而是把 review 前准备态、commit fingerprint、XHigh Review Runner 恢复、findings ledger 和 reviewable slice 固化下来，减少单次 review 的文件数量、基础设施失败重开和 findings 修复后重复浪费的总耗时。

当前这是计划中的 runtime 能力，方案见：

```text
docs/REVIEW_GATE_OPTIMIZATION.md
```

方案要求后续实现时满足这些体感：

- preflight 失败时先修 deterministic 问题，不启动 xhigh review。
- review 结果必须绑定当前 diff fingerprint；diff 变化后旧 review 自动失效。
- 大 diff 可先拆成 reviewable slices，降低最终 gate 失败率。
- runner 遇到 429、5xx 或 timeout 时按既有退避策略恢复，不把基础设施失败当通过。
- findings 修复后必须重新跑最终 gate。

## Session Worktree 绑定

本节校正依据（2026-05-08 本地只读核对）：现有 workspace routing、SubAgent route binding 和 scope guard 入口见 `docs/WORKSPACE_ADAPTIVE_ROUTING.md`、`plugins/codex-memory/scripts/workspace_subagents.py`、`plugins/codex-memory/scripts/subagent_scheduler.py`。

第三个问题的目标是让每个写任务都有明确 checkout。只有一个活跃 session 写某项目时，可以直接用当前 checkout；如果已有活跃写 session 绑定同一项目，新 session 必须创建或复用自己的隔离 worktree。任务结束时释放绑定；session 意外退出、中断、长时间遗忘和一个任务多个 session 并行，都通过 lease、heartbeat、stale cleanup、managed worktree 和 scope guard 管理。

当前这是计划中的 runtime 能力，方案见：

```text
docs/SESSION_WORKTREE_BINDING.md
```

方案要求后续实现时满足这些体感：

- 写任务开始时返回 `effective_cwd`，后续命令和编辑都在该目录执行。
- 第二个活跃写 session 自动获得 managed worktree 和 session branch。
- 同一 session 继续同一 task 时复用原 binding。
- dirty 或 branch ahead 的 stale worktree 不自动删除，只提示 recover / review。
- clean managed worktree 只能在 dry-run 可见、confirm 后清理。

## Harness Engineering 对标

本项目已经具备本地 memory、harness 生命周期、验证回写、workspace routing、SubAgent binding/dispatch plan、Codex SubAgent receipt dogfood 和基础 release gate 的 MVP，但没有内建独立 SubAgent 子进程执行器、向量数据库或完整 eval 平台。

如果需要确认当前能力边界：

```text
docs/EXTERNAL_BENCHMARK.md
```

如果需要把官方 Codex 的推荐用法对齐到本项目的后续改造路线，可先看官方建议对齐文档。它把官方的 AGENTS.md、hooks、MCP、skills、SubAgent、安全 profile 和验证闭环建议，整理为本项目的优先级和验收标准：

```text
docs/CODEX_OFFICIAL_ALIGNMENT.md
```

如果需要按多角色方式执行复杂任务，当前应按文档里的角色协议记录 artifact，并可用 `codex workspace schedule` 生成 dispatch plan；主 Agent 负责把 `host_spawn_requests` 派发给 Codex SubAgent：

```text
docs/SUBAGENT_WORKFLOW.md
```

代码变更的审核优先使用 Codex CLI 的专用 review 入口，而不是让通用 SubAgent 自行承担最终审核：

```powershell
codex xhigh review --commit <commit-sha>
```

SubAgent Reviewer 适合做窄范围专题审查，例如只看某个 route binding、某类安全风险或某组测试覆盖。最终 push 或发布前，仍应以 `codex xhigh review --commit <commit-sha>` 审核每个候选提交或修复提交作为代码审核 gate。

如果当前宿主支持 SubAgent，大 diff 或长耗时审查应优先派发一个专门的 XHigh Review Runner。它只负责执行 `codex xhigh review --commit <commit-sha>`，必要时降级到 `codex-raw -- review -c model_reasoning_effort="xhigh" --commit <commit-sha>`，并回传退出状态和 findings；它不是让通用 SubAgent 自己重新审查。等待策略按 stdout/stderr 和状态进度观察：持续有输出就继续等待，宿主等待窗口到期只代表本轮观察结束，不得因此中断或判失败，也不得再套固定总时长。

review findings 全部修复、最终 review gate 无阻断问题且验证通过后，流程必须创建一个本地 git commit 记录当前版本。若工作树包含用户无关改动，应只提交本轮相关文件；无法安全隔离时必须说明未提交原因。

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
codex workspace project-template init --domain game_server --project-cwd server --language go
codex workspace project-template init --domain backoffice_web --project-cwd admin --framework vue
codex workspace project-template init --domain design_docs --project-cwd docs
codex workspace project-template init --domain art_pipeline --project-cwd art
```

`doctor/scan` 会读取 `.codex/harness/workspace-routing.json`，再扫描当前 workspace 中常见的 Unity、LayaBox/LayaAir、Cocos Creator、服务器、后台、文档、美术和发布工程信号，输出 project inventory。`route` 会根据任务文件、working set、cwd 或 `--changed` 的 Git diff 生成 route plan。`verify` 会按 route plan 聚合多项目 verification profile，缺失 profile 或 command 会记录 gap，release route 会执行基础 AI 诊断日志 gate。`bind/scope-check/summarize` 用于生成 SubAgent route binding、检查 touched paths 是否越权，并汇总冲突。`schedule` 用于生成 coordinator/specialist dispatch plan。`game-client init/template` 会写入或输出 Unity/Laya/Cocos verification profile 模板；`project-template init/template` 会写入或输出服务器、后台/Web、文档和美术工程 profile 模板。它们都是少数会按用户命令修改业务项目 `.codex/harness` 配置的 workspace 子命令。

从普通 harness 升级到 workspace routing 的步骤、边界和回退方式见：

```text
docs/WORKSPACE_ROUTING_MIGRATION.md
```

在 memory 生命周期中，workspace routing 已做软集成：

- `before_task` 自动生成 route plan 和 SubAgent bindings，并写入 task metadata。
- `after_tool` 根据 touched paths 重算 route/bindings，并执行 scope guard；多项目时会按 specialist assigned scope 分发路径，避免误报未触达 specialist。
- `before_response` 输出 `workspace_routing_review`，报告低置信路由、routing 降级、verification gap 和 scope gap。

当前软集成会把 route plan、bindings、scope guard 和 runtime decision 写入 task metadata / artifact，并在任务完成时按 `memory_plan` 自动生成 `.codex/shared` proposed 草稿，区分 workspace summary 与子项目 facts。proposed 草稿不是 accepted 团队事实；仍需要人工 review、脱敏和 validate 后才能提升为共享事实。

生命周期 metadata 还会写入 `workspace_routing.subagent_runtime`，并在 `workspace_routing_review.subagent_runtime` 中回显当前决策：单项目串行、建议但未启动、用户要求但未启动，或已经观察到 route-bound/SubAgent-style artifact。该字段用于解释主 agent 直接执行或未启动 SubAgent 的原因。

项目可以把 SubAgent 派发授权持久化到 `.codex/harness/project_profile.json`，或 workspace 级 `.codex/harness/workspace-routing.json`。例如正式 implementation 任务默认允许宿主 SubAgent 派发：

```json
{
  "subagent_runtime_policy": {
    "execution_model": "host_subagent_or_manual",
    "autostart": false,
    "task_types": ["implementation"],
    "risk_levels": ["medium", "high"],
    "reason": "Project policy authorizes Harness SubAgent dispatch for normal implementation tasks when the host supports it."
  }
}
```

当 route plan 命中该 policy 时，lifecycle 会写入 `host_dispatch_allowed=true`、`dispatch_plan_required=true` 和 `main_agent_action=read_dispatch_plan_and_call_host_subagents`。这解决“单项目单 specialist 被默认 main_agent_serial 压住”的问题，但实际派发仍取决于当前 Codex 会话是否允许或提供 SubAgent 能力；这不是插件内建子进程，也不是 T59 需要等待的额外 API。

没有项目 policy 时，runtime 也会做通用自动判断。planner 会综合：

- `requirements_gate.task_intent`：例如 `feature_story`、`system_change`、`release_gate`。
- `route_plan.task_type`：例如 `implementation`、`ui`、`contract`、`release`。
- `risk_level`、route 数量、scope 大小、是否复杂应用级任务、是否 review gate。

当这些信号表明任务是功能 story、系统改动、高风险、发布 gate、跨 route 或复杂应用级任务时，会触发 `autonomous_task_analysis` 或对应的 `complex_task` / `route_policy` / `xhigh_review_gate`。普通低风险小修仍保持 `main_agent_serial`。需要审查的实现任务会在 worker specialist 外额外生成 `Route Review Specialist`，最终代码审核仍优先使用 `codex xhigh review --commit <commit-sha>` 审核被审提交。

这不是插件内建的独立 SubAgent 子进程执行器。当前系统准备 binding、scope guard、dispatch plan、runtime decision 和 review；实际派发由主 agent 使用 Codex SubAgent 能力完成，并通过 receipt/readiness report 回写结果。

Workspace routing 的实现拆分和当前进度见：

```text
.codex/harness/backlog/workspace-routing-tasks.md
```

## 打包给别人

维护者在项目根目录运行：

```powershell
codex package build
```

把 `dist/codex-memory-harness-0.1.1.zip` 发给用户。用户解压后运行：

```powershell
.\install.bat
```

POSIX shell：

```sh
sh ./install.sh
```

发布包不会包含维护者本机的根目录 `.codex` 运行态；用户项目的 `.codex/memories` 和 `.codex/harness` 由 bootstrap 在目标机器上初始化。
发布包会包含 `plugins/codex-memory/skills/openai-curated/`、`plugins/codex-memory/skills/local/` 和 `plugins/codex-memory/skills/bundled-skills.json`，用于目标机器离线安装 bundled Codex skills。

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
.\install.bat --uninstall
```

POSIX shell：

```sh
sh ./install.sh --uninstall
```

卸载不会删除项目 memory。需要删除某个项目的 memory 时，由用户手动处理对应项目的 `.codex/memories`，不要由自动脚本递归删除。
卸载也不会默认删除 `~/.agents/skills` 中已有的技能目录，避免误删用户自己安装或修改过的技能。
