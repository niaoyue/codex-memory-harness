# Codex Memory Harness

Codex Memory Harness 是一个本地工具包，用来给 Codex 增加可控的外部记忆、任务运行时、验证闭环和任务总结沉淀能力。

它不会修改模型内部记忆，也不会替换真实的 `codex` 可执行文件。推荐主路径是官方 Codex config/hooks/MCP；PowerShell/POSIX shell profile wrapper 作为兼容、诊断和旧环境兜底。

## 它解决什么问题

默认的 Codex 会话之间没有稳定的项目上下文。这个项目把“当前任务是什么、约束是什么、改了哪些文件、验证结果是什么、任务完成后要沉淀什么”保存到本机项目目录里，让后续 Codex 窗口可以继续接上。

核心能力：

- 项目私有记忆：保存任务状态、工作集、最近发现、项目决策和任务总结。
- 官方 Memories 兼容：保留 `$CODEX_HOME/memories` 给 Codex 官方自动记忆，本插件全局层写入 `$CODEX_HOME/codex-memory-harness/memories`。
- 记忆分层：区分用户全局层、项目私有层和项目共享层，避免把 raw 运行态当团队知识提交。
- 自动记忆挖掘规划：从历史事件中自动发现重复用户习惯、项目工作流和纠正模式；低风险高置信偏好自动进入私有记忆，高风险或冲突候选进入待确认队列。
- Review gate 优化：保留候选提交后的 `codex xhigh review --commit <commit-sha>` 最终语义，通过 preflight、diff fingerprint、runner 恢复记录、findings ledger 和 slice planner 降低长耗时与重复失败。
- Session-worktree 绑定规划：写任务开始时为 session 分配明确 checkout；并发写同一项目时自动走隔离 worktree，并通过 lease、heartbeat、stale cleanup 和 scope guard 管理生命周期。
- 共享记忆提升：从本地任务 summary/decision 生成 `.codex/shared` 可审查 Markdown，并可校验和重建索引。
- Workspace memory 自动分层写入：任务完成时根据 route plan `memory_plan` 写入 `.codex/shared` proposed 草稿，区分 workspace route summary 和子项目 facts。
- 官方接入对齐：优先通过 Codex config/hooks/MCP 承载无感接入，PowerShell/POSIX wrapper 作为兼容、诊断和旧环境兜底。
- 启动自检：检查插件、项目 `.codex` 配置、官方 hooks、sandbox/approval 和推荐环境变量。
- Harness 生命周期：用 `start`、`checkpoint`、`complete` 记录任务过程。
- 验证回写：运行项目配置化验证，并把结果写回 harness artifact。
- SubAgent 等待策略：所有 SubAgent 都没有固定总时长；宿主等待 API 的 timeout 只是观察窗口，窗口到期后继续观察，不得仅因窗口到期中断或判失败。
- 代码审核策略：最终 gate 仍以候选提交后的 Codex CLI `codex xhigh review --commit <commit-sha>` 为准；大改动或长耗时审查优先让 XHigh Review Runner SubAgent 作为并行命令执行器运行该 gate，等待策略按 stdout/stderr 进度输出观察，不用固定总时长超时，也不要再套 10 分钟外层总时长；通用 SubAgent reviewer 只做专题辅助审查。
- Skill-first 治理：任务开始先匹配可用技能；需求澄清优先用 `grill-me` 风格补问题清单，接口/API/schema 设计优先用 `design-an-interface` 先比较多个方案。
- Codex specs：Codex 自己生成的需求、设计、任务、PRD、RFC 和执行计划等持久规划文档默认写入 `.codex/specs/<feature-slug>/requirements.md`、`design.md`、`tasks.md`，与 `docs/` 的公开文档和 `.codex/memories` 的运行态记忆分开。
- 未完成 Task 进度汇总：显式请求未完成项时，`before_response` 可返回结构化 `unfinished_task_summary` 和 Markdown，字段包含状态、最近 checkpoint 或更新时间、已完成/剩余验收、阻塞点、下一步和证据来源。
- 写入前敏感扫描：memory、harness artifact 和 distillation 写入前先脱敏，高危私钥块阻断。
- AI 诊断日志策略：编码和 AI 调试期允许临时观测，发布和生产构建必须关闭。
- Workspace routing schema：提供 project inventory、显式配置、route plan、SubAgent binding 和 verification aggregation 的结构化契约。
- Workspace 只读路由：`codex workspace doctor/scan/route` 输出子项目 inventory 和 route plan，不修改业务项目文件。
- 需求质量门：route plan 会区分 bugfix、小优化、功能 story、系统改动和发布 gate；高风险需求缺来源、验收或回滚材料时要求澄清。
- Workspace 验证聚合：`codex workspace verify` 按 route plan 聚合多项目 verification profile 和 gap。
- SubAgent 绑定与守卫：`codex workspace bind/scope-check/summarize` 生成 route binding、检查越权路径并汇总冲突。
- SubAgent 调度计划：`codex workspace schedule` 根据 route plan 生成 specialist/coordinator dispatch plan，并可写入 checkpoint。
- 项目级 custom agents 模板：`codex memory init` 创建 `.codex/agents` 下的 Workspace Coordinator、Implementation Specialist、Route Review Specialist 和 XHigh Review Runner 模板，不默认写用户全局。
- 游戏客户端模板：`codex workspace game-client init/template` 为 Unity、LayaBox/LayaAir、Cocos Creator 生成 verification profile 模板。
- 业务项目模板：`codex workspace project-template init/template` 为服务器、后台/Web、文档和美术工程生成 workspace routing 与 verification profile 模板。
- AI 诊断日志 release gate：release route 会执行基础静态扫描，阻断已开启诊断、临时 sink 和绕过门面的裸日志。
- Bundled Codex skills：安装包按 `bundled-skills.json` 内置所有可用治理技能，默认离线安装到 `~/.agents/skills`。
- 打包分发：生成不包含本机运行态和记忆数据库的 release zip。
- 安全边界：不提交 `.codex/memories`、runtime task、`dist`、缓存、数据库或事件日志。

