# Workspace Routing 任务拆分与进度

> Canonical planning source: this Codex-generated workspace routing task document was migrated from `docs/WORKSPACE_ROUTING_TASK_LIST.md` to `.codex/specs/backlog-governance/workspace-routing-tasks.md`. The old `docs/` path is now only a compatibility stub.

## 1. 目的

本文把 `docs/WORKSPACE_ADAPTIVE_ROUTING.md` 的设计拆成可执行任务，并同步当前项目进度。

当前状态：已完成文档设计、设计审查、隐私边界、检索作用域同步、workspace routing schema 与项目配置模板、只读 workspace scanner、最小只读 route planner、最小 workspace verification aggregation、SubAgent route binding、scope guard、coordinator summary、dispatch plan、host receipt readiness report、Codex SubAgent 执行通道 dogfood、memory lifecycle 软集成、workspace memory 自动分层写入、游戏客户端自动扫描默认规则、游戏客户端 profile 模板生成器、服务器/后台/文档/美术业务模板、本仓库 dogfood workspace routing 配置、workspace routing 发布迁移说明、基础 AI 诊断日志 release gate 和 release manifest evidence gate；尚未实现完整发布级平台构建流水线。

## 2. 进度状态

| 状态 | 含义 |
|---|---|
| done | 已完成并验证 |
| doing | 当前正在实现 |
| todo | 未开始 |
| blocked | 有明确阻塞 |

## 3. 总体里程碑

| ID | 里程碑 | 目标 | 状态 |
|---|---|---|---|
| WR-M0 | 文档和设计审查 | 明确 workspace routing 设计、边界、风险和实现拆分 | done |
| WR-M1 | 只读发现 | 扫描 workspace，输出 project inventory，不修改项目文件 | done |
| WR-M2 | 路由计划 | 根据任务、diff、SubAgent scope 生成 route plan | done |
| WR-M3 | 验证聚合 | 按 route plan 聚合多个项目的 verification profile | done |
| WR-M4 | SubAgent 集成 | 为每个 SubAgent 绑定 project/domain/scope/rules/profile ids | done |
| WR-M5 | 生命周期集成 | 在 before_task/after_tool/before_response 中自动使用路由结果 | done |
| WR-M6 | 业务模板 | 为游戏客户端、服务器、后台、文档、美术工程提供可配置模板 | done |
| WR-M7 | Memory 分层写入 | 根据 route plan `memory_plan` 写入 `.codex/shared` proposed 草稿 | done |

## 4. 详细任务

