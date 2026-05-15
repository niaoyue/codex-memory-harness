# SubAgent 角色分工工作流

## 1. 当前状态

当前 Codex Memory Harness 不内建独立的 SubAgent 子进程执行器。正式执行通道是主 agent 读取 dispatch plan 后使用 Codex 宿主提供的 SubAgent 能力。

本项目当前能做的是：

- 为主任务创建 harness task。
- 为不同角色的工作结果记录 checkpoint artifact。
- 把验证结果写回同一个任务闭环。
- 从 workspace route plan 生成 SubAgent route binding。
- 从 route plan 和 bindings 生成 SubAgent dispatch plan 与 `host_spawn_requests`。
- 对 SubAgent touched paths 执行 scope guard。
- 汇总多 SubAgent artifact 的冲突、verification gap、发布顺序和回滚要求。
- 在 memory 中沉淀角色产出的决策、发现和总结。

因此本文件定义的是“角色协作协议”、最小 binding runtime 和调度计划协议。它声明的边界是：插件不自行启动子进程，但主 agent 可以按计划派发 Codex SubAgent。

当用户明确选择 SubAgent、分角色或并行代理，任务属于复杂/应用级/多阶段实现，或项目持久化 `subagent_runtime_policy` 授权当前 route 时，主 agent 必须消费 lifecycle 写入的 `metadata.workspace_routing.subagent_dispatch_plan.host_spawn_requests` 来派发 Codex SubAgent。这个动作发生在主 agent 和 Codex 宿主运行时之间，不是 Python 插件自行启动子进程或远程 agent。

项目或全局 `AGENTS.md` 中的 SubAgent 规则是用户级长期明确授权。只要 runtime 写出 `host_dispatch_allowed=true` 或 `dispatch_required=true`，且 `host_spawn_requests` 非空，就应视为用户已经明确要求使用指定 role 的 SubAgent；主 agent 不应再因为当前 prompt 没有重复写“使用 SubAgent”而降级或要求确认。

所有 SubAgent 都不得设置固定总时长。Codex SubAgent 的观察窗口、`wait_agent` 类观察参数或命令执行器 timeout 只能作为单次观察窗口；窗口到期后继续观察或读取最新输出，不得仅因观察窗口到期就中断、关闭或判失败。只要 SubAgent 有 stdout/stderr、checkpoint、状态更新或其他可见进度，就视为仍在运行。

## 2. 为什么需要 SubAgent 分工

Harness Engineering 的核心不是让一个 agent 直接做完所有事情，而是把复杂任务拆成可验证、可审计、可并行的工程流程。

复杂任务里至少存在这些不同心智负载：

- 设计目标与边界。
- 修改代码或文档。
- 找 bug 和回归风险。
- 运行验证并解释失败。
- 维护用户文档和迁移说明。
- 检查敏感信息、安全边界和发布包内容。

这些工作由同一个上下文连续完成时，容易发生遗漏。角色分工可以降低遗漏，但必须通过 harness artifact 汇聚证据，不能只依赖口头总结。

## 3. 推荐角色

| 角色 | 职责 | 典型产物 |
|---|---|---|
| Task Planner | 拆解目标、明确验收、划定最小变更边界 | task spec、工作集、风险清单 |
| Architect | 判断模块边界、接口方向、是否需要颠覆性调整 | 设计说明、取舍记录 |
| Implementer | 修改代码、脚本、文档或配置 | patch、变更摘要 |
| Reviewer | 做限定 scope 的专题审查；不得替代 Codex CLI xhigh review | review findings |
| XHigh Review Runner | 作为并行命令执行器运行 commit-based 的 `codex xhigh review --commit <commit-sha>`，必要时降级到 `codex-raw -- review -c model_reasoning_effort="xhigh" --commit <commit-sha>` | xhigh review 结果、失败原因 |
| Verifier | 运行测试、打包、诊断、静态检查 | verification payload |
| Documentation Maintainer | 更新 README、用户指南、迁移说明 | docs diff、读者视角检查 |
| Security Reviewer | 检查密钥、敏感路径、网络边界、危险命令 | security findings |
| Release Manager | 过滤提交内容、生成提交说明、确认发布包边界 | commit summary、release notes |

## 4. 何时使用

建议使用 SubAgent 分工的场景：