## 对标与路线

本项目按 Harness Engineering 思路实现本地 MVP：把上下文装载、状态机、工具入口、验证回写和任务沉淀放到可审计的本机工程闭环里。

当前已经实现的部分：

- 本地 memory 和 task state。
- context pack 与预算裁剪。
- `codex harness start/checkpoint/complete` 任务生命周期。
- `codex harness verify` 配置化验证回写。
- `codex xhigh review --commit <commit-sha>` 作为代码变更的优先最终审核入口；大 diff 或长耗时场景优先委托 XHigh Review Runner SubAgent 并行执行该命令并回传结果，只有 stdout/stderr 长时间无输出才判 idle timeout。
- `codex review preflight/status/plan/record/findings/ledger` 作为最终 xhigh review 前后的辅助 runtime，记录 diff fingerprint、确定性 preflight、review ledger、infra failure 恢复策略和 reviewable slices。
- 项目共享 memory promote、validate 和 index rebuild。
- workspace memory 自动分层写入 proposed shared drafts。
- memory retention：按 `task_id` dry-run/confirm 归档和清理项目 memory DB/history。
- eval replay：把失败或高价值 artifact 转为 `.codex/evals`，执行 deterministic no-network checks。
- 自动历史记忆挖掘 runtime：记录脱敏事件、生成候选、治理候选并把 accepted preferences 注入 context pack。
- 可选本地语义检索 provider：显式启用 `local/auto` 时用 deterministic token/TF-IDF/Jaccard provider 扩展检索，默认禁用并可降级。
- 写入前敏感信息扫描。
- workspace routing schema 与 `.codex/harness/workspace-routing.json` 模板。
- `codex workspace doctor/scan` 只读识别 Unity、Laya、Cocos、服务器、后台、文档、美术和发布工程。
- `codex workspace route` 根据任务文件、working set、cwd 和 changed paths 生成 route plan；自动扫描到游戏客户端时会补充引擎规则和任务类型规则。
- `requirements_gate` 会随 route plan 输出任务意图、需求来源、缺失项和待澄清问题；需求不清时使用 `ask_user`，技术选择则先遵守既有项目约定。
- `codex workspace verify` 根据 route plan 聚合验证，缺失 profile/command 会记录 gap。
- `codex workspace bind/scope-check/summarize` 标准化 SubAgent route binding、scope guard 和 coordinator summary。
- `subagent_receipts.py` 支持宿主 SubAgent 执行回执导入和 integration readiness report；它不自行启动 SubAgent。
- `codex workspace schedule` 标准化 SubAgent dispatch plan，包含 `host_spawn_requests`，供主 Agent 在用户显式选择、项目持久化 `subagent_runtime_policy` 授权、通用 planner 判定功能/系统/发布/复杂任务需要派发，或 xhigh review gate 需要并行执行时调用 Codex 宿主 SubAgent；普通低风险小修仍可保持主 Agent 串行。
- `codex workspace game-client init/template` 为 Unity、LayaBox/LayaAir、Cocos Creator 生成业务项目 verification profile 模板。
- `codex workspace project-template init/template` 为服务器、后台/Web、文档和美术工程生成业务项目 verification profile 与 route project 模板。
- Workspace lifecycle 软集成：`before_task` 写入 route plan/bindings 和 `subagent_runtime` 决策，`after_tool` 按 touched paths 重算路由、记录 SubAgent-style artifact 并执行 scope guard，`before_response` 输出 routing review、gap 和未启动原因。
- Workspace meta 识别：scanner 能识别仓库根工具工程，router 会避免根项目吞掉已有子项目路径。
- 基础 AI 诊断日志 release gate：release route 会扫描任务 scope 内的常见客户端代码文件，检查诊断开关、临时 sink 和裸日志绕过。
- Release manifest gate：`release_profile_gate.py --manifest-file` 对渠道/平台/产物/回滚/evidence manifest 做本地阻断检查，不执行平台构建。
- Requirements conflict scanner：`requirements_conflict_scanner.py` 扫描任务字段和 OpenSpec change 中显式冲突标记，输出 `blocked_by_conflict` requirements gate。
- 安装、更新、诊断、打包和卸载入口。

