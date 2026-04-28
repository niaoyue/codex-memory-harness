# Workspace Routing 任务拆分与进度

## 1. 目的

本文把 `docs/WORKSPACE_ADAPTIVE_ROUTING.md` 的设计拆成可执行任务，并同步当前项目进度。

当前状态：已完成文档设计、设计审查、隐私边界和检索作用域同步；尚未实现 workspace scanner、route planner、自动验证聚合或 SubAgent route binding runtime。

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
| WR-M1 | 只读发现 | 扫描 workspace，输出 project inventory，不修改项目文件 | todo |
| WR-M2 | 路由计划 | 根据任务、diff、SubAgent scope 生成 route plan | todo |
| WR-M3 | 验证聚合 | 按 route plan 聚合多个项目的 verification profile | todo |
| WR-M4 | SubAgent 集成 | 为每个 SubAgent 绑定 project/domain/scope/rules/profiles | todo |
| WR-M5 | 生命周期集成 | 在 before_task/after_tool/before_response 中自动使用路由结果 | todo |
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
| WR-05 | 定义 project inventory schema | JSON schema 文档或 Python schema 常量 | WR-01 | todo |
| WR-06 | 定义 route plan schema | task route、affected projects、rules、profiles、risk、confidence | WR-05 | todo |
| WR-07 | 定义 subagent route binding schema | project_id、domain、assigned_scope、rules、profiles、artifact policy | WR-06 | todo |
| WR-08 | 定义 verification aggregation schema | per-project profile、cwd、result、skip reason、blocking status | WR-06 | todo |
| WR-09 | 实现 workspace scanner | 只读扫描目录，识别客户端、服务器、后台、文档、美术、CI | WR-05 | todo |
| WR-10 | 支持显式 workspace 配置 | `.codex/harness/workspace-routing.json` 读取与合并 | WR-05 | todo |
| WR-11 | 实现配置优先级合并 | 用户指定 > SubAgent 指定 > 显式配置 > 自动识别 > fallback | WR-10 | todo |
| WR-12 | 实现 route planner | 根据请求、working set、diff、inventory 输出 route plan | WR-06,WR-09 | todo |
| WR-13 | 增加低置信度降级 | 只读分析或请求确认，不自动执行高风险验证 | WR-12 | todo |
| WR-14 | 扩展 verification command cwd | 支持每个命令或 profile 指定 project cwd | WR-08 | todo |
| WR-15 | 实现 workspace verify aggregator | `codex workspace verify --auto` 或等价内部 runner | WR-08,WR-14 | todo |
| WR-16 | route plan 写入 harness artifact | checkpoint 记录路由、原因、置信度、profiles | WR-12 | todo |
| WR-17 | SubAgent 启动绑定 route | 将 route binding 放入 SubAgent 初始上下文或 artifact | WR-07,WR-16 | todo |
| WR-18 | Specialist scope guard | 检查 SubAgent touched paths 是否越过 assigned_scope | WR-17 | todo |
| WR-19 | Coordinator 汇总规则 | 汇总多项目验证、冲突、契约、发布顺序、回滚策略 | WR-15,WR-17 | todo |
| WR-20 | 冲突检测 | 同文件修改、契约不一致、文档实现偏差、缺失验证 | WR-19 | todo |
| WR-21 | memory scope 策略 | workspace 级 summary 与子项目事实分层写入 | WR-16 | todo |
| WR-22 | before_task 集成 | 自动扫描 workspace、生成初始 route plan、加载规则 | WR-12,WR-21 | todo |
| WR-23 | after_tool 集成 | 根据 touched paths 重算 affected projects 和验证计划 | WR-22 | todo |
| WR-24 | before_response 集成 | 检查必须验证是否执行，缺失时输出 verification_gap | WR-23 | todo |
| WR-25 | 游戏客户端模板 | Unity/Laya/Cocos project rules 和 profile 示例 | WR-10 | todo |
| WR-26 | 游戏服务器模板 | Go/Java/C#/Node 服务端 rules 和 profile 示例 | WR-10 | todo |
| WR-27 | 后台/Web 模板 | 管理端、GM、运营后台 rules 和 profile 示例 | WR-10 | todo |
| WR-28 | 文档与美术工程模板 | docs/art/asset pipeline rules 和 profile 示例 | WR-10 | todo |
| WR-29 | 测试覆盖 | scanner、route planner、aggregation、scope guard 行为测试 | WR-09,WR-12,WR-15,WR-18 | todo |
| WR-30 | 发布与迁移说明 | 用户如何从普通 harness 升级到 workspace routing | WR-29 | todo |

## 5. 当前项目进度同步

当前仓库已经具备：

- `codex memory doctor/init`。
- `codex harness start/checkpoint/complete`。
- `codex harness verify run --profile primary`。
- 本地 memory、summary、distillation。
- 项目级 `.codex/harness/commands.json` 与 `project_profile.json`。
- SubAgent 角色协作协议文档。
- 游戏客户端 domain 文档。
- Workspace routing 设计文档。

当前仓库尚未具备：

- workspace scanner。
- project inventory schema。
- route plan runtime。
- SubAgent route binding runtime。
- verification aggregation runtime。
- 每个 verification command 的 project cwd 支持。
- workspace 级 memory 与子项目 memory 的自动分层。
- `codex workspace ...` 命令。

## 6. 推荐下一步

下一步优先级：

1. WR-05 到 WR-08：先定 schema，避免实现阶段反复改数据结构。
2. WR-09 到 WR-13：实现只读 scanner 和 route planner，不执行构建。
3. WR-14 到 WR-16：补 verification cwd 和聚合写回。
4. WR-17 到 WR-20：再进入 SubAgent route binding 与 coordinator 汇总。
5. WR-21 到 WR-24：最后接入 memory 生命周期。

这个顺序可以降低风险：先只读，再计划，再验证，最后才进入 SubAgent 和生命周期自动化。
