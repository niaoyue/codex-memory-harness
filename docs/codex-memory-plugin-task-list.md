# Codex 外脑插件任务清单

## 1. 使用说明

本清单用于驱动逐步实施，状态定义如下：

- `todo`：未开始
- `doing`：进行中
- `done`：已完成
- `blocked`：受阻

当前实现策略：一次只推进一个主里程碑，避免并行改动过多导致上下文污染。workspace routing 已能生成 SubAgent dispatch plan，允许 coordinator 按计划分配多个 specialist；但当前项目尚未实现宿主级真实 SubAgent 自动执行器。

新增需求：当输出“未完成 Task 汇总”时，不能只列出未完成 Task ID 和状态；必须为每个未完成 Task 附带可追溯的进度摘要，包括当前状态、最近 checkpoint 或更新时间、已完成/未完成验收项、阻塞点、下一步和可用证据来源。缺少证据时明确标为未知，不得凭空估算进度。

## 2. 主任务清单

| ID | 阶段 | 任务 | 产出物 | 依赖 | 状态 |
|---|---|---|---|---|---|
| T00 | 0 | 创建插件目录骨架 | `plugins/codex-memory/` 目录结构 | 无 | done |
| T01 | 0 | 创建 `.codex-plugin/plugin.json` 占位清单 | 插件入口清单 | T00 | done |
| T02 | 0 | 创建 `mcp/` 最小服务入口 | `memory_server.py` 骨架 | T00 | done |
| T03 | 0 | 创建 `storage/` 与初始化脚本 | 本地存储骨架 | T00 | done |
| T04 | 1 | 定义任务状态模型 | 状态 schema 文档或代码 | T02,T03 | done |
| T05 | 1 | 实现任务状态读写 | `task state` 读写接口 | T04 | done |
| T06 | 1 | 实现项目决策读写 | `repo decisions` 读写接口 | T04 | done |
| T07 | 1 | 实现任务结束总结回写 | `summary` 生成与持久化 | T05,T06 | done |
| T08 | 2 | 实现精确检索 | 文件名/符号/关键词检索 | T02,T03 | done |
| T09 | 2 | 实现全文检索 | FTS 检索与证据包输出 | T08 | done |
| T10 | 2 | 预留语义检索接口 | embedding 检索占位接口 | T09 | done |
| T11 | 3 | 实现 context pack 构建 | 统一上下文装配逻辑 | T05,T07,T09 | done |
| T12 | 3 | 实现注入预算控制 | 上下文裁剪与分层策略 | T11 | done |
| T13 | 4 | 实现任务蒸馏输出 | 模式归档与技能草稿占位 | T07,T11 | done |
| T14 | 4 | 写回蒸馏资产索引 | `distilled/` 与结构化记录 | T13 | done |
| T15 | 5 | 实现 hooks 自动触发 | 自动读取、更新、回写 | T05,T11,T13 | done |
| T16 | 5 | 增加失败降级与容错 | 无记忆模式回退能力 | T15 | done |
| T17 | 5 | 补充验证脚本与示例流程 | 本地验收脚本或文档 | T16 | done |
| T18 | 6 | 对齐 Codex 插件市场接入 | repo/home marketplace 与本机插件入口 | T15 | done |
| T19 | 6 | 对齐官方 hooks 入口格式 | `hooks.json` 与 `hook_bridge.py` | T15 | done |
| T20 | 6 | 落地无感使用默认工作流 | 安装脚本、仓库 AGENTS 与自动兜底 | T18,T19 | done |
| T21 | 7 | 实现用户全局层/项目私有层隔离 | 用户全局 `$CODEX_HOME/codex-memory-harness/memories` 与项目私有 `.codex/memories` | T20 | done |
| T22 | 8 | 实现最小 Harness Controller | start/checkpoint/complete 三段式控制器 | T21 | done |
| T23 | 8 | 增加项目 harness 配置 | `.codex/harness` 配置与命令注册 | T22 | done |
| T24 | 9 | 增加 Harness Verification Runner | 配置化验证执行、危险命令拦截、checkpoint 回写 | T23 | done |
| T25 | 10 | 增加全局 Bootstrap / Doctor | 窗口启动自检、项目初始化、状态诊断 JSON | T24 | done |
| T26 | 11 | 增加 PowerShell codexm 启动器 | 全局 profile 函数、doctor/init 后启动真实 Codex | T25 | done |
| T27 | 12 | 增加 PowerShell codex 包装函数 | profile 级 codex wrapper、codex-raw 回退、禁用开关 | T26 | done |
| T28 | 13 | 补齐 Harness Engineering 外部对标文档 | `docs/EXTERNAL_BENCHMARK.md` | T27 | done |
| T29 | 13 | 补齐记忆检索与向量库策略 | `docs/MEMORY_RETRIEVAL_STRATEGY.md` | T28 | done |
| T30 | 13 | 补齐 SubAgent 角色分工协议 | `docs/SUBAGENT_WORKFLOW.md` | T28 | done |
| T31 | 14 | 实现写入前敏感信息扫描器 | memory/artifact/index 写入前脱敏与拒绝策略 | T28,T29,T30 | done |
| T32 | 14 | 实现 SubAgent artifact schema | roles、subagents artifact、冲突检测和汇总规则 | T30 | done |
| T33 | 14 | 实现可选语义检索 provider | `semantic_retrieval.py` 已提供本地 deterministic token/TF-IDF/Jaccard provider，`RetrievalEngine` 默认 disabled，显式 `local/auto` 时启用并支持降级 | T29,T31 | done |
| T34 | 15 | 补齐游戏客户端专项工作流文档 | `docs/GAME_CLIENT_WORKFLOW.md` | T28,T30 | done |
| T35 | 15 | 评估 `codex game-client` 独立命令 | 结论：不新增顶层入口，改用 `codex workspace game-client init/template` 生成 Unity/Laya/Cocos profile | T34 | done |
| T36 | 16 | 补齐 Workspace 自适应路由设计 | `docs/WORKSPACE_ADAPTIVE_ROUTING.md` | T30,T34 | done |
| T37 | 16 | 实现 workspace scanner | project inventory、子项目识别、置信度和信号输出 | T36 | done |
| T38 | 16 | 实现 route plan schema | task route、subagent route binding、verification aggregation | T36 | done |
| T39 | 17 | 审查并修正 Workspace 路由文档设计 | 文档一致性修正、runtime 差距说明、memory/cwd 策略 | T36 | done |
| T40 | 17 | 拆分 Workspace 路由实现任务 | `docs/WORKSPACE_ROUTING_TASK_LIST.md` | T39 | done |
| T44 | 17 | 同步 workspace 隐私与检索设计边界 | `docs/PRIVACY.md`、`docs/MEMORY_RETRIEVAL_STRATEGY.md` | T39 | done |
| T45 | 17 | 修复 working set glob 触发检索降级 | fulltext 检索按 literal 处理 `*.md` 等模式 | T39 | done |
| T41 | 18 | 实现 verification command cwd | 支持每个子项目独立 cwd/profile 聚合执行 | T38 | done |
| T42 | 18 | 实现 SubAgent scope guard | 检测 SubAgent touched paths 是否越过 assigned scope | T38 | done |
| T43 | 18 | 实现 workspace memory 分层 | workspace summary 与子项目 facts 分层写入 | T38 | done |
| T46 | 17 | 设计项目共享 memory 层 | `.codex/shared` 分层说明、冲突策略、提升流程文档 | T44 | done |
| T47 | 19 | 实现项目共享 memory 模板 | `.codex/shared` 目录模板、schema、示例和 `.gitignore` 精细放行 | T46 | done |
| T48 | 19 | 实现 memory promote 命令 | 从本地 summary/decision 提升为共享 Markdown，执行脱敏和校验 | T46,T31 | done |
| T49 | 17 | 设计 AI 诊断日志策略 | `docs/AI_DIAGNOSTIC_LOGGING.md`、README、用户指南、游戏客户端和 workspace 文档入口 | T39,T34 | done |
| T50 | 18 | 实现 AI 诊断日志 release gate | release route 基础扫描诊断开关、调试宏、临时 sink 和裸日志绕过 | T49,T24,T31 | done |
| T51 | 17 | 落地完整开发流程图 | `docs/FULL_DEVELOPMENT_WORKFLOW.md`、README、用户指南、系统总结和 workspace 入口 | T36,T39,T49 | done |
| T52 | 18 | 实现 workspace lifecycle 软集成 | hook lifecycle 写入 route plan/bindings、scope guard 和 routing review | T37,T41,T42 | done |
| T53 | 18 | 实现 SubAgent dispatch plan | `subagent_scheduler.py` 与 `codex workspace schedule` | T42,T52 | done |
| T54 | 18 | 实现游戏客户端 profile 模板生成器 | `game_client_profiles.py` 与 `codex workspace game-client init/template` | T34,T52 | done |
| T55 | 19 | 实现发布级完整验证平台 | 已有 release profile/evidence gate 与 `release_profile_gate.py --manifest-file` manifest gate；完整渠道包、热更、平台构建和回滚材料 gate 依赖业务项目与 CI 材料，继续拆分推进 | T50,T54 | doing |
| T56 | 19 | 补服务器/后台/文档/美术业务模板 | `workspace_business_templates.py` 与 `codex workspace project-template init/template` | T54,WR-26,WR-27,WR-28 | done |
| T57 | 19 | 补 workspace routing 发布与迁移说明 | `docs/WORKSPACE_ROUTING_MIGRATION.md` 说明普通 harness 到 workspace routing 的升级说明和兼容边界 | T52,WR-30 | done |
| T58 | 20 | 实现 workspace memory 自动分层写入 | 根据 `memory_plan` 写入 workspace summary 与子项目 fact | T43,WR-34 | done |
| T59 | 20 | 实现真实 SubAgent 自动执行器 | 当前已生成 `host_spawn_requests` 与调度计划，`subagent_receipts.py` 已支持宿主执行回执/status 汇总；真实启动/观察 SubAgent 仍依赖宿主 API | T53 | blocked |
| T60 | 20 | 补本仓库 dogfood workspace routing 配置 | 当前仓库根 `.codex/harness/workspace-routing.json` 与源码布局对齐 | WR-33 | done |
| T61 | 20 | 实现安装器 dry-run | 安装前输出将写入的 profile、AGENTS、marketplace、skills 和 Codex config 变更 | T20 | done |
| T62 | 20 | 实现旧全局 memory marker 迁移工具 | `migrate-legacy-global --dry-run/--confirm`，含 manifest、checksum 和回滚说明 | T21 | done |
| T63 | 20 | 提供 custom agents 模板 | `.codex/agents` 模板对齐 dispatch plan，不默认写入用户全局 | T53 | done |
| T64 | 20 | 平台化 eval replay | `eval_replay.py` 已支持 create/list/run，将失败或高价值 artifact 转为 `.codex/evals/*.json`，run 只做 deterministic no-network safety checks | T24,T55 | done |
| T65 | 20 | 实现 memory archive/cleanup 与 retention policy | `memory_retention.py` 已支持 status、dry-run cleanup、confirm archive/cleanup，按 `task_id` 精确处理 DB 行和 history JSONL | T31,T58 | done |
| T66 | 21 | 设计自动历史记忆挖掘方案 | `docs/AUTOMATED_MEMORY_MINING.md`，明确事件账本、候选、自动提升和人工确认边界 | T15,T31,T48 | done |
| T67 | 21 | 实现历史事件账本 | `memory_store.py` 已将任务事件追加到 history ledger，失败静默降级 | T66,T31 | done |
| T68 | 21 | 实现记忆候选挖掘器 | `memory_mining.py` 已从历史事件生成 workflow/command/correction 候选 | T67 | done |
| T69 | 21 | 实现自动提升策略 | `memory_mining.py` 已支持 candidate accept/reject/deprecate 与 accepted context 查询 | T68,T31 | done |
| T70 | 21 | 将 accepted 私有记忆注入 context pack | `context_builder.py` 已按 project/scope/intent/working_set 注入 Learned Preferences，并受预算控制 | T69,T11 | done |
| T71 | 21 | 增加自动挖掘治理命令 | `codexm.ps1` 已暴露 `codex memory mine status|run`、`codex memory candidates list|accept|reject|deprecate`，清理接入 retention | T69,T65 | done |
| T72 | 22 | 设计 review gate 优化方案 | `docs/REVIEW_GATE_OPTIMIZATION.md`，明确 preflight、diff fingerprint、ledger、runner 恢复和 slice planner | T53,T24 | done |
| T73 | 22 | 实现 review preflight | `codex review preflight --uncommitted`，运行 diff check、配置化验证摘要、敏感扫描和打包边界检查 | T72,T24,T31 | done |
| T74 | 22 | 实现 diff fingerprint 与 review ledger | 将 review 结果绑定到 diff fingerprint，diff 变化时旧 review 自动 invalidated | T72 | done |
| T75 | 22 | 实现 review runner 状态与恢复记录 | 记录 XHigh Review Runner active/resumed/restarted/infra_failed，不把 429/5xx/timeout 当通过 | T72,T53 | done |
| T76 | 22 | 实现 findings loop | 结构化记录 findings、resolve/reopen、修复后强制重跑最终 gate | T74,T75 | done |
| T77 | 22 | 实现 review slice planner | 按路径、风险、删除/生成文件和验证边界输出 reviewable slices | T74 | done |
| T78 | 23 | 设计 session-worktree 绑定方案 | `docs/SESSION_WORKTREE_BINDING.md`，明确 lease、heartbeat、stale、cleanup、多 session 同 task | T52,T53 | done |
| T79 | 23 | 实现 binding registry | 用户私有 registry、project_key、session_id、task_id、binding_id、file lock 和 heartbeat | T78 | done |
| T80 | 23 | 实现 worktree allocator | 单 session 绑定 primary checkout，并发写同项目时创建 managed worktree 和 session branch | T79 | done |
| T81 | 23 | 集成 session binding lifecycle | 最小 `write-guard` 已落地；完整 before_task/before_first_write/after_tool/before_response/on_task_complete 强制接入仍需后续 hook/宿主支持 | T80,T52 | doing |
| T82 | 23 | 实现 stale 与 cleanup 治理 | `worktree list` 已展示 stale/dirty orphan/prunable/pruned，`worktree prune --dry-run` 已输出候选，`worktree prune --confirm` 已重新校验并清理 clean managed worktree，`worktree recover <binding-id>` 已能恢复 clean at base 的 managed stale/prunable binding 并阻断 dirty/pruned/非 managed 场景 | T81,T65 | done |
| T83 | 23 | 支持多 session 同 task 协作 | 已具备 binding、scope guard、coordinator summary 和 `subagent_receipts.py` integration readiness report；自动合并 specialist branches 与 integration worktree final gate 依赖 T59/T81 强制接入 | T81,T53,T74 | blocked |
| T84 | 24 | 引入 OpenSpec change contract 与需求完整性门禁 | `openspec/` profile、`change-governance` spec、OpenSpec/BMAD 集成 proposal/design/tasks/spec delta；本切片仅落地文档，不实现 runtime | T24,T76,T81 | done |
| T85 | 24 | 定义 BMAD upstream planning policy | 明确何时进入 Product Brief/PRFAQ/PRD/Architecture/Epic/Story/Readiness，何时直接进入 OpenSpec change contract | T84 | done |
| T86 | 24 | 调研并适配 OpenSpec/BMAD 上游核心代码复用 | 已核对 license、版本、entrypoint、依赖、telemetry、storage 和安全边界；决策为先做命令/插件 adapter，vendoring 仅在 adapter 不足时按 pinned source + LICENSE/NOTICE 执行，不重写上游 core | T84,T85 | done |
| T87 | 24 | 实现严格 Requirements Integrity Gate runtime | 已完成最小 runtime、blocking write enforcement、governance adapter、误判修复与 `requirements_conflict_scanner.py` 显式 spec/implementation conflict 静态扫描；真实 BMAD upstream 执行仍需外部工具或用户规划材料 | T84,T86 | doing |
| T88 | 25 | 落地 skill-first 治理文档 | `docs/SKILL_ROUTING_AND_DEFAULT_GOVERNANCE.md`，列出可用技能、触发场景、需求/技术/测试/review/SubAgent 默认规则 | T84,T87 | done |
| T89 | 25 | 扩展 bundled skills 清单 | `bundled-skills.json` 已改为 manifest-driven 全量可用技能清单，安装验证按 manifest 期望数量计算；安装仍不覆盖用户已有技能目录 | T20,T88,T31 | done |
| T90 | 25 | 实现 skill routing audit runtime | `skill_routing_audit.py` 已接入 hook before_task/after_tool/before_response，输出 matched/used/skipped、原因、checkpoint signal 和最终 brief | T88,T52 | done |
| T91 | 25 | 扩展 Requirements Gate 默认治理字段 | Requirements Gate schema 已纳入策划问题、技术选择依据、测试计划缺口、性能/包体/WebGL/小游戏/资源 AB 约束字段 | T24,T85,T87,T88 | done |
| T92 | 25 | 强化多任务 SubAgent 卡点分析 | `subagent_blocker_plan.py` 已在 dispatch plan 前输出依赖/决策/环境/接口/验证卡点、scope matrix，并阻断非 disjoint 并行派发；真正跨 session 合并仍由 T59/T83 后续能力扩展 | T53,T81,T88 | done |
| T93 | 25 | 扩展发布级验证到小游戏与资源依赖 | release profile gate 原型已覆盖本地化、平台矩阵、WebGL/小游戏、AB 依赖、包体、性能和诊断日志关闭的证据聚合 | T55,T88 | done |
| T94 | 25 | 治理文档一致性清理 | README、系统总结、skill-first 文档、OpenSpec tasks 与任务清单已同步 manifest skills、commit-based review、workspace memory 分层和治理 adapter 现状 | T58,T72,T84,T88 | done |
| T95 | 25 | 实现 OpenSpec command/artifact adapter 原型 | `governance_adapter.py` 已连接 OpenSpec change contract、harness task、verification artifact、effective cwd 与证据 bundle，不复制第三方 core | T86,T87,T81 | done |
| T96 | 25 | 实现 BMAD upstream planning adapter 原型 | `governance_adapter.py` 已支持 BMAD planning artifact 作为 upstream evidence，不声称本项目已有 BMAD 多 agent runtime | T85,T86,T95 | done |
| T97 | 25 | 连接最终验证/review 证据到 spec sync/archive | `governance_adapter.py` 已把 verification、release gate、commit-based xhigh review ledger 与 sync/archive readiness 串成可审计 evidence bundle | T72,T76,T84,T95,T96 | done |
| T98 | 25 | Bundled skill 安装按名称去重 | `skill_bundle.py` 已按 manifest skill name 去重；目标同名技能存在时保留用户版本并跳过 bundled copy，`install --dry-run` 报告 `already_exists_deduped`，不要求覆盖或更新 | T89,T72 | done |
| T99 | 26 | 未完成 Task 汇总携带进度 | `unfinished_task_summary.py` 已提供可调用的未完成任务进度汇总器，`before_response` 显式请求时返回结构化 summary 和 Markdown；每个未完成 Task 输出状态、最近 checkpoint 或更新时间、验收进度、阻塞点、下一步和证据来源，缺证据标记 `unknown` 且不猜测百分比 | T05,T22,T24,T65 | done |
| T100 | 26 | 规范化 Codex 自生成文档到 `.codex/specs` | 建立 Kiro-like specs 三件套规范，要求 Codex 自己生成的需求、设计、任务、PRD、RFC 和计划类持久文档默认写入 `.codex/specs/<feature-slug>/`，并同步 `.gitignore`、仓库规则与安装模板 | T84,T88,T99 | done |