当前没有实现的部分：

- 不包含仓库内建的 SubAgent 并发执行器；`workspace schedule` 只生成调度计划和宿主调用请求，不自行启动子进程或远程 agent。用户明确选择 SubAgent、任务属于复杂/应用级/多阶段实现，且宿主提供能力时，由主 Agent 消费 `subagent_dispatch_plan.host_spawn_requests` 调用宿主 SubAgent。
- 不包含发布级完整验证平台；当前 release gate 是可阻断的基础静态检查和 verification aggregation，不覆盖所有平台构建配置。
- 不包含完整的宿主级 session-worktree 自动绑定 runtime；当前已有最小 `codex workspace write-guard`、binding registry 和 worktree allocator，能在 dirty primary checkout 或已有 active write lease 时返回 managed worktree 的 `effective_cwd`。后续仍需接入真正的 `before_first_write` 强制拦截、stale cleanup 和多 session 协作。
- 不依赖向量数据库，也没有远程 embedding 索引；可选本地 semantic provider 是轻量 token/TF-IDF/Jaccard 检索。官方 Codex Memories 作为个人自动记忆层兼容，不替代本项目的工程记忆层。
- 不包含远程沙箱执行；eval replay 当前只做本地 deterministic no-network checks。

这些不是默认宣称已完成的能力。文档中已经明确当前边界和后续路线：