- 生成完整应用、网站、管理后台、仿制产品体验或端到端功能流程，即使 route plan 只命中一个项目。
- 同时涉及 runtime、安装器、测试和文档。
- 需要多专题辅助审查，并且最终仍由 Codex CLI 的 `codex xhigh review --commit <commit-sha>` 审核被审提交。
- 大 diff 或耗时审查场景，需要让 SubAgent 并行运行 xhigh review，主 agent 同时跑测试、编译、diff check 或敏感扫描。
- 需要外部资料对标、架构判断和落地修改。
- 需要跨文件批量重构。
- 需要安全或发布包边界核查。

不建议使用的场景：

- 单文件小修。
- 直接回答概念问题。
- 当前任务上下文太少，角色拆分会制造沟通成本。
- 变更强耦合，多个 agent 容易改同一文件导致冲突。

## 5. 与 Harness 的协作协议

建议主 agent 负责创建和关闭任务：

```powershell
codex harness start --task-file task.json
```

每个角色完成工作后，把结果作为 checkpoint 写入同一个 task：

```powershell
codex harness checkpoint --task-id <task-id> --result-file role-result.json
```

推荐 `role-result.json` 结构：

```json
{
  "tool_name": "subagent:reviewer",
  "phase": "review",
  "dispatch_id": "dispatch-binding-docs-review",
  "binding_id": "binding-docs-review",
  "subagent_id": "agent-docs-review",
  "project_id": "codex-memory-harness",
  "domain": "docs",
  "assigned_scope": ["README.md", "docs/"],
  "summary": "发现 README 缺少 SubAgent 分工说明，建议新增文档入口。",
  "touched_paths": ["README.md", "docs/SUBAGENT_WORKFLOW.md"],
  "signals": {
    "role": "Reviewer",
    "status": "findings",
    "findings": [
      {
        "severity": "medium",
        "path": "README.md",
        "summary": "文档没有说明多角色协作边界。"
      }
    ]
  },
  "next_step": "由 Documentation Maintainer 补齐文档入口"
}
```

Verifier 角色应通过配置化验证入口产生 artifact：

```powershell
codex harness verify run --task-id <task-id> --profile primary
```

任务完成时由主 agent 汇总：

```powershell
codex harness complete --task-id <task-id> --summary-file summary.md
```

## 6. 角色输出规则

角色输出必须满足这些规则：

- 只写和任务相关的最小事实。
- 不写密钥、令牌、内部链接、原始敏感日志。
- checkpoint 必须把 `dispatch_id`、`binding_id`、`subagent_id`、`project_id`、`domain`、`assigned_scope` 和 touched paths 放在顶层字段，便于 Harness lifecycle 归因和 mandatory dispatch gate 校验。
- findings 必须带路径或证据来源。
- implementer 只修改自己负责的文件集合。
- reviewer 不直接重写大块代码，除非被明确授权；代码变更的最终审核优先使用 Codex CLI 的 `codex xhigh review --commit <commit-sha>` 审核被审提交。
- XHigh Review Runner 不自行发散审查、不修改文件，只负责执行 xhigh review 命令、记录退出状态和关键 findings。
- verifier 不修改业务文件，只记录验证结果。
- documentation maintainer 必须同步 README、用户指南和迁移说明。
- release manager 必须过滤 `.codex/`、`dist/`、`__pycache__/`、数据库和日志。

## 7. 推荐执行顺序

一般任务：

1. Task Planner 明确目标、验收、工作集。
2. Implementer 完成最小变更。
3. 如需并行辅助，SubAgent Reviewer 只审自己的 route binding 或专题风险。
4. Verifier 运行验证。
5. Release Manager 创建只包含本轮相关文件的本地 candidate commit，并记录被审提交 SHA。
6. 主流程运行 `codex xhigh review --commit <commit-sha>` 审核该提交引入的变更；大 diff 时优先派发 XHigh Review Runner SubAgent 并行执行该命令。
7. Implementer 修复 review findings。
8. Documentation Maintainer 补齐文档。
9. Security Reviewer 做敏感信息和边界扫描。
10. 如有阻断 findings，修复后创建新的本地提交或在未 push 前重做候选提交，并重新 review 最新提交；无新阻断问题后才允许 push。

大型任务可以并行：

- Architect 和 Documentation Maintainer 可先并行梳理设计与文档结构。
- Implementer 可按不重叠文件集合并行。
- Reviewer 和 Security Reviewer 可在实现完成后并行。
- XHigh Review Runner 可在 diff 稳定后并行运行；它只运行 Codex CLI review，不替代专题 Reviewer。等待策略应监控 stdout/stderr 和状态进度；持续有输出时不因总耗时失败，也不得再套任何固定总时长。
- Verifier 可在修复过程中反复执行，但最终结果必须写回 task。

## 7.1 SubAgent 执行 xhigh review