## 3. 当前推荐执行步

当前执行状态如下：

### Step 1（已完成）

- 目标：完成阶段 0 的插件脚手架。
- 范围：T00、T01、T02、T03。
- 不做：状态模型、检索、上下文编排、蒸馏逻辑。
- 验收：
  - 插件目录存在。
  - `plugin.json` 存在。
  - MCP 服务入口存在。
  - 存储目录存在。

### Step 2（已完成）

- 目标：完成阶段 1 的状态模型与最小读写接口。
- 范围：T04、T05、T06、T07。
- 不做：混合检索、上下文编排、蒸馏逻辑。
- 验收：
  - 任务状态 schema 明确。
  - 可读写 `task state`。
  - 可读写 `repo decisions`。
  - 可写回任务总结。

### Step 3（已完成）

- 目标：完成阶段 2 的代码优先最小混合检索。
- 范围：T08、T09、T10。
- 不做：上下文编排、蒸馏逻辑、hooks 自动触发。
- 验收：
  - 可对本地代码和文档执行精确检索。
  - 可对本地文本执行全文检索。
  - 检索输出可组织成统一证据包。
  - 语义检索接口保留占位，但不强行接入远程依赖。

### Step 4（已完成）

- 目标：完成阶段 3 的 context pack 与注入预算控制。
- 范围：T11、T12。
- 不做：蒸馏逻辑、hooks 自动触发。
- 验收：
  - 可从任务状态、项目决策、证据包构建统一 context pack。
  - 注入内容按层分组，而不是原始拼接。
  - 预算控制可裁剪低优先级证据。