- `docs/LLM_AGENT_MEMORY_HANDBOOK.md`
- `docs/EXTERNAL_BENCHMARK.md`
- `docs/CODEX_OFFICIAL_ALIGNMENT.md`
- `docs/OFFICIAL_CODEX_MEMORY_COMPATIBILITY.md`
- `docs/MEMORY_LAYERING.md`
- `docs/MEMORY_RETRIEVAL_STRATEGY.md`
- `docs/AUTOMATED_MEMORY_MINING.md`
- `docs/REVIEW_GATE_OPTIMIZATION.md`
- `docs/SKILL_ROUTING_AND_DEFAULT_GOVERNANCE.md`
- `docs/SESSION_WORKTREE_BINDING.md`
- `docs/SUBAGENT_WORKFLOW.md`
- `docs/FULL_DEVELOPMENT_WORKFLOW.md`
- `docs/AI_DIAGNOSTIC_LOGGING.md`
- `docs/GAME_REQUIREMENTS_GATE.md`
- `docs/GAME_CLIENT_WORKFLOW.md`
- `docs/WORKSPACE_ADAPTIVE_ROUTING.md`
- `docs/WORKSPACE_ROUTING_TASK_LIST.md`

## 安装与更新

首次安装，在仓库根目录运行：

```bat
install.bat
```

PowerShell 中运行 batch 文件时使用：

```powershell
.\install.bat
```

在 Linux/macOS shell，或 Git Bash、MSYS、Cygwin 等 POSIX shell 环境中：

```sh
sh ./install.sh
```

安装器会做这些事：

- 先检查 Python 3.11+ 是否可用；缺少 Python、版本过低或未加入 PATH 时，会提示安装命令和重试方式。
- 如果希望脚本代为尝试安装 Python，可显式运行 `install.bat --install-python` 或 `sh ./install.sh --install-python`。Windows 会使用 `winget`；POSIX shell 会按可用包管理器尝试 Homebrew、apt、dnf、yum 或 pacman。默认不会静默安装系统环境。
- `install.sh` 会在 Linux/macOS 默认写入 POSIX hook/MCP launcher，并向 `~/.profile`、`~/.bashrc`、`~/.zshrc` 写入带标记块的 `codex`/`codexm` shell wrapper；在 Windows POSIX shell 中如检测到 `powershell`，默认仍写入 PowerShell launcher。可用 `CODEX_MEMORY_LAUNCHER_FAMILY=posix|powershell` 显式指定。
- 修复必要的官方 Codex 配置：确保 `$CODEX_HOME/config.toml` 中启用 `[features] hooks = true`。
- 安装 bundled Codex skills 到 `~/.agents/skills/<skill-name>`：安装器读取 `plugins/codex-memory/skills/bundled-skills.json`，当前包含 security、GitHub、CLI、迁移、release gate、需求澄清、接口设计、TDD、提交、review、PRD、重构、文档、图像、OpenAI docs 等可用技能。技能已随包 vendor，安装时不联网下载；安装计划按技能名去重，如果目标技能目录已存在，会保留用户已有版本并跳过，不要求覆盖或更新。
- 把 `~/plugins/codex-memory` 指向本仓库的 `plugins/codex-memory`。
- 更新 `~/.agents/plugins/marketplace.json`。
- 更新当前仓库 `.agents/plugins/marketplace.json`。
- 向 `~/.codex/AGENTS.md` 写入 Codex Memory 全局使用规则。
- 向 shell profile 写入 `codex`、`codexm`、`codex-raw`、`codex-memory-doctor` 入口：PowerShell 使用函数，Linux/macOS POSIX shell 使用随包 `codexm.sh` 分流器。

如果已经安装的是当前版本，安装器不会重新安装插件，会返回 `already_installed`，只做必要的 profile、marketplace 和规则修复。

如果 `~/plugins/codex-memory` 已经指向其他目录，默认不会覆盖。它会提示已经存在旧安装或其他安装，并建议显式更新：

```bat
install.bat --update-existing
```

POSIX shell：

```sh
sh ./install.sh --update-existing
```

