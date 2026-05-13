# 技能路由与默认开发治理

## 1. 目的

本文把“什么时候必须优先使用技能”“需求和技术选择怎么审”“拆成多任务时怎么并行”和“哪些技能需要随包安装”固化成默认规则。

这些规则面向所有使用 Codex Memory Harness 的项目。项目自己的 `AGENTS.md`、`.codex/harness/project_profile.json` 或 workspace routing 配置可以收紧规则，但不应弱化安全、需求完整性、验证和最终 review gate。

## 2. Skill-First 入口规则

每个任务开始时，主 Agent 先做一次技能匹配：

1. 读取用户请求、working set、任务类型、风险等级和现有 route plan。
2. 按本文的技能场景表选择可用技能。
3. 如果技能能直接回答或补齐信息，先由 Agent 自行阅读代码、文档和配置后补齐。
4. 如果技能流程要求提问，而且问题不能通过本地上下文可靠回答，才把问题反馈给用户。
5. 任务继续执行前，把已使用技能、未使用但匹配的技能和跳过原因写入 checkpoint 或最终简报。

不能只口头说“这里应该用技能”。如果技能选择会长期影响后续任务，必须写回治理文档、任务清单或项目规则。

## 3. 可用技能场景表

| 技能 | 默认触发场景 | 分发状态 | 使用要求 |
|---|---|---|---|
| `grill-me` | 需求、方案、策划文档存在不确定、逻辑跳跃、隐含验收或冲突时 | 已随包 | 先自查代码和文档；能自答的补进需求，不能自答的形成问题清单给用户 |
| `design-an-interface` | 创建 API、模块接口、插件协议、schema、CLI 命令或跨模块契约前 | 已随包 | 先产出至少两个差异明显的接口方向；对高风险接口用并行 SubAgent 生成不同设计 |
| `write-a-prd` | 从想法或业务目标生成完整 PRD | 已随包 | 用于产品/策划需求成型，不替代 Requirements Integrity Gate |
| `prd-to-plan` | PRD 已存在，需要拆实施阶段和 tracer bullet | 已随包 | 产出阶段计划后再进入任务清单 |
| `prd-to-issues` | PRD 需要拆成 GitHub issues 或本地 issue 草稿 | 已随包 | 只在用户要求 issue 化或团队协作时触发 |
| `request-refactor-plan` | 大重构、模块边界调整、需要小提交序列 | 已随包 | 先形成 RFC 或本地计划，再执行改动 |
| `triage-issue` | 用户报告 bug、异常或需要 root cause | 已随包 | 先只读定位根因，再决定是否修复 |
| `tdd` | 用户要求 TDD、测试先行，或风险高的 bugfix/核心逻辑变更 | 已随包 | 先红后绿再重构；测试失败不能被当作完成 |
| `review-fix-merge-branch` | 分支收尾、review/fix/commit/merge 闭环 | 已随包 | 只提交本轮相关文件，最终仍走 commit-based xhigh review gate |
| `git-safe-commit` | 需要 staging、commit、过滤运行态/敏感文件 | 已随包 | 提交前检查边界，不纳入 `.codex/memories`、runtime task、缓存和构建产物 |
| `git-guardrails-claude-code` | 需要拒绝危险 git 操作或自动化命令校验 | 已随包 | 作为安全护栏，不替代人工确认和仓库规则 |
| `improve-codebase-architecture` | 用户要求架构改进、可测试性、模块深化 | 已随包 | 先提出具体可验证的重构机会，不做泛泛建议 |
| `edit-article` | 文档、文章、handbook 需要结构和表达优化 | 已随包 | 文档事实以实现和权威来源为准 |
| `ubiquitous-language` | 领域术语、DDD、概念混乱、术语表 | 已随包 | 输出 canonical terms 和歧义项 |
| `write-a-skill` / `skill-creator` | 新建或更新技能 | 已随包 | 先定义触发条件、边界和 progressive disclosure |
| `skill-installer` | 列出或安装外部技能 | 已随包 | 只按用户授权联网安装；本包默认使用离线 vendor 技能 |
| `plugin-creator` | 新建 Codex plugin 或 marketplace 元数据 | 已随包 | 插件目录和 `.codex-plugin/plugin.json` 必须完整 |
| `openai-docs` | OpenAI API、模型、Codex 官方能力和最新文档 | 已随包 | 只查官方 OpenAI 来源，输出引用和时效边界 |
| `imagegen` / `proxy-image-generation` | 需要图片生成、图片代理或视觉资产 | 已随包 | 仅在需要 bitmap 资产或代理配置时触发 |
| `cli-creator` | 设计或实现 CLI、API wrapper、SDK 命令行 | 已随包 | CLI 输出要稳定、可组合、可验证 |
| `migrate-to-codex` | 迁移 AGENTS、skills、agents、MCP 配置到 Codex | 已随包 | 不覆盖用户文件，先 dry-run 或列出改动 |
| `harness-release-gate` | 本项目或使用本 harness 的提交前验证/release gate | 已随包 | 跑 verify、candidate commit、commit-based xhigh review |
| `gh-fix-ci` | GitHub Actions PR checks 失败 | 已随包 | 只处理 GitHub Actions；外部 CI 只记录链接 |
| `gh-address-comments` | GitHub PR review/issue comments 处理 | 已随包 | 先验证 `gh` 登录，不泄露 token |
| `security-best-practices` | 用户明确要求安全最佳实践或安全代码建议 | 已随包 | 支持语言内触发；普通 review 不自动升级成安全审计 |
| `security-threat-model` | 用户明确要求 threat model 或 abuse path | 已随包 | 输出资产、边界、攻击者能力、缓解措施 |
| `setup-pre-commit` | 用户要求 pre-commit/Husky/lint-staged | 已随包 | 只适用于对应 JS/TS repo 形态 |
| `migrate-to-shoehorn` | TypeScript 测试从 `as` 迁移到 shoehorn | 已随包 | 只在明确命中该技术栈时触发 |
| `scaffold-exercises` | 创建课程练习目录和题解 | 已随包 | 只在课程/练习项目触发 |
| `obsidian-vault` | 用户要求搜索、创建或整理 Obsidian 笔记 | 已随包 | 先发现 vault 路径，避免误写其他目录 |

