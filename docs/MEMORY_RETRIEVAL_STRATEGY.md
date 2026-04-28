# 记忆检索与向量数据库策略

## 1. 当前结论

当前 Codex Memory Harness 不依赖向量数据库，这是有意的 MVP 设计，不是遗漏。

当前记忆体系优先解决的是“任务状态可恢复、决策可追踪、验证结果可回写、上下文可控装载”。这些数据大多是结构化的、路径相关的、任务相关的，使用 SQLite、JSONL、Markdown summary 和 `rg` 检索已经能覆盖第一阶段需求。

向量数据库适合大规模语义召回，但它会引入 embedding 模型、索引维护、敏感信息治理、增量更新和可复现性问题。当前项目选择先把本地闭环做扎实，再把向量检索作为可选增强。

## 2. 当前检索结构

当前检索由四类数据组成：

| 数据层 | 存储位置 | 作用 |
|---|---|---|
| 结构化任务状态 | `.codex/memories/memory.db` | 保存当前 task state、constraints、working set、next step |
| 项目决策 | `.codex/memories/memory.db` | 保存 repo decision，供后续任务引用 |
| 任务总结 | `.codex/memories/summaries/*.md` | 保存任务完成后的总结 |
| 事件与蒸馏资产 | `.codex/memories/events.jsonl`、`distilled/` | 保存工具事件和可复用经验 |

工作区证据检索由 `retrieval_store.py` 负责：

- `exact`：文件名、路径、固定字符串、标识符检索。
- `fulltext`：对代码和文档执行全文检索。
- `auto`：合并路径、精确内容和全文结果。
- `semantic`：当前是占位接口，明确返回不可用。

上下文装配由 `context_builder.py` 负责：

- 优先放入当前任务状态。
- 再放入任务总结。
- 再放入项目决策。
- 最后按预算加入 evidence。

## 3. 为什么不先上向量数据库

主要原因如下：

| 原因 | 解释 |
|---|---|
| 安装复杂度 | 本项目是本地分发工具，默认应能离线安装和运行 |
| 安全边界 | embedding 前必须先解决密钥、日志、内部链接、PII 的过滤问题 |
| 可审计性 | 关键词、路径和结构化状态更容易解释“为什么召回这条证据” |
| 可复现性 | 不同 embedding 模型和索引参数会导致召回结果漂移 |
| 当前数据形态 | 任务状态、文件路径、命令结果、验证摘要天然适合结构化和全文检索 |
| 代码任务特性 | 编码任务经常依赖精确符号、文件名、错误信息，向量相似度不一定更可靠 |
| 依赖边界 | 不希望用户为了基础 memory 能力安装数据库服务或提供外部 API key |

因此当前策略是：

- 默认检索必须本地、透明、可审计。
- 语义检索只作为可选 provider。
- provider 不可用时必须无损降级到 exact/fulltext。

## 4. 当前方案的局限

不依赖向量库也有明确局限：

- 用户用自然语言描述“之前那个安装器旧版本处理问题”时，关键词不命中就可能漏召回。
- 跨项目、跨时间的大量总结会越来越难靠路径和关键词检索。
- 同义词、概念迁移、架构主题检索不够强。
- 没有 rerank，无法综合语义相关性、时间、任务重要性和文件权重。

这些局限不是要忽略，而是应在安全和可控基础打稳后解决。

## 5. 何时引入向量检索

建议满足以下条件后再引入：

- 写入前敏感信息扫描已经落地。
- memory archive/cleanup 已经落地，能控制索引规模。
- 每条可索引内容都有来源、时间、scope、task_id 和可删除标识。
- 有清晰的 rebuild/reindex 命令。
- 检索结果能解释来源，不能只返回相似度分数。
- 默认关闭，用户显式启用。

适合启用向量检索的场景：

- 项目 memory 已有大量历史 summary 和 decision。
- 用户经常用自然语言追问历史上下文。
- 团队希望沉淀跨项目工程模式。
- 需要检索“类似问题怎么处理过”而不是只查某个文件名。

## 6. 推荐未来设计

未来可以把检索拆成 provider：

```text
RetrievalProvider
  - ExactProvider        当前 rg 路径/精确检索
  - FullTextProvider     当前 rg 全文检索
  - MemorySqlProvider    SQLite task/decision/summary 检索
  - SemanticProvider     可选向量检索
```

语义 provider 的最低要求：

- 默认禁用。
- 本地索引优先。
- 支持全量重建和增量更新。
- 支持删除某个 task_id 或 scope 的索引。
- 索引前执行敏感信息过滤。
- 召回结果必须带原始文件、task_id、时间和片段来源。
- provider 失败时返回结构化降级原因，不阻断基础检索。

可选存储方向：

| 方向 | 适合场景 | 注意事项 |
|---|---|---|
| SQLite 扩展类向量索引 | 继续保持单文件、本地、低运维 | 需要处理扩展安装兼容性 |
| 本地轻量向量库 | 单机项目知识库 | 需要额外依赖和索引目录管理 |
| 独立向量服务 | 团队级共享知识库 | 必须解决权限、脱敏、网络和删除策略 |

## 7. 命令路线

未来命令可以保持 Codex 风格入口：

```powershell
codex memory index status
codex memory index rebuild
codex memory index update --task-id <task-id>
codex memory search --semantic "之前安装器旧版本怎么处理"
```

默认行为：

- 没有启用向量检索时，`--semantic` 返回明确的不可用原因。
- exact/fulltext 永远可用。
- 索引目录不进入发布包。
- 索引内容不跨项目自动共享。

## 8. 当前落点

当前代码中 `retrieval_store.py` 已保留 `semantic` 模式，但明确返回：

```text
Semantic retrieval is not implemented in the local MVP.
```

这条状态应继续保留，直到真正完成 provider、索引、安全过滤和验证闭环。文档上需要明确：当前没有向量数据库，是为了先保证本地、可审计、低依赖和安全默认值。