`--update-existing` 会把旧的 `~/plugins/codex-memory` 迁移到当前包版本。旧目录如果是普通目录，会先备份；如果是 junction 或 symlink，会移除链接后重新指向当前版本。

`--replace-existing` 仍保留为兼容别名。`install.bat` 和 `install.sh` 也兼容旧的 PowerShell 风格参数，例如 `-UpdateExisting`、`-ReplaceExisting`、`-ProfileShells all`。

如果希望同时写入 PowerShell 7 和 Windows PowerShell profile：

```bat
install.bat --profile-shells all
```

如果旧安装也要更新，并且同时写入两个 profile：

```bat
install.bat --profile-shells all --update-existing
```

如果只想安装插件接入、不写入 bundled skills：

```bat
install.bat --skip-skills
```

POSIX shell：

```sh
sh ./install.sh --skip-skills
```

安装前如需只读预览会写入哪些 profile、全局 AGENTS、marketplace、bundled skills 和 Codex config：

```bat
install.bat --dry-run
```

PowerShell 兼容入口：

```powershell
.\install.ps1 -DryRun
```

安装完成后，之后可以通过 Codex 入口检查或修复安装状态：

```powershell
codex memory check-install
codex memory install
codex memory update
```

注意：从很老的版本更新时，旧 wrapper 可能还没有 `codex memory update` 命令。此时应使用当前包里的 `install.bat --update-existing`、PowerShell 里的 `.\install.bat --update-existing`，或 `sh ./install.sh --update-existing`。`.\install.ps1 -UpdateExisting` 仍可作为兼容入口使用。

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

诊断当前项目 memory/harness 和官方 Codex 配置对齐状态：

```powershell
codex memory doctor
```

初始化当前项目缺失的 `.codex/memories` 和 `.codex/harness` 配置：

```powershell
codex memory init
```

`codex` 正常启动时也会自动检查并初始化缺失的项目配置；手动执行 `codex memory init` 主要用于排查或提前准备项目。

官方 hooks 可用时，插件会通过 `UserPromptSubmit`、`PostToolUse` 和 `Stop` 桥接任务上下文、工具摘要和回复前上下文整理，并在打开项目记忆前应用 hook payload 的 `cwd`。shell wrapper 仍保留为兼容入口；不经过 wrapper 的 Codex 客户端应依赖官方 config/hooks/MCP 接入。

## 记忆分层

本项目把 memory 分成三层：

| 层级 | 位置 | 是否提交 | 放置内容 |
|---|---|---|---|
| 官方 Codex Memories | `$CODEX_HOME/memories` | 不提交 | 官方自动生成的个人长期记忆 |
| 用户全局层 | `$CODEX_HOME/codex-memory-harness/memories` | 不提交 | 跨项目偏好、通用工作流、长期个人规则 |
| 项目私有层 | `<项目根目录>/.codex/memories` | 不提交 | 本地任务状态、运行事件、summary、distilled 草稿 |
| 项目规格层 | `<项目根目录>/.codex/specs` | 可提交 | Codex 生成的需求、设计、任务、PRD、RFC 和执行计划三件套 |
| 项目共享层 | `<项目根目录>/.codex/shared` | 可提交，需审查 | 团队确认的项目事实、决策、流程、路由摘要 |

当前已经实现用户全局层、项目私有层和项目共享层初始化模板；项目规格层作为可提交目录约定，用于放 Kiro-like `requirements.md`、`design.md`、`tasks.md` 三件套。项目共享层只放可审查的 Markdown 和索引，不能直接用 raw `.codex/memories` 代替。官方 Codex Memories 只作为个人自动记忆来源，不作为团队事实来源。

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

运行项目健康检查、Python 编译、JSON 校验、行为测试、发布包边界检查，以及隔离的 `install.bat` 普通安装 smoke test：

```powershell
codex package verify
```

这些命令底层仍复用仓库里的 Python 脚本，但用户不需要直接调用 `py -X utf8 ...`。

