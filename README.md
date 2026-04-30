# Codex Memory Harness

Codex Memory Harness 是一个本地工具包，用来给 Codex 增加可控的外部记忆、任务运行时、验证闭环和任务总结沉淀能力。

它不会修改模型内部记忆，也不会替换真实的 `codex` 可执行文件。它只通过本地插件、PowerShell profile wrapper、全局规则和项目级 `.codex` 配置接入。

## 它解决什么问题

默认的 Codex 会话之间没有稳定的项目上下文。这个项目把“当前任务是什么、约束是什么、改了哪些文件、验证结果是什么、任务完成后要沉淀什么”保存到本机项目目录里，让后续 Codex 窗口可以继续接上。

核心能力：

- 项目私有记忆：保存任务状态、工作集、最近发现、项目决策和任务总结。
- 官方 Memories 兼容：保留 `$CODEX_HOME/memories` 给 Codex 官方自动记忆，本插件全局层写入 `$CODEX_HOME/codex-memory-harness/memories`。
- 记忆分层：区分用户全局层、项目私有层和项目共享层，避免把 raw 运行态当团队知识提交。
- 共享记忆提升：从本地任务 summary/decision 生成 `.codex/shared` 可审查 Markdown，并可校验和重建索引。
- 启动自检：启动 `codex` 前自动检查插件、项目 `.codex` 配置和推荐环境变量。
- Harness 生命周期：用 `start`、`checkpoint`、`complete` 记录任务过程。
- 验证回写：运行项目配置化验证，并把结果写回 harness artifact。
- 代码审核策略：最终 gate 仍以 Codex CLI 的 `codex xhigh review --uncommitted` 为准；大改动可让 SubAgent 作为并行命令执行器运行该 gate，通用 SubAgent reviewer 只做专题辅助审查。
- 写入前敏感扫描：memory、harness artifact 和 distillation 写入前先脱敏，高危私钥块阻断。
- AI 诊断日志策略：编码和 AI 调试期允许临时观测，发布和生产构建必须关闭。
- Workspace routing schema：提供 project inventory、显式配置、route plan、SubAgent binding 和 verification aggregation 的结构化契约。
- Workspace 只读路由：`codex workspace doctor/scan/route` 输出子项目 inventory 和 route plan，不修改业务项目文件。
- Workspace 验证聚合：`codex workspace verify` 按 route plan 聚合多项目 verification profile 和 gap。
- SubAgent 绑定与守卫：`codex workspace bind/scope-check/summarize` 生成 route binding、检查越权路径并汇总冲突。
- SubAgent 调度计划：`codex workspace schedule` 根据 route plan 生成 specialist/coordinator dispatch plan，并可写入 checkpoint。
- 游戏客户端模板：`codex workspace game-client init/template` 为 Unity、LayaBox/LayaAir、Cocos Creator 生成 verification profile 模板。
- AI 诊断日志 release gate：release route 会执行基础静态扫描，阻断已开启诊断、临时 sink 和绕过门面的裸日志。
- 打包分发：生成不包含本机运行态和记忆数据库的 release zip。
- 安全边界：不提交 `.codex/memories`、runtime task、`dist`、缓存、数据库或事件日志。

## 对标与路线

本项目按 Harness Engineering 思路实现本地 MVP：把上下文装载、状态机、工具入口、验证回写和任务沉淀放到可审计的本机工程闭环里。

当前已经实现的部分：

- 本地 memory 和 task state。
- context pack 与预算裁剪。
- `codex harness start/checkpoint/complete` 任务生命周期。
- `codex harness verify` 配置化验证回写。
- `codex xhigh review --uncommitted` 作为代码变更的优先最终审核入口；大 diff 或长耗时场景可委托 SubAgent 并行执行该命令并回传结果。
- 项目共享 memory promote、validate 和 index rebuild。
- 写入前敏感信息扫描。
- workspace routing schema 与 `.codex/harness/workspace-routing.json` 模板。
- `codex workspace doctor/scan` 只读识别 Unity、Laya、Cocos、服务器、后台、文档、美术和发布工程。
- `codex workspace route` 根据任务文件、working set、cwd 和 changed paths 生成 route plan；自动扫描到游戏客户端时会补充引擎规则和任务类型规则。
- `codex workspace verify` 根据 route plan 聚合验证，缺失 profile/command 会记录 gap。
- `codex workspace bind/scope-check/summarize` 标准化 SubAgent route binding、scope guard 和 coordinator summary。
- `codex workspace schedule` 标准化 SubAgent dispatch plan，供 Codex 宿主 SubAgent 或人工按角色执行。
- `codex workspace game-client init/template` 为 Unity、LayaBox/LayaAir、Cocos Creator 生成业务项目 verification profile 模板。
- Workspace lifecycle 软集成：`before_task` 写入 route plan/bindings，`after_tool` 按 touched paths 重算路由并执行 scope guard，`before_response` 输出 routing review 和 gap。
- Workspace meta 识别：scanner 能识别仓库根工具工程，router 会避免根项目吞掉已有子项目路径。
- 基础 AI 诊断日志 release gate：release route 会扫描任务 scope 内的常见客户端代码文件，检查诊断开关、临时 sink 和裸日志绕过。
- 安装、更新、诊断、打包和卸载入口。