### Step 5（已完成）

- 目标：完成阶段 4 的任务蒸馏与资产写回。
- 范围：T13、T14。
- 不做：hooks 自动触发。
- 验收：
  - 任务完成后可生成模式化输出。
  - 蒸馏结果可写回 `distilled/`。
  - 蒸馏资产有结构化索引可读。

### Step 6（已完成）

- 目标：完成阶段 5 的 hooks 自动触发、失败降级与示例验收。
- 范围：T15、T16、T17。
- 不做：更复杂的远程协同或副模型训练。
- 验收：
  - hooks 可触发读取、更新、回写流程。
  - 失败时可降级到无记忆模式。
  - 有一套本地示例流程或验收脚本可复现。

### Step 7（已完成）

- 目标：完成“无感使用”的默认接入，减少用户手动调用插件脚本的成本。
- 范围：T18、T19、T20。
- 不做：真实远程语义检索、平台私有 hook 能力扩展、模型训练。
- 验收：
  - repo 级 marketplace 可发现 `codex-memory`。
  - home 级 marketplace 与本机插件入口可安装并校验。
  - `hooks.json` 按 Codex 插件样例格式工作，并桥接到内部记忆事件。
  - 仓库级 `AGENTS.md` 规定默认自动使用流程。

### Step 8（已完成）