`已随包` 表示技能已在 `plugins/codex-memory/skills/bundled-skills.json` 中登记，并随发布包离线安装到 `~/.agents/skills`。安装器仍保持不覆盖用户已有技能目录的策略。

## 4. 需求与策划文档规则

策划需求默认进入需求完整性审查。审查目标不是替用户补出未经确认的产品决策，而是把问题尽早暴露。

必须检查：

- 目标用户、核心玩法或核心业务目标是否明确。
- 输入、输出、状态变化和边界条件是否完整。
- 前置条件、失败路径、异常状态、恢复路径是否存在。
- 多端、多语言、WebGL/小游戏、离线/弱网、性能和包体约束是否被提到。
- 验收标准是否可测试，是否能转成自动化测试、smoke、手工清单或日志观测点。
- 是否存在逻辑矛盾、循环依赖、不可达状态、缺少初始状态或缺少终止条件。
- 是否有安全、隐私、支付、账号、渠道、资源版权或合规风险。
- 是否有迁移、回滚、灰度、兼容旧数据或“不兼容直接替换”的说明。

能通过现有代码、文档、配置和权威资料回答的问题，由 Agent 自行补齐并标注依据。不能可靠回答的问题，用 `grill-me` 风格形成问题列表，按阻断程度分为 `blocking`、`should_confirm`、`can_assume`。

## 5. 技术选择规则

技术选择默认遵循“正确性与性能优先，兼容性不作为保留旧设计的理由”。

默认顺序：

1. 现有项目约定和已验证架构。
2. 官方库或官方推荐实现。
3. 稳定、维护活跃、license 清楚的第三方开源库。
4. 可改造的第三方库。
5. 自研实现。

性能和包体可以改变顺序。如果官方库比第三方方案在关键指标上差约 20% 以上，且第三方 license、维护、平台兼容和安全边界可接受，应优先第三方，而不是机械坚持官方库。

OpenSpec/BMAD 这类治理集成属于专项例外：已有决策是 upstream-core-first / adapter-first，优先复用官方上游命令或核心能力，通过本项目 adapter 接入。通用“第三方性能优先”规则不能覆盖已确认的上游复用边界；除非后续单独完成 license、性能、兼容和迁移评审。

必须默认考虑：