## 发布包

`codex package build` 会生成：

```text
dist/codex-memory-harness-0.1.1.zip
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

`.codex/specs` 是源码仓库内可提交的治理规格目录；当前 release zip 仍排除根目录 `.codex/`，避免把项目治理材料和本机运行态一起分发到用户安装包。

发布包会包含 `plugins/codex-memory/skills/openai-curated/`、`plugins/codex-memory/skills/local/` 和 `plugins/codex-memory/skills/bundled-skills.json`，用于目标机器离线安装 `~/.agents/skills`。

用户拿到 zip 后解压，在解压后的仓库根目录运行：

```bat
install.bat
```

POSIX shell：

```sh
sh ./install.sh
```

`install.sh` 不要求目标环境存在 `powershell` 命令；Linux/macOS 默认使用随包提供的 POSIX hook/MCP launcher 和 `codexm.sh` profile wrapper。Windows POSIX shell 如需沿用 PowerShell launcher，可设置 `CODEX_MEMORY_LAUNCHER_FAMILY=powershell`。

已有旧安装则运行：

```bat
install.bat --update-existing
```

POSIX shell：

```sh
sh ./install.sh --update-existing
```

## 卸载

只移除 marketplace、PowerShell/POSIX shell profile 标记块和全局 AGENTS 标记块：

```bat
install.bat --uninstall
```

POSIX shell：

```sh
sh ./install.sh --uninstall
```

通过 Codex 入口卸载接入：

```powershell
codex memory uninstall
```

同时移除 `~/plugins/codex-memory`：

```bat
install.bat --uninstall --remove-home-plugin
```

POSIX shell：

```sh
sh ./install.sh --uninstall --remove-home-plugin
```

卸载不会删除任何用户项目里的 `.codex/memories`，也不会删除已经沉淀的项目私有记忆。
卸载也不会默认删除 `~/.agents/skills` 中已经存在的技能，避免误删用户自己安装或修改过的技能目录。

## 目录结构

```text
plugins/codex-memory/        核心插件、hooks、MCP、memory、harness、verification 脚本
.codex/specs/                Codex 自生成需求、设计、任务、PRD、RFC 和执行计划的可提交规格目录
scripts/build_release.py     打包 zip 的底层实现
scripts/verify_project.py    项目健康检查的底层实现
docs/                        LLM/Agent 普及手册、用户指南、隐私说明、系统总结、对标、路由设计和任务计划
templates/                   repo/project 接入模板
install.bat                  Windows CMD 首次安装、更新和卸载入口
install.sh                   POSIX shell 首次安装、更新和卸载入口
install.ps1                  PowerShell 兼容安装入口
uninstall.ps1                PowerShell 兼容卸载入口
```

## 维护原则

- 不修改真实 Codex 安装文件；优先使用官方 config/hooks/MCP，profile wrapper 只作为兼容和诊断入口。
- 安装写入边界包括 `~/plugins/codex-memory`、`~/.agents/plugins/marketplace.json`、`$CODEX_HOME/config.toml`、`~/.codex/AGENTS.md`、PowerShell/POSIX shell profile 和 `~/.agents/skills/<skill-name>`。
- 默认写项目私有层，只有跨项目偏好或用户明确要求才写用户全局层。
- 不写入密钥、令牌、敏感日志或内部链接。
- AI 诊断日志只能用于开发和调试，发布构建必须关闭，并且不能写入敏感内容。
- 所有写入使用 UTF-8 无 BOM。
- 代码文件保持小模块，单文件硬上限 500 行。
- 打包产物不包含运行态、构建产物、缓存、数据库和事件日志。

更多细节：

- `docs/LLM_AGENT_MEMORY_HANDBOOK.md`
- `docs/USER_GUIDE.md`
- `docs/PRIVACY.md`
- `docs/EXTERNAL_BENCHMARK.md`
- `docs/CODEX_OFFICIAL_ALIGNMENT.md`
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