- 目标：完成用户全局层与项目私有层的存储隔离。
- 范围：T21。
- 不做：远程同步、多用户权限系统、向量库。
- 验收：
  - 默认项目私有记忆写入 `<项目根目录>/.codex/memories/`。
  - 显式用户全局记忆写入 `C:/Users/<USER>/.codex/codex-memory-harness/memories/`，官方 Codex Memories 目录 `C:/Users/<USER>/.codex/memories/` 保留给官方自动记忆。
  - `hook_runner.py` 与 `memory_server.py` 均支持 `--memory-scope`。
  - `.codex/memories/` 不进入检索证据包。

### Step 9（已完成）

- 目标：按 Harness Engineering 思路落地最小任务运行时。
- 范围：T22、T23。
- 不做：多 agent 调度、远程环境、复杂 eval 平台。
- 验收：
  - `harness_controller.py start` 可创建 task spec 并加载上下文。
  - `harness_controller.py checkpoint` 可记录 structured artifact 并写入 after_tool。
  - `harness_controller.py complete` 可执行 checklist、写总结并触发蒸馏。
  - 用户首选通过 `codex harness start/checkpoint/complete` 访问上述能力。
  - `.codex/harness/commands.json` 与 `project_profile.json` 存在且可解析。

### Step 10（已完成）