当当前 Codex 会话支持 SubAgent 时，推荐把耗时的最终代码审核派发给单独的 XHigh Review Runner。这个角色不是“让另一个通用模型自己审查代码”，而是让它作为命令执行器运行 Codex CLI 的 xhigh review gate。

推荐指令：

```text
只执行代码审核命令，不修改文件、不提交、不 push。
在仓库根目录运行 codex xhigh review --commit <commit-sha>。
如果 wrapper 不稳定，降级运行 codex-raw -- review -c model_reasoning_effort="xhigh" --commit <commit-sha>。
监控 stdout/stderr 输出和状态进度；持续输出说明仍在分析，不按固定总时长失败。
不要把 runner 放进任何固定总时长的外层执行器；如果宿主工具必须设置等待窗口，该窗口只用于分段观察，到期后继续观察，不能作为 review gate 的语义超时。
返回退出码、是否有 findings、关键 findings 摘要和降级原因。
```

主 agent 在 SubAgent 运行期间可以并行执行这些不改变 diff 的验证：

- `git diff --check`
- 项目 quick/unit/compile 验证
- 敏感信息扫描
- 打包边界检查

如果 XHigh Review Runner 遇到模型容量、429、5xx 或超时类基础设施错误，恢复顺序是先续跑、后重开。主 agent 或宿主仍持有活跃 runner session 时，应按故障类型退避后对同一 session 发送继续指令，让它复用已有 transcript、审查进度和已读上下文：容量/429 退避 20 秒且只要 session 活跃就可继续，5xx/超时退避 2 秒且最多续跑一次。只有 runner session 已关闭、无句柄、不可恢复，或 review 期间 diff 已变化时，才重新启动同一个 review gate。无论续跑还是重开，只要 xhigh review 没有完整返回 clean 或 findings，就不能视为通过。

如果 xhigh review 返回 findings，主 agent 修复后必须创建新的本地提交或在未 push 前重做候选提交，再 review 新提交本身，直到没有新的阻断问题。当前 Codex 会话无法派发 SubAgent、runner idle timeout 或 wrapper 失败时，必须记录失败原因，并由主 agent 直接运行 `codex-raw -- review -c model_reasoning_effort="xhigh" --commit <commit-sha>` 或原生 Codex review 命令兜底。

candidate commit 只应包含本轮相关文件；如果工作树里混有用户无关改动，必须先隔离提交范围，无法安全隔离时在最终答复说明未提交原因。每个候选提交或修复提交 review 无新阻断问题后才允许 push。

## 8. 当前项目的落地方式

当前落地方式是使用 Codex SubAgent 作为执行通道，同时保持插件侧只负责计划、scope guard 和 receipt 汇总：

- 主 agent 使用当前 Codex 会话提供的 SubAgent 能力时，按本文件定义角色和 artifact。
- lifecycle 会在显式、route policy、复杂/应用级任务、xhigh review gate 或通用自动判断命中时写入 `subagent_runtime` 和 `subagent_dispatch_plan`。`route policy` 可来自 `.codex/harness/project_profile.json` 或 `.codex/harness/workspace-routing.json` 的 `subagent_runtime_policy`，用于把正式 implementation 任务的授权持久化。通用 planner 会综合 `task_intent`、`task_type`、`risk_level`、route 数量、scope 大小、复杂度和 review gate：功能 story、系统改动、发布 gate、高风险或复杂应用级任务会允许派发；普通低风险小修仍保持主 Agent 串行。只有当 `subagent_runtime.host_dispatch_allowed=true` 时，主 agent 才应按 `host_spawn_requests` 调用当前 Codex SubAgent 能力；推荐但未允许派发时只记录计划，等待用户选择、项目 policy 授权或当前 Codex 会话允许派发。
- 每个 `host_spawn_requests` 都必须带 `standing_user_authorization=true`、`specified_role_subagent_required=true` 和指定 role 的 `agent_type`。标准映射是：specialist 使用 `Implementation Specialist`，coordinator 使用 `Workspace Coordinator`，专题 reviewer 使用 `Route Review Specialist`，最终 review gate runner 使用 `XHigh Review Runner`。`worker` / `default` 只能作为宿主缺少 custom agent 的降级形态，并必须写明降级原因。
- review gate 任务优先级高于普通 `subagent_runtime_policy`。即使仓库要求 implementation/docs/release 任务强制 SubAgent，命中 `codex xhigh review --commit <commit-sha>` 的最终审核任务也必须派发 `XHigh Review Runner`，不能被改路由为 `Implementation Specialist`。
- 当 planner 判定实现任务需要旁路审查时，dispatch plan 会在 route specialist 之外加入 `Route Review Specialist`。它只做限定 scope 的风险和测试覆盖审查，不替代最终 commit-based 的 `codex xhigh review --commit <commit-sha>` gate。
- 如果 Codex SubAgent 调用失败或 scope 冲突，主 agent 必须记录降级原因，并按同一个 dispatch plan 串行执行或回到普通主 Agent 流程。
- 主 agent 可以派发 XHigh Review Runner 执行 `codex xhigh review --commit <commit-sha>`；这属于使用 Codex SubAgent 能力，不代表本仓库内建了独立执行器。
- 所有角色结论通过 `codex harness checkpoint` 或最终 summary 沉淀。
- workspace 多项目任务可用 `codex workspace bind/scope-check/summarize` 生成 binding、检查越权并汇总冲突。
- 需要标准化派发顺序时，用 `codex workspace schedule --route-file route.json` 生成 dispatch plan；它描述 coordinator/specialist 的角色、scope、依赖和 prompt，并由主 agent 将 `host_spawn_requests` 映射到 Codex SubAgent。
- lifecycle 会在 `workspace_routing.subagent_runtime` 记录实际运行决策，例如 `main_agent_serial`、`recommended_not_started`、`requested_not_started` 或 `artifact_recorded`；该字段说明 route binding 是否只是计划、是否建议宿主 SubAgent、以及为什么没有自动启动。
- 文档必须明确哪些是“已实现运行时能力”，哪些是“推荐协作协议”。

