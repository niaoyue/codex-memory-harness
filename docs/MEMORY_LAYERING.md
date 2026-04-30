# Codex Memory 分层策略

## 1. 总体结论

Codex Memory Harness 的自研 memory 应分成三层，并与官方 Codex Memories 并存：

| 层级 | 位置 | 是否提交 | 作用 |
|---|---|---|---|
| 官方 Codex Memories | `$CODEX_HOME/memories` | 不提交 | 官方自动生成的个人长期记忆；不写入本插件 SQLite/JSONL 运行态 |
| 用户全局层 | `$CODEX_HOME/codex-memory-harness/memories` | 不提交 | 当前用户跨项目复用的偏好、通用工作流和长期规则 |
| 项目私有层 | `<项目根目录>/.codex/memories` | 不提交 | 当前项目的本地任务状态、运行日志、summary、distilled 草稿 |
| 项目共享层 | `<项目根目录>/.codex/shared` | 可提交，需审查 | 团队共享的稳定项目事实、决策、流程和路由规则摘要 |

注意：`$CODEX_HOME/memories` 保留给官方 Codex Memories。Harness 用户全局层使用 `$CODEX_HOME/codex-memory-harness/memories`，避免和官方自动生成的 Markdown 记忆混合。

## 2. 用户全局层

位置：

```text
$CODEX_HOME/codex-memory-harness/memories
```

适合写入：

- 用户长期偏好，例如输出语言、常用检查顺序、常用命令风格。
- 跨项目通用规则，例如优先使用 `codex memory doctor`、`codex package verify`。
- 与具体业务无关的工作流习惯，例如提交前先做敏感扫描。
- 用户明确要求全局沉淀的非敏感经验。

不应写入：

- 某个业务项目的内部架构、接口、生产地址或私有仓库信息。
- 密钥、令牌、cookie、账号、密码。
- 某个项目的临时任务状态、构建日志、运行失败详情。
- 团队需要共同审查的正式项目决策。

读取策略：

- 所有项目都可以读取这一层，但只作为用户偏好和通用约束。
- 如果全局层和项目规则冲突，项目规则优先。
- 如果用户本次明确要求不同做法，用户本次要求优先。

## 3. 项目私有层

位置：

```text
<项目根目录>/.codex/memories
```

适合写入：

- 当前任务状态：objective、constraints、working set、next step。
- 工具执行摘要、验证结果摘要、失败原因和下一步。
- 本地 task summary、distilled asset、recent findings。
- 低置信度判断、临时假设、未审查的 agent 发现。
- 个人工作机相关的路径、窗口状态和运行态信息。

不应直接提交的原因：

- `memory.db` 是 SQLite，Git 无法可靠合并。
- `events.jsonl` 是高频追加日志，多成员同时写入会频繁冲突。
- summary 和 distilled 可能包含低置信结论、临时路径或敏感摘要。
- raw memory 自动装载后会放大错误结论和记忆污染。

读取策略：

- 默认只给当前项目和当前用户使用。
- 可以作为候选材料，但不能直接当作团队事实。
- 需要共享时，必须先提升到项目共享层。

## 4. 项目共享层

建议位置：

```text
<项目根目录>/.codex/shared
```

适合写入：

- 已确认的项目架构决策。
- 模块边界、目录规则、代码所有权和禁区。
- workspace routing 的稳定项目清单、domain、scope 摘要。
- 客户端、服务器、后台之间的跨项目契约。
- 验证 profile 的说明、发布流程、回滚策略。
- 经 review 的坑点、迁移说明和可复用修复模式。

不应写入：

- raw task state、raw artifacts、完整事件日志。
- 密钥、令牌、生产域名、私有仓库地址。
- 原始构建日志、原始策划表、原始美术资产。
- 低置信度判断或只有个人环境成立的结论。

推荐结构：

```text
.codex/shared/
  decisions/
  facts/
  workflows/
  routes/
  glossary.md
```

推荐每条共享记忆一个文件，不把所有项目知识堆进一个大文件：

```text
.codex/shared/decisions/20260428-client-login-contract-v2.md
.codex/shared/facts/unity-ui-state-boundary.md
.codex/shared/workflows/client-release-check.md
```

## 5. 共享记忆格式

共享记忆应使用可审查的 Markdown，并带 front matter：