- 目标：把验证命令纳入 harness runtime，让 Codex 在收尾前自动运行配置化验证并记录证据。
- 范围：T24。
- 不做：远程 eval 平台、沙箱容器、多 agent 调度。
- 验收：
  - `verification_runner.py list` 可列出配置化命令。
  - `verification_runner.py run --profile primary` 可执行项目验证配置。
  - 用户首选通过 `codex harness verify list` 与 `codex harness verify run --profile primary` 访问验证入口。
  - 传入 `--task-id` 时可自动写入 harness checkpoint。
  - 明显危险命令会被拒绝。

### Step 11（已完成）

- 目标：让所有 Codex 窗口具备统一启动自检和项目初始化入口。
- 范围：T25。
- 不做：强制拦截真实 `codex` 命令、远程守护进程、宿主私有 hook。
- 验收：
  - `codex memory doctor` 可输出当前窗口 memory/harness 状态。
  - `codex memory init` 可创建缺失的项目 memory/harness 配置，且不覆盖已有配置。
  - 当前项目 primary 验证包含 bootstrap doctor。
  - 全局与项目说明包含 `codex memory doctor/init` 使用入口。

### Step 12（已完成）

- 目标：提供低风险 PowerShell 启动器，让 Codex 启动前自动执行 bootstrap/doctor。
- 范围：T26。
- 不做：覆盖真实 `codex` 命令、修改 PATH 顺序、强制 shell hook。
- 验收：
  - `codex memory doctor` 与 `codexm memory doctor` 可输出 doctor JSON。
  - PowerShell/POSIX shell profile 中注册 `codexm` 函数。
  - `codexm.ps1` 可定位真实 `codex` 命令，且不递归调用自身。
  - 当前项目 primary 验证包含 bootstrap doctor，并可通过 `codex harness verify run --profile primary` 执行。

### Step 13（已完成）

- 目标：让 PowerShell 中输入 `codex` 也自动经过 memory bootstrap，但不改写真实 Codex 安装文件。
- 范围：T27。
- 不做：修改 npm-global `codex.ps1` / `codex.cmd`、调整 PATH 顺序、删除真实 Codex shim。
- 验收：
  - PowerShell/POSIX shell profile 中注册 `codex` 函数，调用对应的 `codexm.ps1` 或 `codexm.sh`。
  - `codex-raw` 可绕过 wrapper 调用真实 Codex。
  - `CODEX_MEMORY_DISABLE_WRAPPER=1` 可作为禁用开关。
  - `codexm.ps1` 仍可跳过函数并定位真实外部 Codex 命令。

### Step 14（已完成）

- 目标：对照 Harness Engineering 外部资料，补齐当前能力、缺口和路线说明。
- 范围：T28、T29、T30。
- 不做：实现真实 SubAgent 自动执行器、向量数据库、embedding 索引、eval replay 平台。
- 验收：
  - `docs/EXTERNAL_BENCHMARK.md` 说明外部资料读取状态、当前实现对标和缺口。
  - `docs/MEMORY_RETRIEVAL_STRATEGY.md` 说明为什么当前不依赖向量数据库，以及后续可选接入路线。
  - `docs/SUBAGENT_WORKFLOW.md` 说明当前是角色协作协议，不是内建真实 SubAgent 自动执行器。
  - README、用户指南和系统总结有对应入口。

### Step 15（已完成）

- 目标：针对 Unity、LayaBox/LayaAir、Cocos Creator 客户端项目补齐专项工作流路线。
- 范围：T34。
- 不做：实现 `codex game-client` 命令、写死业务项目引擎路径、引入外部游戏模板。
- 验收：
  - `docs/GAME_CLIENT_WORKFLOW.md` 对 BMAD-METHOD、BMGD 和 Claude-Code-Game-Studios 进行客户端向裁剪。
  - 文档覆盖客户端任务分级、角色分工、路径规则、验证 profile、未来命令路线。
  - README、用户指南和系统总结有对应入口。

### Step 16（已完成）

- 目标：补齐多项目 workspace 下的自动路由设计。
- 范围：T36。
- 不做：实现 workspace scanner、route plan 运行时、真实 SubAgent 自动执行器。
- 验收：
  - `docs/WORKSPACE_ADAPTIVE_ROUTING.md` 说明 workspace 子项目发现、任务路由、SubAgent route binding、综合事务 coordinator、验证聚合和冲突处理。
  - `docs/GAME_CLIENT_WORKFLOW.md` 明确游戏客户端只是 workspace routing 的 `game_client` domain。
  - `docs/SUBAGENT_WORKFLOW.md` 增加 route binding 说明。
  - README、用户指南和系统总结有对应入口。

### Step 17（已完成）

- 目标：全面审查 workspace routing、game client、SubAgent 和系统总结文档设计，修正不一致和缺口。
- 范围：T39、T40、T44、T45、T46。
- 不做：实现 runtime scanner、route planner、verification aggregator。
- 验收：
  - `docs/WORKSPACE_ADAPTIVE_ROUTING.md` 补齐设计审查结论、route plan artifact、verification cwd 差距和 memory 分层策略。
  - `docs/SUBAGENT_WORKFLOW.md` 的 artifact 示例包含 `project_id`、`domain`、`assigned_scope` 和 `cwd`。
  - `docs/GAME_CLIENT_WORKFLOW.md` 明确 `game-client.json` 只适合单客户端仓库或 workspace 中的局部扩展。
  - `docs/PRIVACY.md` 补齐 workspace scanner、route plan、子项目 memory 和游戏资产/渠道敏感项边界。
  - `docs/MEMORY_RETRIEVAL_STRATEGY.md` 补齐 workspace/project/domain/scope/task_id 等未来检索 metadata。
  - `docs/MEMORY_LAYERING.md` 说明用户全局层、项目私有层、项目共享层分别放什么，以及共享层冲突处理。
  - `retrieval_store.py` 修复 working set 中 `*.md` 这类 glob 派生检索词导致 `rg` 正则报错的问题。
  - `docs/WORKSPACE_ROUTING_TASK_LIST.md` 拆分 workspace routing 实现任务并同步当前进度。
  - README、用户指南、系统总结和本任务清单有对应入口。