| ID | 任务 | 产出物 | 依赖 | 状态 |
|---|---|---|---|---|
| WR-00 | 审查现有文档设计 | 修正后的 README、系统总结、SubAgent、Game Client、Workspace 文档 | 无 | done |
| WR-01 | 定义 workspace routing 总设计 | `docs/WORKSPACE_ADAPTIVE_ROUTING.md` | WR-00 | done |
| WR-02 | 定义游戏客户端 domain 关系 | `docs/GAME_CLIENT_WORKFLOW.md` 中说明 `game_client` 是 workspace domain | WR-00 | done |
| WR-03 | 定义 SubAgent route binding | `docs/SUBAGENT_WORKFLOW.md` route binding 章节 | WR-00 | done |
| WR-04 | 建立任务拆分与进度表 | `.codex/specs/backlog-governance/workspace-routing-tasks.md`，旧 `docs/WORKSPACE_ROUTING_TASK_LIST.md` 仅保留兼容 stub | WR-01 | done |
| WR-04A | 同步隐私与检索边界 | `docs/PRIVACY.md`、`docs/MEMORY_RETRIEVAL_STRATEGY.md` 说明 workspace/project/domain scope | WR-01 | done |
| WR-05 | 定义 project inventory schema | `schemas/workspace_project_inventory.schema.json` | WR-01 | done |
| WR-06 | 定义 route plan schema | `schemas/workspace_route_plan.schema.json` | WR-05 | done |
| WR-07 | 定义 subagent route binding schema | `schemas/subagent_route_binding.schema.json` | WR-06 | done |
| WR-08 | 定义 verification aggregation schema | `schemas/verification_aggregation.schema.json` | WR-06 | done |
| WR-09 | 实现 workspace scanner | `workspace_scanner.py` 与 `codex workspace doctor/scan` | WR-05 | done |
| WR-10 | 支持显式 workspace 配置 | 读取 `.codex/harness/workspace-routing.json` 并优先并入 inventory | WR-05 | done |
| WR-11 | 实现配置优先级合并 | 显式 project id > cwd/path/text > 显式配置/扫描 inventory > fallback | WR-10 | done |
| WR-12 | 实现 route planner | `workspace_router.py` 与 `codex workspace route` | WR-06,WR-09 | done |
| WR-13 | 增加低置信度降级 | `unknown_low_confidence` 输出 `readonly_analysis` fallback | WR-12 | done |
| WR-14 | 扩展 verification command cwd | `CommandSpec.cwd`，限制在 project root 内 | WR-08 | done |
| WR-15 | 实现 workspace verify aggregator | `workspace_verifier.py` 与 `codex workspace verify` | WR-08,WR-14 | done |
| WR-16 | route plan 写入 harness artifact | `codex workspace route --checkpoint` 和 verify checkpoint | WR-12 | done |
| WR-17 | SubAgent 启动绑定 route | `workspace_subagents.py bind` 生成 route binding artifact | WR-07,WR-16 | done |
| WR-18 | Specialist scope guard | `workspace_subagents.py scope-check` 检查 assigned/denied scope | WR-17 | done |
| WR-19 | Coordinator 汇总规则 | `workspace_subagents.py summarize` 汇总验证 gap、发布顺序和 scope 结果 | WR-15,WR-17 | done |
| WR-20 | 冲突检测 | summarize 检测同文件多 owner 修改冲突 | WR-19 | done |
| WR-21 | memory scope 策略接入 | route plan `memory_plan` 写入 task metadata，区分 workspace/project semantic scope | WR-16 | done |
| WR-22 | before_task 集成 | 自动扫描 workspace、生成初始 route plan 和 SubAgent bindings，写入 metadata | WR-12,WR-21 | done |
| WR-23 | after_tool 集成 | 根据 touched paths 重算 affected projects、bindings 和 scope guard | WR-22 | done |
| WR-24 | before_response 集成 | 输出 routing review，报告低置信、routing 降级、verification gap 和 scope gap | WR-23 | done |
| WR-25 | 游戏客户端模板 | `codex workspace game-client init/template` 生成 Unity/Laya/Cocos profile 模板 | WR-10 | done |
| WR-25A | 游戏客户端自动路由默认规则 | 自动扫描到 Unity/Laya/Cocos 时补充 `game_client/<engine>` 和任务类型规则 | WR-12 | done |
| WR-26 | 游戏服务器模板 | `codex workspace project-template init --domain game_server` 生成 Go/Java/C#/Node 服务端 rules 和 profile 示例 | WR-10 | done |
| WR-27 | 后台/Web 模板 | `codex workspace project-template init --domain backoffice_web` 生成管理端、GM、运营后台 rules 和 profile 示例 | WR-10 | done |
| WR-28 | 文档与美术工程模板 | `codex workspace project-template init --domain design_docs|art_pipeline` 生成 docs/art/asset pipeline rules 和 profile 示例 | WR-10 | done |
| WR-29 | 测试覆盖 | scanner、route planner、aggregation、scope guard 和 lifecycle hook 行为测试 | WR-09,WR-12,WR-15,WR-18 | done |
| WR-30 | 发布与迁移说明 | `docs/WORKSPACE_ROUTING_MIGRATION.md` 说明用户如何从普通 harness 升级到 workspace routing | WR-29 | done |
| WR-31 | SubAgent dispatch plan | `codex workspace schedule` 生成 coordinator/specialist 调度计划 | WR-17,WR-19 | done |
| WR-32 | AI 诊断日志 release gate | release route 阻断诊断开关、临时 sink 和裸日志绕过 | WR-15,WR-25A | done |
| WR-33 | 本仓库 workspace routing dogfood 配置 | 当前仓库根 `.codex/harness/workspace-routing.json` 对齐模板和当前源码布局 | WR-10 | done |
| WR-34 | workspace memory 自动分层写入 | 按 route plan `memory_plan` 把 workspace summary 与子项目事实分层沉淀 | WR-21 | done |

## 5. 当前项目进度同步

当前仓库已经具备：

- `codex memory doctor/init`。
- `codex harness start/checkpoint/complete`。
- `codex harness verify run --profile primary`。
- 本地 memory、summary、distillation。
- 项目级 `.codex/harness/commands.json` 与 `project_profile.json`。
- 显式 workspace 配置模板 `templates/project/.codex/harness/workspace-routing.json`，以及本仓库根 `.codex/harness/workspace-routing.json` dogfood 配置。
- Workspace project inventory、routing config、route plan、SubAgent route binding 和 verification aggregation schema。
- `codex workspace doctor/scan` 只读 workspace scanner。
- `codex workspace route` 只读 route planner。
- `codex workspace verify` 最小 verification aggregation。
- `codex workspace bind/scope-check/summarize` 最小 SubAgent binding、scope guard、coordinator summary 和冲突检测。
- `codex workspace schedule` 最小 SubAgent dispatch plan 生成。
- `codex workspace game-client init/template` Unity、LayaBox/LayaAir、Cocos Creator profile 模板生成。
- `codex workspace project-template init/template` 服务器、后台/Web、文档和美术工程业务模板生成。
- workspace verifier 的基础 AI 诊断日志 release gate。
- `before_task` / `after_tool` / `before_response` 的 workspace routing 软集成。
- `workspace_meta` 根工具工程识别和根路径路由。
- SubAgent 角色协作协议文档。
- 游戏客户端 domain 文档。
- Workspace routing 设计文档。

当前仓库尚未具备：

- 发布级完整验证闭环和 release gate 平台。
- 插件内建独立 agent 子进程调度；当前正式执行通道是主 Agent 按 dispatch plan 调用 Codex SubAgent，并用 receipt/readiness report 回写结果。

## 6. 推荐下一步

下一步优先级：

1. 后续主线：实现更完整的发布验证平台。
2. 后续主线：补强多 session integration worktree final gate。

这个顺序可以降低风险：已完成只读发现、计划、验证、SubAgent binding、dispatch plan、Codex SubAgent 派发通道、游戏客户端模板、业务模板、dogfood 配置、发布迁移说明、基础 release gate、lifecycle 软集成和 workspace memory 自动分层写入；接下来再进入发布级平台和多 session integration gate。