当前没有实现的部分：

- 不包含宿主级真实 SubAgent 并发执行器；`workspace schedule` 只生成调度计划，不启动子进程或远程 agent。
- 不包含发布级完整验证平台；当前 release gate 是可阻断的基础静态检查和 verification aggregation，不覆盖所有平台构建配置。
- 不依赖向量数据库，也没有 embedding 索引；官方 Codex Memories 作为个人自动记忆层兼容，不替代本项目的工程记忆层。
- 不包含平台化 eval replay 或远程沙箱执行。

这些不是默认宣称已完成的能力。文档中已经明确当前边界和后续路线：

- `docs/EXTERNAL_BENCHMARK.md`
- `docs/OFFICIAL_CODEX_MEMORY_COMPATIBILITY.md`
- `docs/MEMORY_LAYERING.md`
- `docs/MEMORY_RETRIEVAL_STRATEGY.md`
- `docs/SUBAGENT_WORKFLOW.md`
- `docs/FULL_DEVELOPMENT_WORKFLOW.md`
- `docs/AI_DIAGNOSTIC_LOGGING.md`
- `docs/GAME_CLIENT_WORKFLOW.md`
- `docs/WORKSPACE_ADAPTIVE_ROUTING.md`
- `docs/WORKSPACE_ROUTING_TASK_LIST.md`

## 安装与更新

首次安装，在仓库根目录运行：

```powershell
.\install.ps1
```

安装器会做这些事：

- 把 `~/plugins/codex-memory` 指向本仓库的 `plugins/codex-memory`。
- 更新 `~/.agents/plugins/marketplace.json`。
- 更新当前仓库 `.agents/plugins/marketplace.json`。
- 向 `~/.codex/AGENTS.md` 写入 Codex Memory 全局使用规则。
- 向 PowerShell profile 写入 `codex`、`codexm`、`codex-raw`、`codex-memory-doctor` 函数。

如果已经安装的是当前版本，安装器不会重新安装插件，会返回 `already_installed`，只做必要的 profile、marketplace 和规则修复。

如果 `~/plugins/codex-memory` 已经指向其他目录，默认不会覆盖。它会提示已经存在旧安装或其他安装，并建议显式更新：

```powershell
.\install.ps1 -UpdateExisting
```

`-UpdateExisting` 会把旧的 `~/plugins/codex-memory` 迁移到当前包版本。旧目录如果是普通目录，会先备份；如果是 junction 或 symlink，会移除链接后重新指向当前版本。

`-ReplaceExisting` 仍保留为兼容别名，但新文档统一推荐 `-UpdateExisting`。

如果希望同时写入 PowerShell 7 和 Windows PowerShell profile：

```powershell
.\install.ps1 -ProfileShells all
```

如果旧安装也要更新，并且同时写入两个 profile：

```powershell
.\install.ps1 -ProfileShells all -UpdateExisting
```

安装完成后，之后可以通过 Codex 入口检查或修复安装状态：

```powershell
codex memory check-install
codex memory install
codex memory update
```

注意：从很老的版本更新时，旧 wrapper 可能还没有 `codex memory update` 命令。此时应使用当前包里的 `.\install.ps1 -UpdateExisting`。

## 日常使用

正常启动 Codex：

```powershell
codex
```

显式走 memory wrapper：

```powershell
codexm
```

绕过 memory wrapper，直接调用真实 Codex：

```powershell
codex-raw
```

诊断当前项目 memory/harness 状态：

```powershell
codex memory doctor
```

初始化当前项目缺失的 `.codex/memories` 和 `.codex/harness` 配置：

```powershell
codex memory init
```

`codex` 正常启动时也会自动检查并初始化缺失的项目配置；手动执行 `codex memory init` 主要用于排查或提前准备项目。

## 记忆分层

本项目把 memory 分成三层：