### Step 17A（已完成）

- 目标：补齐 AI 诊断 Debug 日志统一开关和发布关闭策略。
- 范围：T49。
- 不做：实现裸日志扫描器、构建宏检查器或 release gate runtime。
- 验收：
  - `docs/AI_DIAGNOSTIC_LOGGING.md` 明确诊断日志定义、统一开关、敏感边界和 release 关闭要求。
  - `docs/GAME_CLIENT_WORKFLOW.md` 补齐 Unity、LayaBox/LayaAir、Cocos Creator 的诊断日志策略。
  - `docs/WORKSPACE_ADAPTIVE_ROUTING.md` 说明 route plan、SubAgent 和 release_train 如何处理 diagnostic scope。
  - README、用户指南、隐私说明、系统总结和本任务清单有对应入口。

### Step 17B（已完成）

- 目标：说明完整实现后的实际开发流程，并落地流程图。
- 范围：T51。
- 不做：实现 workspace scanner、SubAgent runtime、verification aggregation 或 release gate runtime。
- 验收：
  - `docs/FULL_DEVELOPMENT_WORKFLOW.md` 给出用户体感流程、内部自动编排流程和 Mermaid 总流程图。
  - 文档覆盖 bootstrap、memory 装载、workspace scanner、task router、SubAgent route binding、AI 诊断日志、验证聚合、release gate 和 memory 沉淀。
  - README、用户指南、workspace 路由文档、系统总结和本任务清单有对应入口。

### Step 18（已完成）

- 目标：开始把团队共享 memory 从设计推进到可初始化模板。
- 范围：T47。
- 不做：promote 命令、shared validate 命令、自动索引重建。
- 验收：
  - `codex memory init` 会创建 `.codex/shared/README.md`、`index.json` 和 `decisions/`、`facts/`、`workflows/`、`routes/` 目录。
  - `templates/project/.codex/shared` 提供 README、index 和示例 Markdown。
  - `schemas/shared_memory.schema.json` 定义共享记忆 front matter 的字段约束。
  - `.gitignore` 放行 `.codex/shared/**`，继续忽略 `.codex/memories/`、`.codex/harness/tasks/`、数据库和 JSONL。

### Step 18A（已完成）

- 目标：补齐写入前敏感信息扫描器，给 promote 和 release gate 提供基础能力。
- 范围：T31。
- 不做：完整 secret detection 产品、远程扫描、release gate 专项规则。
- 验收：
  - 新增 `sensitive_scan.py`，支持敏感 key、authorization、token assignment、JWT、AK 和私钥块识别。
  - memory 写入、harness checkpoint 和 distillation 写入前会先调用扫描器。
  - 可脱敏内容写入 `[REDACTED]` 摘要；私钥块阻断持久化。
  - 单测覆盖敏感 key/token 脱敏和 task summary 写入前脱敏。

### Step 19（已完成）

- 目标：实现项目私有 memory 到项目共享层的最小提升命令。
- 范围：T48。
- 不做：严格 JSON Schema 校验、PR 自动 review、多人冲突自动解决。
- 验收：
  - 新增 `shared_memory.py`，支持 promote、shared validate 和 shared index rebuild。
  - `codex memory promote --task-id <task-id> --kind fact` 可从本地 summary/decision 生成 `.codex/shared` Markdown。
  - `codex memory shared validate` 可检查 front matter、状态枚举和敏感内容。
  - `codex memory shared index rebuild` 可重建 `.codex/shared/index.json`。
  - 单测覆盖 summary promote 和 shared validate。

### Step 20（已完成）

- 目标：把 workspace routing 设计收束为可验证 schema 和项目配置模板。
- 范围：T38、WR-05、WR-06、WR-07、WR-08。
- 不做：scanner/route planner 的生命周期自动集成、SubAgent route binding runtime、完整验证聚合平台。
- 验收：
  - 新增 `schemas/workspace_project_inventory.schema.json`，定义 workspace scanner 的 project inventory 输出。
  - 新增 `schemas/workspace_routing_config.schema.json`，定义 `.codex/harness/workspace-routing.json` 显式配置。
  - 新增 `schemas/workspace_route_plan.schema.json`，统一 `routes[]`、`verification_profile_ids`、memory plan 和 coordinator 契约字段。
  - 新增 `schemas/subagent_route_binding.schema.json`，定义 SubAgent 的 project/domain/cwd/scope/rules/profile/artifact policy 绑定。
  - 新增 `schemas/verification_aggregation.schema.json`，定义多项目验证计划、结果、gap 和 release gate 摘要。
  - 新增 `templates/project/.codex/harness/workspace-routing.json`，覆盖 Unity、Laya、Cocos 客户端、服务器、后台、文档和美术工程示例。
  - 单测覆盖 schema JSON、模板字段、release package 收录边界。

### Step 21（已完成）

- 目标：实现 workspace routing 的最小只读发现运行时。
- 范围：T37、WR-09、WR-10。
- 不做：route plan artifact 写回、自动 SubAgent 派发、完整验证聚合平台、业务项目文件写入。
- 验收：
  - 新增 `workspace_scanner.py`，输出 project inventory JSON。
  - 支持显式 `.codex/harness/workspace-routing.json` 优先，并与扫描候选合并。
  - 支持 Unity、LayaBox/LayaAir、Cocos Creator、游戏服务器、后台 Web、设计文档、美术工程和发布工程常见信号。
  - 新增 `codex workspace doctor` 与 `codex workspace scan` 入口。
  - 单测覆盖扫描识别、显式配置优先和 launcher dispatcher。

### Step 22（已完成）