## 9. 未来运行时路线

后续可以在现有 workspace binding runtime 之上增加这些角色文件和命令：

```text
.codex/harness/roles.json
.codex/harness/tasks/<task-id>/subagents.jsonl
```

可能命令：

```powershell
codex harness roles list
codex harness roles plan --task-id <task-id>
codex harness roles record --task-id <task-id> --role Reviewer --result-file result.json
```

当前第一阶段已经具备 route binding、scope guard、coordinator summary、dispatch plan 生成和 Codex SubAgent receipt dogfood。下一阶段应补更完整的观察记录、取消状态和结果合并。

## 10. Workspace 路由绑定

当 Codex 运行在一个包含多个子项目的 workspace 中，SubAgent 还需要绑定具体项目路由。不要只按“Reviewer / Implementer”区分角色，还要记录它负责的 project、domain 和 scope。

推荐 route binding：

```json
{
  "version": 1,
  "task_id": "fix-login-flow",
  "route_plan_id": "route-fix-login-flow",
  "binding_id": "binding-client-ui-review",
  "subagent_id": "agent-client-ui-review",
  "role": "Reviewer",
  "binding_mode": "specialist",
  "route_id": "client-unity-ui",
  "project_id": "client-unity",
  "domain": "game_client",
  "cwd": "client",
  "assigned_scope": ["client/Assets/Scripts/UI"],
  "denied_scope": ["server", "admin"],
  "rules": ["workspace/base", "game_client/unity", "game_client/ui"],
  "verification_profile_ids": ["client_quick", "client_ui_smoke"],
  "memory_binding": {
    "storage_scope": "project",
    "semantic_scope": "project",
    "project_id": "client-unity",
    "write_summary": true
  },
  "artifact_policy": {
    "required_fields": ["dispatch_id", "binding_id", "subagent_id", "project_id", "domain", "assigned_scope", "touched_paths"],
    "forbid_raw_sensitive_output": true,
    "checkpoint_required": true
  },
  "scope_guard": {
    "enabled": true,
    "on_violation": "report_cross_project_dependency"
  }
}
```

综合事务应由 coordinator 管理多个 route binding，并汇总各项目 artifact。完整 workspace 路由设计见：

```text
docs/WORKSPACE_ADAPTIVE_ROUTING.md
```

## 11. 验收标准

当声明“已支持 Codex SubAgent 派发闭环”时，至少要满足：

- 有角色配置 schema。
- 有每个角色的输入、输出和责任边界。
- 有 artifact 记录和查询方式。
- 有冲突文件检测。
- 有失败/超时/取消状态。
- 能由主 agent 按 `host_spawn_requests` 派发 Codex SubAgent，并把 dispatch 状态回写。
- 有最终汇总规则。
- 有验证结果和安全检查结果汇聚。

本项目可以说“支持按 SubAgent 角色协议记录协作结果，并支持 workspace route binding/scope guard/coordinator summary/dispatch plan/Codex SubAgent receipt”。不能说“插件内建了独立 SubAgent 子进程执行器”。