- 多语言、多平台、WebGL/小游戏兼容性。
- 包体、首包、热更包、资源依赖和运行时内存。
- Unity/Laya/Cocos 等客户端目标平台差异。
- 移动端和小游戏弱 CPU、弱 GPU、弱网络、文件系统限制。
- 是否能模块化、可拆卸、可选择性编译。
- 是否会破坏 IDE、编译器、代码补全、tree-shaking 或 AOT/linker 裁剪能力。
- 是否需要抽象层；为了性能、工具链或平台能力，不应过度封装。例如官方 logging API 已能提供编译期辅助时，不应再套一层导致代码补全和静态分析失效。

资源管理默认规则：

- 一个业务预制体优先只依赖本模块自己的 AB 包。
- 最多再依赖一个公共 AB 包。
- 禁止一个预制体无边界依赖多模块 AB 包。
- 跨模块公共资源必须有明确 owner、版本、变更影响和回滚策略。
- release gate 应检查资源依赖扩散、重复资源、未裁剪资源和平台包体变化。

## 6. 测试与验证规则

新增或修改功能时，测试计划必须说明：

- 单元测试覆盖核心纯逻辑、边界条件和错误路径。
- 集成测试覆盖跨模块契约、配置读取、序列化、CLI 或 hook 行为。
- 平台测试覆盖 Windows、Linux/macOS、WebGL/小游戏或目标引擎差异。
- 性能测试覆盖关键路径、包体、冷启动、内存、资源依赖和热更大小。
- AI 诊断日志或 DEBUG 日志能定位关键分支、输入输出摘要、降级原因、状态转换和完成结果。
- Release profile 确认诊断日志、调试宏、临时 sink 和裸日志绕过均已关闭。

缺少必要测试时，不能把任务标记为完整完成；只能标记为实现完成但验证不完整，并列出下一步。

## 7. 多任务与 SubAgent 并行规则

当需求被拆分成多个任务时，先写卡点分析：

- 依赖关系：哪些任务必须先完成，哪些可以并行。
- 决策卡点：哪些问题需要用户确认。
- 环境卡点：缺工具、缺权限、缺平台或无法运行验证。
- 接口卡点：跨模块 schema、API、资源契约或数据迁移未定。
- 验证卡点：没有 profile、没有测试数据、没有设备或无法复现。

只要不是所有任务都被同一个卡点阻塞，就必须按依赖关系并行推进。并行方式优先使用 SubAgent，但每个 SubAgent 必须有明确 scope、cwd、规则、验收、验证 profile 和 forbidden paths。SubAgent 不得回滚他人改动，不得越权写文件，不得用固定总时长判失败。

主 Agent 负责：

- 创建 harness task。
- 读取 `subagent_dispatch_plan.host_spawn_requests`。
- 派发互不重叠的 specialist。
- 在 SubAgent 运行时处理不改变其 scope 的本地任务。
- 汇总 checkpoint、scope guard、验证结果、冲突和下一步。

如果宿主不支持 SubAgent、scope 冲突或所有任务共享同一阻塞，主 Agent 记录降级原因后串行执行。

## 8. 代码 Review 规则

代码 review 以阻断 correctness、数据安全、迁移风险、性能退化、验证缺口和发布风险为主，不做低价值风格 nit。

默认 gate：

1. 先跑确定性验证和 review preflight。
2. 创建只包含本轮相关文件的 candidate commit。
3. 记录 commit SHA。
4. 运行 `codex xhigh review --commit <commit-sha>`。
5. 发现阻断问题后修复并创建新的提交或重做候选提交，再 review 新提交本身。
6. 无新阻断问题后才允许 push 或发布。

通用 SubAgent reviewer 只能做窄范围专题审查，不替代最终 commit-based xhigh review。大 diff 或长耗时 gate 可以用 XHigh Review Runner SubAgent 作为命令执行器。

## 9. 后续落地任务

本轮文档先固化规则。后续实现必须拆成可验证任务：

- 扩展 bundled skills：核对 `grill-me`、`design-an-interface`、`prd-*`、`tdd`、`review-fix-merge-branch`、`git-safe-commit` 等技能的来源、license、体积和依赖，符合条件后随包 vendor 并默认安装。
- 实现 skill routing audit：任务开始时输出 matched skills、used skills、skipped skills 和跳过原因。
- 强化 Requirements Integrity Gate：把策划需求问题列表、技术选择依据、测试计划缺口和性能/包体约束纳入结构化字段。
- 强化 SubAgent planner：拆多任务时先输出卡点分析，并把可并行任务转为 disjoint `host_spawn_requests`。
- 强化 release profile：覆盖 WebGL/小游戏、多语言、多平台、资源 AB 依赖、包体、性能和诊断日志关闭。