- 目标：实现 workspace routing 的最小只读 route planner。
- 范围：WR-11、WR-12、WR-13。
- 不做：自动 SubAgent 派发、scope guard、后续 lifecycle 软集成、业务项目文件写入。
- 验收：
  - 新增 `workspace_router.py`，根据 inventory、任务文件、working set、cwd 和 changed paths 生成 route plan。
  - `codex workspace route --task-file task.json` 可输出单项目、多项目和低置信度 route plan。
  - 支持显式 project id 优先、路径/cwd/text 匹配和 fallback 降级。
  - route plan 使用 `routes[]`、`verification_profile_ids`、memory plan、coordination 和 diagnostic logging 字段。
  - 单测覆盖单项目路由、客户端/服务器契约路由和显式配置项目路由。

### Step 23（已完成）

- 目标：实现 workspace verification aggregation 的最小运行时。
- 范围：WR-14、WR-15、WR-16。
- 不做：SubAgent route binding runtime、scope guard、后续 lifecycle 软集成。
- 验收：
  - `verification_runner.py` 的 command spec 支持相对 `cwd`，并阻止逃出 project root。
  - 新增 `workspace_verifier.py`，可根据 route plan 聚合多项目 verification profile。
  - `codex workspace verify` 支持 route file、task file、changed paths 和 `--no-run`。
  - 缺失 profile 或 command 写入 `gaps[]`，不伪装为通过。
  - `codex workspace route --checkpoint` 可把 route plan 写入 harness checkpoint。
  - 单测覆盖 command cwd、cwd 越界拒绝、workspace verify 聚合和 gap。

### Step 24（已完成）

- 目标：实现 SubAgent route binding、scope guard、coordinator summary 和冲突检测的最小运行时。
- 范围：T32、T42、WR-17、WR-18、WR-19、WR-20。
- 不做：自动启动真实 SubAgent、后续 lifecycle 软集成、跨进程调度。
- 验收：
  - 新增 `workspace_subagents.py`，支持 bind、scope-check 和 summarize。
  - `codex workspace bind --route-file route.json` 可把 route plan 转换为 coordinator/specialist bindings。
  - `codex workspace scope-check` 可检查 touched paths 是否越过 assigned/denied scope，并输出 cross_project_dependencies。
  - `codex workspace summarize` 可汇总同文件多 owner 冲突、scope guard 结果、verification gaps 和发布顺序。
  - 单测覆盖 coordinator binding、scope 越权和同文件冲突检测。

### Step 25（已完成）

- 目标：把 workspace routing 结果接入 memory hook 生命周期，并修正当前仓库根工具工程路由。
- 范围：WR-21、WR-22、WR-23、WR-24、T52。
- 不做：自动启动真实 SubAgent、发布级完整验证平台、业务项目文件写入。
- 验收：
  - 新增 `workspace_lifecycle.py`，避免 `hook_runner.py` 聚合过多 routing 逻辑并保持单文件行数上限。
  - `before_task` 自动生成 route plan 和 SubAgent bindings，并写入 task metadata。
  - `after_tool` 根据 touched paths 重算 route/bindings，并执行 lifecycle scope guard。
  - `before_response` 输出 `workspace_routing_review`，报告低置信、routing 降级、verification gap 和 scope gap。
  - scanner 能识别 `workspace_meta` 根工具工程，router 会避免根项目吞掉已有子项目路径。
  - 单测覆盖 hook lifecycle、routing 降级 review、多项目 scope guard 分发和 workspace meta 路由。

### Step 26（已完成）

- 目标：补齐 SubAgent dispatch plan，给宿主 SubAgent 或人工编排提供统一派发计划。
- 范围：T53、WR-31。
- 不做：启动真实 agent 进程、远程执行、超时取消状态机。
- 验收：
  - 新增 `subagent_scheduler.py`，根据 route plan 和 bindings 生成 coordinator prepare、specialist dispatch、coordinator summarize 计划。
  - `codex workspace schedule --route-file route.json` 可输出 dispatch plan。
  - `--checkpoint` 可把 `subagent_dispatch_plan` 写入 harness artifact。
  - 单测覆盖 coordinator/specialist prompt、依赖和 scope 信息。

### Step 27（已完成）

- 目标：补齐游戏客户端 Unity/Laya/Cocos profile 模板生成器。
- 范围：T35、T54、WR-25。
- 不做：新增顶层 `codex game-client ...`、写死本机引擎路径、替业务项目实现 Editor 脚本。
- 验收：
  - 新增 `game_client_profiles.py`，支持 `template` 和 `init`。
  - `codex workspace game-client init --engine unity|laya|cocos` 会合并写入 `.codex/harness/commands.json`、`project_profile.json` 和 `game-client.json`。
  - 生成 `client_quick`、`client_diagnostic`、`client_release` profile 模板。
  - 单测覆盖不覆盖已有命令和 Cocos/Unity 模板内容。

### Step 28（已完成）

- 目标：补齐基础 AI 诊断日志 release gate runtime。
- 范围：T50、WR-32。
- 不做：完整发布平台、所有引擎平台配置扫描、渠道包和热更流水线检查。
- 验收：
  - 新增 `diagnostic_gate.py`，扫描 release route scope 内的常见客户端代码文件。
  - `workspace_verifier.py` 在 `release_blocking` route 中把诊断 gate 纳入总体阻断状态。
  - 基础检查覆盖诊断开启标记、调试宏、临时 sink 和裸日志绕过统一门面。
  - 单测覆盖裸日志阻断、统一门面放行和 clean route 通过。

## 4. 每步完成后的固定动作

每完成一个主步，都执行以下动作：

1. 更新本清单状态。
2. 记录新增文件与目的。
3. 记录是否影响下一步边界。
4. 如有阻塞，明确写出阻塞原因和替代方案。

## 5. 暂不进入当前实现的事项

以下事项仍未实现：

- 复杂向量检索
- 远程数据库
- 副模型训练
- 高级 rerank
- 云端同步
- 严格 JSON Schema 校验 shared memory front matter
- 自动启动/调度真实 SubAgent
- 发布级完整 workspace 验证平台
- 真实 SubAgent 自动执行器
- 平台化 eval replay
- memory archive/cleanup 与 retention policy
- 自动历史记忆挖掘 runtime、候选自动提升、治理命令和 context 注入
- session-worktree 宿主级强制 lifecycle、stale cleanup 和多 session 协作

