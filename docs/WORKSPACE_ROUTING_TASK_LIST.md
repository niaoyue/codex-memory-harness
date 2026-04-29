# Workspace Routing 任务拆分与进度

## 1. 目的

本文把 `docs/WORKSPACE_ADAPTIVE_ROUTING.md` 的设计拆成可执行任务，并同步当前项目进度。

当前状态：已完成文档设计、设计审查、隐私边界、检索作用域同步、workspace routing schema 与项目配置模板、只读 workspace scanner、最小只读 route planner、最小 workspace verification aggregation、SubAgent route binding、scope guard、coordinator summary 和 memory lifecycle 软集成；尚未实现自动 SubAgent 调度或发布级完整验证平台。

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
| WR-M6 | 业务模板 | 为游戏客户端、服务器、后台、文档、美术工程提供可配置模板 | todo |

## 4. 详细任务

| ID | 任务 | 产出物 | 依赖 | 状态 |
|---|---|---|---|---|
| WR-00 | 审查现有文档设计 | 修正后的 README、系统总结、SubAgent、Game Client、Workspace 文档 | 无 | done |
| WR-01 | 定义 workspace routing 总设计 | `docs/WORKSPACE_ADAPTIVE_ROUTING.md` | WR-00 | done |
| WR-02 | 定义游戏客户端 domain 关系 | `docs/GAME_CLIENT_WORKFLOW.md` 中说明 `game_client` 是 workspace domain | WR-00 | done |
| WR-03 | 定义 SubAgent route binding | `docs/SUBAGENT_WORKFLOW.md` route binding 章节 | WR-00 | done |
| WR-04 | 建立任务拆分与进度表 | `docs/WORKSPACE_ROUTING_TASK_LIST.md` | WR-01 | done |
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
| WR-25 | 游戏客户端模板 | Unity/Laya/Cocos project rules 和 profile 示例 | WR-10 | todo |
| WR-26 | 游戏服务器模板 | Go/Java/C#/Node 服务端 rules 和 profile 示例 | WR-10 | todo |
| WR-27 | 后台/Web 模板 | 管理端、GM、运营后台 rules 和 profile 示例 | WR-10 | todo |
| WR-28 | 文档与美术工程模板 | docs/art/asset pipeline rules 和 profile 示例 | WR-10 | todo |
| WR-29 | 测试覆盖 | scanner、route planner、aggregation、scope guard 和 lifecycle hook 行为测试 | WR-09,WR-12,WR-15,WR-18 | done |
| WR-30 | 发布与迁移说明 | 用户如何从普通 harness 升级到 workspace routing | WR-29 | todo |

## 5. 当前项目进度同步

当前仓库已经具备：

- `codex memory doctor/init`。
- `codex harness start/checkpoint/complete`。
- `codex harness verify run --profile primary`。
- 本地 memory、summary、distillation。
- 项目级 `.codex/harness/commands.json` 与 `project_profile.json`。
- 显式 workspace 配置模板 `templates/project/.codex/harness/workspace-routing.json`。
- Workspace project inventory、routing config、route plan、SubAgent route binding 和 verification aggregation schema。
- `codex workspace doctor/scan` 只读 workspace scanner。
- `codex workspace route` 只读 route planner。
- `codex workspace verify` 最小 verification aggregation。
- `codex workspace bind/scope-check/summarize` 最小 SubAgent binding、scope guard、coordinator summary 和冲突检测。
- `before_task` / `after_tool` / `before_response` 的 workspace routing 软集成。
- `workspace_meta` 根工具工程识别和根路径路由。
- SubAgent 角色协作协议文档。
- 游戏客户端 domain 文档。
- Workspace routing 设计文档。

当前仓库尚未具备：

- workspace 级 memory 与子项目 memory 的自动分层写入；当前只在 route plan metadata 中记录 `memory_plan`。
- 发布级完整验证闭环和 release gate 平台。
- 自动启动/调度真实 SubAgent。

## 6. 推荐下一步

下一步优先级：

1. WR-25 到 WR-28：补业务模板，覆盖客户端、服务器、后台、文档和美术工程。
2. WR-30：补发布与迁移说明。
3. T50：实现 AI 诊断日志 release gate runtime。
4. 后续再实现自动 SubAgent 调度、更完整的发布验证平台和 workspace memory 自动分层写入。

这个顺序可以降低风险：已完成只读发现、计划、验证、SubAgent binding 和 lifecycle 软集成；接下来先补业务模板和 release gate，再考虑自动调度与发布级平台。