| 层级 | 位置 | 是否提交 | 放置内容 |
|---|---|---|---|
| 官方 Codex Memories | `$CODEX_HOME/memories` | 不提交 | 官方自动生成的个人长期记忆 |
| 用户全局层 | `$CODEX_HOME/codex-memory-harness/memories` | 不提交 | 跨项目偏好、通用工作流、长期个人规则 |
| 项目私有层 | `<项目根目录>/.codex/memories` | 不提交 | 本地任务状态、运行事件、summary、distilled 草稿 |
| 项目共享层 | `<项目根目录>/.codex/shared` | 可提交，需审查 | 团队确认的项目事实、决策、流程、路由摘要 |

当前已经实现用户全局层、项目私有层和项目共享层初始化模板。项目共享层只放可审查的 Markdown 和索引，不能直接用 raw `.codex/memories` 代替。官方 Codex Memories 只作为个人自动记忆来源，不作为团队事实来源。

详细规则见：

```text
docs/MEMORY_LAYERING.md
```

## Harness 命令

Harness 用于记录一个任务的生命周期。它不是必须手动使用的日常命令，但适合自动化流程或代理内部调用。

创建任务：

```powershell
codex harness start --task-file task.json
```

记录工具结果或阶段性产物：

```powershell
codex harness checkpoint --task-id <task-id> --result-file result.json
```

完成任务并触发总结沉淀：

```powershell
codex harness complete --task-id <task-id> --summary-file summary.md
```

查看项目配置的验证命令：

```powershell
codex harness verify list
```

运行默认验证 profile：

```powershell
codex harness verify run --profile primary
```

把验证结果绑定到某个 harness 任务：

```powershell
codex harness verify run --task-id <task-id> --profile primary
```

## 维护者命令

生成可分发 zip：

```powershell
codex package build
```

运行项目健康检查、Python 编译、JSON 校验、行为测试和发布包边界检查：

```powershell
codex package verify
```

这些命令底层仍复用仓库里的 Python 脚本，但用户不需要直接调用 `py -X utf8 ...`。

## 发布包

`codex package build` 会生成：

```text
dist/codex-memory-harness-0.1.0.zip
```

发布包会排除：

- 根目录 `.codex/`
- `.codex/memories/`
- `.codex/harness/tasks/`
- `plugins/codex-memory/storage/*.db`
- `plugins/codex-memory/storage/*.jsonl`
- `dist/`
- `__pycache__/`
- `*.pyc`

用户拿到 zip 后解压，在解压后的仓库根目录运行：

```powershell
.\install.ps1
```

已有旧安装则运行：

```powershell
.\install.ps1 -UpdateExisting
```

## 卸载

只移除 marketplace、PowerShell profile 标记块和全局 AGENTS 标记块：

```powershell
.\uninstall.ps1
```

通过 Codex 入口卸载接入：

```powershell
codex memory uninstall
```

同时移除 `~/plugins/codex-memory`：

```powershell
.\uninstall.ps1 -RemoveHomePlugin
```

卸载不会删除任何用户项目里的 `.codex/memories`，也不会删除已经沉淀的项目私有记忆。

## 目录结构

```text
plugins/codex-memory/        核心插件、hooks、MCP、memory、harness、verification 脚本
scripts/build_release.py     打包 zip 的底层实现
scripts/verify_project.py    项目健康检查的底层实现
docs/                        用户指南、隐私说明、系统总结、对标、路由设计和任务计划
templates/                   repo/project 接入模板
install.ps1                  首次安装和更新入口
uninstall.ps1                卸载入口
```

## 维护原则

- 不修改真实 Codex 安装文件，只通过 profile wrapper 接入。
- 默认写项目私有层，只有跨项目偏好或用户明确要求才写用户全局层。
- 不写入密钥、令牌、敏感日志或内部链接。
- AI 诊断日志只能用于开发和调试，发布构建必须关闭，并且不能写入敏感内容。
- 所有写入使用 UTF-8 无 BOM。
- 代码文件保持小模块，单文件硬上限 500 行。
- 打包产物不包含运行态、构建产物、缓存、数据库和事件日志。

更多细节：

- `docs/USER_GUIDE.md`
- `docs/PRIVACY.md`
- `docs/EXTERNAL_BENCHMARK.md`
- `docs/OFFICIAL_CODEX_MEMORY_COMPATIBILITY.md`
- `docs/MEMORY_LAYERING.md`
- `docs/MEMORY_RETRIEVAL_STRATEGY.md`
- `docs/SUBAGENT_WORKFLOW.md`
- `docs/FULL_DEVELOPMENT_WORKFLOW.md`
- `docs/AI_DIAGNOSTIC_LOGGING.md`
- `docs/GAME_CLIENT_WORKFLOW.md`
- `docs/WORKSPACE_ADAPTIVE_ROUTING.md`
- `docs/WORKSPACE_ROUTING_TASK_LIST.md`
- `docs/codex-memory-harness-system-summary.md`
