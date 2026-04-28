# Harness Engineering 外部对标核查

## 1. 来源与读取状态

本次对标基于用户指定资料和一个补充一手来源：

| 来源 | 读取状态 | 本文使用方式 |
|---|---|---|
| 腾讯云文章：`https://cloud.tencent.com/developer/article/2649999` | 已读取 | 只提炼公开文章中的高层 Harness Engineering 观点，不复述疑似来源不明的实现细节 |
| GitHub 项目：`https://github.com/deusyu/harness-engineering` | 已读取 README | 作为 Harness Engineering 学习/实践项目参考 |
| 知乎专栏：`https://zhuanlan.zhihu.com/p/2021938778906862975` | 当前环境返回 403，无法直接核验正文 | 不把未读到的内容作为证据；需要用户提供正文或可访问镜像后再补充 |
| OpenAI 官方文章：`https://openai.com/index/harness-engineering` | 已读取 | 作为同主题一手来源，补足不可访问知乎文章带来的证据缺口 |

注意：对标只使用公开可访问资料中的工程原则，不复制大段原文，也不把任何敏感实现细节写入本仓库。

## 2. 外部资料抽象出的能力点

这些资料共同强调的不是单纯提示词，而是围绕模型构建可控工程系统：

| 能力点 | 说明 |
|---|---|
| 上下文装载 | 让模型每次开始任务时获得目标、约束、工作集、历史决策和必要证据 |
| 工具编排 | 把搜索、读写、验证、打包、诊断等行为沉淀为可复用命令 |
| 状态机 | 任务从开始、执行、验证到完成要有明确状态和产物记录 |
| 验证闭环 | 代码或文档变更后应运行项目定义的验证命令，并把结果写回任务记录 |
| 记忆沉淀 | 把任务结论、决策和可复用经验写入外部记忆，而不是依赖会话临时上下文 |
| 上下文预算 | 需要裁剪、排序和摘要，避免把无关内容直接塞给模型 |
| 角色分工 | 复杂任务可拆成 Planner、Implementer、Reviewer、Verifier、Documenter 等角色 |
| 可审计性 | 关键输入、工具调用、验证结果和最终总结应有本地 artifact |
| 安全边界 | 避免写入密钥、敏感日志、内部链接和不必要的原始数据 |

## 3. 当前实现对标结论

总体结论：当前项目已经覆盖最小可用的本地 memory/harness/verification 闭环，但还没有实现完整 SubAgent 调度器、真实语义向量召回、平台化 eval 回放和远程执行环境。缺口已经在文档中明确化，并纳入后续路线。

| 外部能力点 | 当前实现 | 状态 | 差距与处理 |
|---|---|---|---|
| 上下文装载 | `hook_runner.py`、`context_builder.py` 读取 task state、summary、decisions、evidence | 已实现 MVP | 预算固定，后续可按任务类型配置化 |
| 工具编排 | `codex memory ...`、`codex harness ...`、`codex package ...` 命令入口 | 已实现 | 底层仍是 Python 脚本，但用户入口已收敛为 Codex 风格命令 |
| 状态机 | `harness_controller.py start/checkpoint/complete` | 已实现 MVP | 当前是单任务线性状态机，不含并发 SubAgent 状态 |
| 验证闭环 | `verification_runner.py` 读取 `.codex/harness` 配置并 checkpoint | 已实现 MVP | 还不是完整 eval 平台，没有历史失败用例回放 |
| 记忆沉淀 | SQLite、JSONL、summary、distilled asset | 已实现 MVP | 缺少长期清理、归档和迁移工具 |
| 上下文预算 | `DEFAULT_CONTEXT_BUDGET` 分配 task、summary、decision、evidence 字符预算 | 已实现 MVP | 后续应支持 profile 配置 |
| 角色分工 | `docs/SUBAGENT_WORKFLOW.md` | 文档已补齐，运行时未实现 | 当前只定义协作协议，不自动创建或调度 SubAgent |
| 语义召回 | `retrieval_store.py` 保留 `semantic` placeholder | 预留接口 | 暂不依赖向量库，路线见 `docs/MEMORY_RETRIEVAL_STRATEGY.md` |
| 可审计性 | task spec、run state、artifacts、verification payload、本地 memory | 已实现 MVP | 后续可增加 artifact schema 版本和导出命令 |
| 安全边界 | 打包排除、敏感字段脱敏、危险命令拦截、隐私文档 | 已实现 MVP | 写入前敏感扫描器仍是后续增强 |
| Workspace 路由 | `docs/WORKSPACE_ADAPTIVE_ROUTING.md`、`docs/WORKSPACE_ROUTING_TASK_LIST.md` | 文档已补齐，运行时未实现 | 当前只定义 project inventory、route plan、SubAgent route binding 和验证聚合路线 |

## 4. 是否已经“都做到了”

没有全部做到。更准确的结论如下：

- 已做到：本地项目记忆、任务状态、决策记录、上下文包、harness 生命周期、验证回写、安装/更新入口、打包边界、基础隐私边界。
- 部分做到：Harness Engineering 的工程闭环已经有 MVP，但还不是成熟平台；上下文预算有固定实现，但没有 profile 化；语义检索有接口但没有向量索引。
- 之前没说清：为什么不引入向量数据库、SubAgent 怎么分工、哪些能力只是规划层而非运行时能力。
- 未做到：真实 SubAgent 调度器、并发 agent artifact 汇聚、向量数据库、embedding 索引、eval replay 平台、远程沙箱执行。

## 5. 已补齐的文档

当前已新增或更新的文档入口：

- `docs/EXTERNAL_BENCHMARK.md`：外部资料对标、已实现能力、缺口和路线。
- `docs/MEMORY_RETRIEVAL_STRATEGY.md`：解释为什么当前不依赖向量数据库，以及未来如何接入。
- `docs/SUBAGENT_WORKFLOW.md`：定义 SubAgent 角色分工、artifact 协议和未来落地路线。
- `docs/GAME_CLIENT_WORKFLOW.md`：定义 Unity、LayaBox/LayaAir、Cocos Creator 客户端专项流程。
- `docs/WORKSPACE_ADAPTIVE_ROUTING.md`：定义多项目 workspace 的自动识别、路由、SubAgent 绑定和验证聚合设计。
- `docs/WORKSPACE_ROUTING_TASK_LIST.md`：把 workspace routing 设计拆成带状态的实现任务。
- `README.md`、`docs/USER_GUIDE.md`、`docs/codex-memory-harness-system-summary.md`、`docs/codex-memory-plugin-task-list.md`：补充上述入口和状态说明。

## 6. 后续路线建议

优先级建议按风险和收益排序：

1. 先做写入前敏感信息扫描器，避免 memory、artifact 和向量索引污染。
2. 再做 eval replay，把失败任务沉淀为可回放验证集。
3. 再做 SubAgent artifact 协议的运行时支持，例如 `roles.json` 和 `subagents.jsonl`。
4. 最后接入可选向量索引，保持默认离线、默认不上传、默认可降级。

这个顺序的原因是：向量库和 SubAgent 都会放大已有信息质量问题。如果 memory 中先混入敏感数据或低质量记录，后续检索和多角色协作都会把问题扩散到更多上下文里。