## 6. 当前状态与下一步

当前已完成至 Step 39，状态如下；其中 Step 37 仍有 hook/宿主强制接入的后续增强项：

- Step 6 已完成
- Step 7 已完成
- Step 8 已完成
- Step 9 已完成
- Step 10 已完成
- Step 11 已完成
- Step 12 已完成
- Step 13 已完成
- Step 14 已完成
- Step 15 已完成
- Step 16 已完成
- Step 17 已完成
- Step 17A 已完成
- Step 17B 已完成
- Step 18 已完成
- Step 18A 已完成
- Step 19 已完成
- Step 20 已完成
- Step 21 已完成
- Step 22 已完成
- Step 23 已完成
- Step 24 已完成
- Step 25 已完成
- Step 26 已完成：SubAgent dispatch plan 与 `codex workspace schedule`
- Step 27 已完成：游戏客户端 Unity/Laya/Cocos profile 模板生成器
- Step 28 已完成：基础 AI 诊断日志 release gate runtime
- Step 29 已完成：服务器/后台/文档/美术业务模板与 `codex workspace project-template`
- Step 30 已完成：本仓库 dogfood workspace routing 配置与发布迁移说明
- Step 31 已完成：workspace memory 自动分层写入会在任务完成时根据 route plan `memory_plan` 写入 `.codex/shared` proposed 草稿，并可用 `workspace_memory_writer.py` 进行 dry-run/confirm。
- Step 32 受阻：真实 SubAgent 自动执行器仍依赖宿主 SubAgent API；当前仓库已能生成 `host_spawn_requests` 和调度计划，并通过 `subagent_receipts.py` 导入宿主执行回执与 readiness report。
- Step 33 进行中：release profile/evidence gate、release manifest gate 与 eval replay 已完成；完整发布级验证平台仍依赖业务项目渠道包、热更、平台构建、CI 和回滚材料。
- Step 34 已完成：安装器 dry-run、旧全局 memory marker 迁移工具、custom agents 模板、memory archive/cleanup 与可选本地语义检索 provider 均已落地。
- Step 35 已完成：自动历史记忆挖掘 runtime 已落地事件账本、候选挖掘、accepted context 注入和治理命令；低风险偏好可进入 accepted context，高风险或冲突候选保留为可审查状态。
- Step 36 已完成：review gate 优化 runtime 已提供 `codex review status/preflight/plan/record/findings/ledger`，最终语义改为先创建 candidate commit，再用 `codex xhigh review --commit <commit-sha>` 审核被审提交；通过 preflight、commit fingerprint、review ledger、runner 恢复记录和 slice planner 降低长耗时与重复失败。
- Step 37 进行中：最小 session-worktree write guard 已提供 `codex workspace session ...`、`codex workspace worktree list` 和 `codex workspace write-guard ...`；当前能在 dirty primary checkout 或已有其他 active write lease 时创建 managed worktree 并返回 `effective_cwd`。后续还需把 before_first_write 做成宿主/Hook 强制拦截，并补 stale cleanup 与多 session 合并。
- Step 38 已完成：stale/cleanup 治理已完成只读、dry-run、confirm 清理和 recover 切片；`codex workspace worktree list` 会展示 active、stale、dirty orphan、prunable、pruned 和 needs_user_review，`codex workspace worktree prune --dry-run` 只输出 released 且 clean at base 的 managed worktree 候选，不执行删除，`codex workspace worktree prune --confirm` 会重新校验 Git 状态和 managed worktree 容器路径后执行 `git worktree remove` 并把 binding 标记为 `pruned`，`codex workspace worktree recover <binding-id>` 只恢复 clean at base 的 managed stale/prunable binding。多 session 合并继续由 T83 跟进。
- Step 39 已完成：skill-first governance runtime 已完成 T89-T97；bundled skills 改为 manifest-driven 全量可用技能，hook lifecycle 输出 skill routing audit，Requirements Gate 扩展治理字段，SubAgent dispatch 前输出 blocker/scope matrix，release profile 原型覆盖小游戏/WebGL/AB/包体/性能证据，OpenSpec/BMAD governance adapter 连接 verification 与 commit-based review evidence。
- Step 40 已完成：bundled skill 安装状态按技能名去重；随包 `harness-release-gate` 已是 candidate commit + `codex xhigh review --commit <commit-sha>` 流程。若用户本机已安装同名技能，安装器保留用户版本并跳过 bundled copy，`install --dry-run` 报告 `already_exists_deduped`，不要求覆盖或更新。
- Step 41 已完成：T33/T64/T65/T67-T71 已完成实现和定向测试；T55/T59/T83/T87 的可离线切片已落地为 release manifest gate、host receipt/readiness report 和 requirements conflict scanner；剩余项明确为宿主、CI、业务构建材料、强制写入 hook 或外部 BMAD 执行依赖，不在仓库内伪造完成状态。
- Step 42 已完成：T99 已实现。新增 `unfinished_task_summary.py` 只读聚合器，优先从 task list、`task_state`、task summary、harness task spec、run state 和 artifacts 中提取证据；`before_response` 支持通过 `include_unfinished_tasks` 或 `include_unfinished_task_progress` 显式返回结构化 `unfinished_task_summary` 和 Markdown。输出每个未完成 Task 的状态、最近进展、剩余验收、阻塞点、下一步和证据来源；缺少证据时标记 `unknown`，不生成无依据百分比。
- Step 43 已完成：T100 已实现。参考 `H:\dev\company\GPTProxy\.kiro\specs` 的 `requirements.md`、`design.md`、`tasks.md` 三件套，已在 `.codex/specs/codex-generated-documents/` 落地本项目自己的 specs 规范；已同步 `.gitignore` 放行 `.codex/specs/**`，并更新仓库规则、安装模板、README 和 skill-first 治理文档，保证后续 Codex 自生成需求、设计和任务文档默认进入 `.codex/specs/<feature-slug>/`。
