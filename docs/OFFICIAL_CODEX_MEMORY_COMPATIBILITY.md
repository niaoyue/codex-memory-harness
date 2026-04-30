# 官方 Codex Memories 兼容策略

## 1. 结论

官方 Codex Memories、Chronicle 和本项目的 Memory/Harness 不应互相替代。推荐职责边界如下：

| 层级 | 位置或来源 | 作用 |
|---|---|---|
| 官方 Codex Memories | `$CODEX_HOME/memories`，默认通常是 `~/.codex/memories` | Codex 官方自动生成的个人长期记忆 |
| Chronicle | 官方 Codex 的个人活动上下文预览能力 | 补充用户近期看过的 app、网页和文档上下文 |
| Harness 用户全局层 | `$CODEX_HOME/codex-memory-harness/memories` | 本插件跨项目偏好、长期通用流程和用户明确要求沉淀的非敏感规则 |
| Harness 项目私有层 | `<项目根目录>/.codex/memories` | 当前项目本机任务状态、checkpoint、验证摘要和蒸馏草稿 |
| Harness 项目共享层 | `<项目根目录>/.codex/shared` | 团队确认的项目事实、架构决策、流程和路由摘要 |
| 强规则层 | `AGENTS.md`、项目文档、`.codex/harness/*.json` | 必须遵守的规则、验证配置和团队约束 |

因此本项目不再把自研用户全局 memory 写入 `~/.codex/memories`。该目录保留给官方 Codex Memories，避免 SQLite、JSONL、summary 和官方自动 Markdown 混在一起。

## 2. 官方能力边界

官方 Codex Memories 适合保存个人偏好、轻量习惯和自动提炼的长期上下文。它不是强规则系统，也不应承载团队必须遵守的规范。

Chronicle 适合提供用户近期工作上下文。它不是项目事实来源，也不能直接替代项目共享记忆。任何从 Chronicle 或官方 Memories 得到的项目结论，如果要进入团队共享层，必须经过脱敏、验证和 review。

官方参考：

- `https://developers.openai.com/codex/memories`
- `https://developers.openai.com/codex/memories/chronicle`
- `https://developers.openai.com/codex/concepts/customization`
- `https://developers.openai.com/codex/config-reference`

## 3. 优先级

当多个来源给出冲突信息时，按以下顺序处理：

1. 用户本次明确要求。
2. 安全策略、敏感信息策略和危险命令禁令。
3. 项目 `AGENTS.md`、仓库文档和 `.codex/harness` 配置。
4. `.codex/shared` 中 `accepted` 且 `medium/high` confidence 的团队共享事实。
5. 当前 harness task state、route plan、checkpoint 和 verification artifact。
6. 项目私有 `.codex/memories` 中的本地 summary、decision 和 distilled asset。
7. 官方 Codex Memories 与 Harness 用户全局层中的个人偏好。
8. 低置信度草稿、旧 summary、未验证 SubAgent 发现。

自动生成的 memory 不能覆盖强规则、当前用户要求或已 review 的项目共享事实。

## 4. Doctor 只读检测

`codex memory doctor` 会只读报告官方兼容状态：

- `$CODEX_HOME/config.toml` 是否存在，是否能解析。
- `features.memories` 总开关是否显式启用。
- `memories.generate_memories` 是否显式配置；总开关启用时，该项缺省按 Codex 默认值视为启用，只有显式 `false` 才报告生成输入关闭。
- `memories.use_memories` 是否显式配置；总开关启用时，该项缺省按 Codex 默认值视为启用，只有显式 `false` 才报告读取注入关闭。
- 官方 `$CODEX_HOME/memories` 是否存在。
- Harness 全局 memory 目录 `$CODEX_HOME/codex-memory-harness/memories` 是否存在。
- 旧版 harness runtime 标记是否仍出现在官方 memories 目录。
- Chronicle 相关本地临时目录是否存在；只报告目录状态，不读取内容。

Doctor 不会自动开启官方 Memories，不会读取官方 memory 文件内容，不会迁移或删除官方目录内容。

## 5. 迁移策略

从旧版本升级后，如果 `codex memory doctor` 发现 `$CODEX_HOME/memories` 下存在 `memory.db`、`events.jsonl`、`summaries/` 或 `distilled/`，说明旧版可能把 Harness 全局运行态写到了官方目录。

默认策略是：

- 不自动迁移，避免误动官方自动记忆。
- 新写入使用 `$CODEX_HOME/codex-memory-harness/memories`。
- 用户确认旧目录只包含 Harness 运行态后，可手动迁移需要保留的文件。
- 项目私有层 `<项目根目录>/.codex/memories` 不受影响。

## 6. 不引入向量库的关系

官方 Memories 使用本地文件记忆，并不要求向量数据库。本项目继续保持 exact/fulltext/SQLite/Markdown 的可审计检索作为默认能力。语义检索仍是未来可选 provider，必须默认关闭、可重建、可删除、可解释来源，并在索引前执行敏感信息过滤。