```markdown
---
id: 20260428-client-login-contract-v2
scope: project
project_id: client-unity
domain: game_client
status: accepted
confidence: high
source: verified-on-main
supersedes: 20260420-client-login-contract-v1
updated_at: 2026-04-28
---

# Client Login Contract

客户端登录请求字段、错误码和重试策略以接口文档为准。UI 层不得直接拼接协议字段。

## Applies To

- `client/Assets/Scripts/Login/**`
- `server/proto/login.proto`

## Verification

- `client_quick`
- `server_contract`
```

最低 metadata：

| 字段 | 说明 |
|---|---|
| `id` | 稳定唯一 ID |
| `scope` | `workspace`、`project`、`module` 或 `workflow` |
| `project_id` | 子项目 ID，workspace 级记忆可为空 |
| `domain` | `game_client`、`game_server`、`backoffice_web` 等 |
| `status` | `proposed`、`accepted`、`deprecated` |
| `confidence` | `low`、`medium`、`high` |
| `source` | PR、issue、验证来源或人工确认来源 |
| `supersedes` | 被替代的旧记忆 ID |
| `updated_at` | 更新时间 |

默认只自动装载 `accepted` 且 `confidence` 为 `medium` 或 `high` 的共享记忆。`proposed` 只能作为参考。

## 6. 冲突处理

项目共享层要避免多人修改同一个大文件。

推荐策略：

- 每条记忆一个文件。
- 文件名包含日期、领域和短标题。
- 修改旧结论时新增文件，并用 `supersedes` 指向旧文件。
- 旧文件改为 `deprecated`，不要直接删除历史。
- 索引文件如果存在，应由命令生成，冲突时重新生成。
- 合并前做 schema、敏感信息和引用完整性检查。

不同数据的处理方式：

| 数据 | 策略 |
|---|---|
| `$CODEX_HOME/memories` | 官方 Codex Memories，本机私有，不提交，不写入 Harness runtime |
| `$CODEX_HOME/codex-memory-harness/memories` | Harness 用户全局层，本机私有，不提交 |
| `.codex/memories/memory.db` | 项目私有 raw memory，不提交 |
| `.codex/memories/events.jsonl` | 项目私有事件流，不提交 |
| `.codex/harness/tasks/**` | 项目私有运行态，不提交 |
| `.codex/harness/*.json` | 可作为项目配置提交，需 review |
| `.codex/shared/**/*.md` | 可提交，按 PR review 和 schema 校验 |
| `.codex/shared/index.json` | 建议生成，冲突时重建 |

## 7. 提升流程

项目私有层中的内容不能自动变成团队事实。推荐后续提供提升命令：

```powershell
codex memory promote --task-id <task-id> --to shared
codex memory shared validate
codex memory shared index rebuild
```

建议流程：

1. 本地任务完成后写入 `.codex/memories`。
2. agent 从 summary、decision、verification 中提取候选共享记忆。
3. 执行敏感信息扫描和 schema 校验。
4. 生成 `.codex/shared/**/*.md`。
5. 通过 Git PR review。
6. 合并后团队成员自动读取项目共享层。

## 8. 当前实现状态

当前已经实现：

- 官方 Codex Memories 兼容检测：只读报告 `$CODEX_HOME/memories`、`features.memories` 总开关、`memories.generate_memories` 和 `memories.use_memories` 状态；总开关启用时，未配置的读写子开关按 Codex 默认启用处理。
- 用户全局层：`$CODEX_HOME/codex-memory-harness/memories`。
- 项目私有层：`<项目根目录>/.codex/memories`。
- 全局/项目 memory scope 隔离。
- `.codex/shared` 初始化模板：`README.md`、`index.json`、`decisions/`、`facts/`、`workflows/`、`routes/`。
- `.gitignore` 对 `.codex/shared` 做精细放行，同时继续忽略 raw memory、runtime task、数据库和事件流。
- `codex memory promote --task-id <task-id> --kind fact`。
- `codex memory shared validate`。
- `codex memory shared index rebuild`。

当前尚未实现：

- 严格 JSON Schema front matter 校验。
- 自动 PR review 或多人冲突解决。

因此当前默认策略仍是保守的：不提交 raw `.codex` 运行态，不把 Harness 全局运行态写进官方 Codex Memories 目录。项目共享层已经具备最小 promote/validate/index 能力，下一步是更严格的 schema 校验和协作冲突处理。
