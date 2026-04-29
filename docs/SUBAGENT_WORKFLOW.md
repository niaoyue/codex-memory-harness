# SubAgent 角色分工工作流

## 1. 当前状态

当前 Codex Memory Harness 没有实现宿主级并发 SubAgent 执行器，也不会自动创建多个 agent 进程或远程 agent。

本项目当前能做的是：

- 为主任务创建 harness task。
- 为不同角色的工作结果记录 checkpoint artifact。
- 把验证结果写回同一个任务闭环。
- 从 workspace route plan 生成 SubAgent route binding。
- 从 route plan 和 bindings 生成 SubAgent dispatch plan。
- 对 SubAgent touched paths 执行 scope guard。
- 汇总多 SubAgent artifact 的冲突、verification gap、发布顺序和回滚要求。
- 在 memory 中沉淀角色产出的决策、发现和总结。

因此本文件定义的是“角色协作协议”、最小 binding runtime 和调度计划协议，不声明当前已经具备自动启动真实 SubAgent 的能力。

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
| Reviewer | 做限定 scope 的专题审查，最终代码审核仍优先交给 `codex xhigh review --uncommitted` | review findings |
| Verifier | 运行测试、打包、诊断、静态检查 | verification payload |
| Documentation Maintainer | 更新 README、用户指南、迁移说明 | docs diff、读者视角检查 |
| Security Reviewer | 检查密钥、敏感路径、网络边界、危险命令 | security findings |
| Release Manager | 过滤提交内容、生成提交说明、确认发布包边界 | commit summary、release notes |

## 4. 何时使用

建议使用 SubAgent 分工的场景：

- 同时涉及 runtime、安装器、测试和文档。
- 需要多专题辅助审查，并且最终仍由 `codex xhigh review --uncommitted` 做代码审核 gate。
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
  "summary": "发现 README 缺少 SubAgent 分工说明，建议新增文档入口。",
  "touched_paths": ["README.md", "docs/SUBAGENT_WORKFLOW.md"],
  "signals": {
    "role": "Reviewer",
    "project_id": "codex-memory-harness",
    "domain": "docs",
    "assigned_scope": ["README.md", "docs/"],
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
- findings 必须带路径或证据来源。
- implementer 只修改自己负责的文件集合。
- reviewer 不直接重写大块代码，除非被明确授权；代码变更的最终审核优先使用 `codex xhigh review --uncommitted`。
- verifier 不修改业务文件，只记录验证结果。
- documentation maintainer 必须同步 README、用户指南和迁移说明。
- release manager 必须过滤 `.codex/`、`dist/`、`__pycache__/`、数据库和日志。

## 7. 推荐执行顺序

一般任务：

1. Task Planner 明确目标、验收、工作集。
2. Implementer 完成最小变更。
3. 如需并行辅助，SubAgent Reviewer 只审自己的 route binding 或专题风险。
4. 主流程运行 `codex xhigh review --uncommitted` 作为最终代码审核 gate。
5. Implementer 修复 review findings。
6. Verifier 运行验证。
7. Documentation Maintainer 补齐文档。
8. Security Reviewer 做敏感信息和边界扫描。
9. Release Manager 准备提交说明。

大型任务可以并行：

- Architect 和 Documentation Maintainer 可先并行梳理设计与文档结构。
- Implementer 可按不重叠文件集合并行。
- Reviewer 和 Security Reviewer 可在实现完成后并行。
- Verifier 可在修复过程中反复执行，但最终结果必须写回 task。

## 8. 当前项目的落地方式

当前没有内建宿主级 SubAgent 自动执行器，所以落地方式是：

- 主 agent 使用宿主环境提供的 SubAgent 能力时，按本文件定义角色和 artifact。
- 如果宿主环境没有 SubAgent，主 agent 仍按角色清单自我检查。
- 所有角色结论通过 `codex harness checkpoint` 或最终 summary 沉淀。
- workspace 多项目任务可用 `codex workspace bind/scope-check/summarize` 生成 binding、检查越权并汇总冲突。
- 需要标准化派发顺序时，用 `codex workspace schedule --route-file route.json` 生成 dispatch plan；它描述 coordinator/specialist 的角色、scope、依赖和 prompt，但不负责启动真实 agent 进程。
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

当前第一阶段已经具备 route binding、scope guard、coordinator summary 和 dispatch plan 生成。下一阶段应补宿主级并发执行适配、超时控制、取消状态和更完整的结果合并。

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
    "required_fields": ["project_id", "domain", "assigned_scope", "touched_paths"],
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

当未来声明“已支持真实 SubAgent 自动调度”时，至少要满足：

- 有角色配置 schema。
- 有每个角色的输入、输出和责任边界。
- 有 artifact 记录和查询方式。
- 有冲突文件检测。
- 有失败/超时/取消状态。
- 能实际启动或委托宿主启动对应 SubAgent，并把 dispatch 状态回写。
- 有最终汇总规则。
- 有验证结果和安全检查结果汇聚。

在这些能力完成前，本项目只能说“支持按 SubAgent 角色协议记录协作结果，并支持 workspace route binding/scope guard/coordinator summary/dispatch plan”，不能说“已经实现真实 SubAgent 自动执行器”。
