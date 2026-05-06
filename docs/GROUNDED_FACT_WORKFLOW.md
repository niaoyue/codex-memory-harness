# 资料核验与反幻觉执行流程

## 1. 目标

本文定义 Codex Memory Harness 项目中“高风险事实”的写作、校正和验证流程。目标不是让模型“更谨慎地写”，而是把外部知识、产品能力、版本状态、安全声明和项目实现状态从自由生成变成可审计的工程流程。

适用场景：

- 校正文档里的 OpenAI、Codex、Agent、RAG、模型、API、价格、限制、能力边界等外部资料。
- 新增、修改或解释外部 API、SDK、CLI、引擎、框架、云服务、Unity/Unreal/服务器框架调用方式。
- 总结权威资料、标准、论文、云厂商文档或安全指南。
- 声明本仓库已经实现、尚未实现、默认启用、发布级可用或经过验证的能力。
- 把 memory、RAG、工具结果、搜索结果或历史任务摘要写入可提交文档。

资料核验记录：本节规则来源于第 9 节权威资料基线，重点参考 OpenAI hallucination 说明、NIST AI 600-1、OWASP LLM09 和 Google Cloud Grounding：`https://openai.com/index/why-language-models-hallucinate/`

## 2. 风险分级

| 等级 | 典型断言 | 最低证据要求 |
|---|---|---|
| low | 本仓库文件存在、命令输出、局部代码行为 | 本地文件、测试或命令输出 |
| medium | 通用技术概念、非关键背景解释、稳定论文概念 | 至少 2 个来源，其中一个应为官方、标准、论文或本仓库实现 |
| high | OpenAI/Codex/API 能力、模型限制、价格、安全/隐私、发布能力、自动执行能力、已经实现/已经验证、外部 API 调用方式和版本差异 | 官方来源 + 第二权威来源，或官方来源 + 本仓库代码/测试/真实命令输出 |
| blocked | 来源冲突、来源不可达、只有搜索摘要、只有记忆、只有模型自述 | 不写成事实；正文标注不确定，或停止修改等待进一步核验 |

风险由断言内容决定，不由文档类型决定。普通教程里只要出现“当前官方支持”“已经实现”“不会泄露”“自动验证通过”等表达，就按 high 处理。

资料核验记录：本节规则来源于第 9 节权威资料基线，重点参考 NIST AI 600-1 和 OWASP LLM09：`https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf`

## 3. 证据模型

每条可写入正文的高风险断言都应能映射到证据记录。证据记录至少包含：

| 字段 | 说明 |
|---|---|
| claim_id | 稳定短 ID，例如 `codex-memory-layering-20260506-01` |
| claim | 被正文表达的最小断言 |
| risk | `low` / `medium` / `high` |
| source_id | 稳定来源 ID，例如 `openai-codex-memories` |
| source_type | `official` / `standard` / `paper` / `vendor` / `repo` / `test` / `observed` / `memory` |
| checked_at | 核验日期，使用 `YYYY-MM-DD` |
| support | `direct` / `indirect` / `contradicted` / `stale` |
| locator | URL、文件路径、测试名或命令摘要 |
| version_scope | 适用版本，例如 Unity 2022.3、Next.js 15.1.8、OpenAI Responses API 当前文档；不适用时写 `n/a` |
| authority_channel | `official_mcp` / `official_docs` / `context7` / `local_sdk` / `openapi` / `protobuf` / `source_code` / `compiler` / `test` |

正文可使用精简形式，但必须保留可审计线索。推荐在相关二级或三级小节末尾放置：

```text
本节校正依据（YYYY-MM-DD 只读核对）：

- OpenAI Codex：`https://platform.openai.com/docs/codex`
- 本项目实现：`plugins/codex-memory/scripts/context_builder.py`
- 本项目测试：`tests/test_project_behaviors.py`
```

资料核验记录：本节规则来源于第 9 节权威资料基线，重点参考 OpenAI Citation formatting 和本项目测试约束：`https://platform.openai.com/docs/guides/citation-formatting`

## 4. 多源核验规则

1. 先拆断言，再找来源。不要先搜一堆链接再让模型自由综合。
2. OpenAI、Codex、ChatGPT、Responses API、模型能力、工具能力和 pricing 类内容，以 OpenAI 官方文档为第一来源。
3. 安全、风险、治理类内容优先使用 NIST、OWASP、厂商安全文档和本仓库实际 gate。
4. RAG、向量检索、citation、grounding 类内容至少区分“检索到相关材料”和“生成内容被证据直接支持”。
5. 本项目能力声明必须回到代码、测试、验证命令或 release gate；不能只引用计划文档。
6. 记忆、历史 summary、搜索摘要、二手博客只能作为线索，不能单独支撑 high 风险断言。
7. 如果来源之间冲突，优先级为：官方当前文档 > 标准/监管框架 > 论文 > 云厂商实现文档 > 本仓库代码/测试/命令输出 > 项目记忆 > 搜索摘要。
8. 如果冲突无法消解，正文必须写“不确定/未确认/当前未核验”，或停止修改。

资料核验记录：本节规则来源于第 9 节权威资料基线，重点参考 OpenAI、NIST、OWASP 和 Google Cloud Grounding：`https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/overview`

## 5. API Authority Resolver

API 幻觉和资料幻觉不同。资料幻觉通常是“事实说错”；API 幻觉通常是“方法名、参数、导入路径、生命周期、配置键、版本差异或 SDK 能力被模型编出来”。因此，涉及外部 API 的任务必须先解析 API 权威来源，再写代码或文档。

项目本身应提供的能力：

| 能力 | 作用 | 最小实现 |
|---|---|---|
| 项目生态识别 | 判断客户端、服务器、后台、脚本、文档等 route 分别使用什么技术栈 | workspace scanner 读取 `package.json`、lockfile、`*.csproj`、`ProjectSettings/ProjectVersion.txt`、`Packages/manifest.json`、OpenAPI/protobuf 等 |
| 版本识别 | 避免拿错误版本文档生成代码 | 从 lockfile、Unity project version、NuGet/npm/pip/go module、SDK manifest 中读取版本 |
| API authority plan | 为任务列出要查哪些 API 权威来源 | harness artifact 记录 `ecosystem`、`package`、`version_scope`、`authority_channel`、`locator`、`verification` |
| 本地 API 证据 | 让私有框架和内部 SDK 不依赖公网资料 | 检索本地源码、生成客户端、XML docs、OpenAPI/protobuf、已有调用点 |
| 验证 gate | 不让“看起来对”的 API 直接进入完成态 | 编译、类型检查、Unity batchmode、单测、contract test、schema/codegen 验证 |

外部可提供的能力：

| 来源 | 适合解决 | 信任边界 |
|---|---|---|
| 官方 MCP | OpenAI 等官方维护文档 | 优先级最高；仍需版本和本地验证 |
| 官方网页/API 文档 | Unity Scripting API、云厂商 SDK、数据库、支付、认证 | 必须匹配版本；网页不可达时不能写成已核验 |
| Context7 | 常见第三方库、版本变化快的 JS/TS/Python/云服务 SDK 文档 | 是通用文档检索和上下文注入，不等于官方证明器；结果需结合本地版本和测试 |
| 本地 SDK/源码 | 私有包、内部框架、生成代码、已安装依赖 | 对当前项目最贴近；可能缺少语义解释，需要测试验证 |
| OpenAPI/protobuf/GraphQL schema | 服务端/客户端契约、接口参数、生成客户端 | 对接口 shape 权威；不证明业务流程正确 |
| 编译器和测试 | API 是否存在、签名是否匹配、调用是否能运行 | 最终 gate；不能替代外部行为和文档语义 |

API authority plan 示例：

```json
{
  "ecosystem": "unity",
  "route": "client",
  "detected_version": "2022.3.x",
  "api_surface": ["UnityEngine", "UnityEditor", "Addressables", "TMP"],
  "authority_channels": ["official_docs", "local_sdk", "compiler"],
  "locators": [
    "ProjectSettings/ProjectVersion.txt",
    "Packages/manifest.json",
    "https://docs.unity3d.com/ScriptReference/"
  ],
  "verification": ["unity_batchmode_compile"]
}
```

执行规则：

1. 只要任务会新增、修改或解释非本项目自定义 API，就必须生成或复用 API authority plan。
2. Unity 客户端优先使用 Unity 官方 Scripting API、对应包官方文档、本地 Unity 版本和 batchmode 编译验证。
3. 服务器优先使用语言/框架官方文档、本地 dependency lock、OpenAPI/protobuf/schema、编译和 contract test。
4. OpenAI/Codex 相关 API 优先使用 OpenAI 官方 docs 或官方 docs MCP；Context7 只能作为补充。
5. Context7 适合查常见库的当前文档和代码片段，但不得单独支撑安全、支付、认证、云权限、版本迁移等 high 风险断言。
6. 本地版本与外部文档冲突时，以本地 dependency/version + 编译测试结果为完成 gate；正文要说明外部文档适用版本。
7. 查不到权威 API 来源时，不能凭模型补全 API 名称；应改为本地搜索已有调用、读取类型定义、生成最小编译探针，或停止并标注 blocked。

当前 Phase 1 已落地只读 `api_authority_router.py`。它复用 workspace scanner 识别 Unity、Web、服务器和本仓库工具项目，输出 `ecosystem`、`detected_version`、`api_surfaces`、`authority_channels`、`locators`、`verification` 和 MCP 缺口状态。该阶段不联网、不安装 MCP，只生成计划；自动安装和真实 MCP 调用应在后续 policy gate 中单独接入。

推荐本地入口：

```powershell
py -X utf8 plugins\codex-memory\scripts\api_authority_router.py --workspace-root . --objective "OpenAI Responses API" plan
```

资料核验记录：本节规则来源于 Unity 官方文档、OpenAI Codex MCP、OpenAI Docs MCP、Context7 官方 README/API Guide、本项目 workspace routing 设计和 Phase 1 实现：`https://docs.unity3d.com/ScriptReference/index.html`、`plugins/codex-memory/scripts/api_authority_router.py`、`plugins/codex-memory/scripts/api_authority_sources.py`、`tests/test_api_authority_router.py`

## 6. MCP 与 Context7 接入策略

MCP 是权威资料和工具接入通道，不是天然可信来源。接入策略必须同时看来源可信度、权限、副作用和是否需要认证。

| 等级 | 典型 MCP | 默认动作 |
|---|---|---|
| A：官方、只读、无密钥或低风险密钥 | OpenAI Docs MCP、官方只读文档 MCP | 可由 doctor/authority ensure 自动安装或补配置，并记录工具简报 |
| B：第三方通用文档检索 | Context7 | 默认可生成安装计划；只有项目 policy 允许 `safe_readonly_auto_install` 时才自动安装 |
| C：需要 token/OAuth、能写数据、能操作外部系统 | GitHub、Figma、Sentry、浏览器自动化、内部生产 MCP | 不自动安装；必须显式授权、限定 tool allowlist、记录风险 |

第一次使用时的建议流程：

1. `authority doctor` 检查当前任务需要哪些 MCP 或外部 authority channel。
2. 已安装且可见：直接使用。
3. 未安装但属于 A 级：自动执行安装/配置，随后重新 doctor；当前 session 看不到新 MCP 时，记录“已为下次 session 配好”，本轮降级到官方网页或本地 SDK。
4. 未安装且属于 B 级：如果项目策略允许自动安装，则安装；否则输出安装计划和降级来源。
5. 属于 C 级：只输出计划，等待用户明确授权。

Context7 的正确定位：

- 它通过 `resolve-library-id` 和 `query-docs` 获取库文档上下文，能减少“模型按旧训练数据编 API”的概率。
- 它公开的 MCP server 是只读工具壳，会调用 Context7 后端；官方声明 API backend、解析器和爬虫是私有组件。
- 它适合解决常见库的过期 API、错误导入路径、参数签名、配置格式和版本迁移片段。
- 它不能证明本地项目安装版本、不能替代官方文档、不能验证私有 API、不能替代编译测试。

资料核验记录：本节规则来源于 OpenAI Codex MCP、OpenAI Docs MCP、Context7 官方 README、Context7 API Guide 与 Context7 MCP 源码：`https://github.com/upstash/context7`

## 7. 禁止项

- 编造来源、编造 citation、把打不开的页面当成已核验。
- 引用 URL 但正文断言没有被该 URL 直接支持。
- 用 RAG/search 召回内容直接替代事实判断。
- 用 MCP/Context7 返回内容替代版本识别、官方来源判断和本地验证。
- 未读取项目依赖版本就套用外部 API 示例。
- 用其他语言、其他引擎、其他主版本的 API 套到当前项目。
- 把“计划实现”“建议实现”“可能支持”写成“已经实现”。
- 把 memory 里的旧结论写成当前事实而不重新验证。
- 用二手文章替代官方文档说明 OpenAI/Codex/API 当前能力。
- 把工具 stdout 的片段外推成完整验证通过。
- 在文档中保留高风险关键词但没有本节依据或资料核验记录。

资料核验记录：本节规则来源于第 9 节权威资料基线，重点参考 OpenAI Citation formatting 和 OWASP LLM09：`https://genai.owasp.org/llmrisk/llm092025-misinformation/`

## 8. 网络失败与离线降级

外部核验必须遵守只读和最小化原则，不上传密钥、令牌、原始日志、私有 URL 或敏感载荷。

失败处理：

- 429：退避 20 秒后再试。
- 5xx 或超时：退避 2 秒，最多重试一次。
- 仍失败：给保守离线答案，明确写出“未完成在线核验”的局限，不把未核验内容写成确定事实。

离线时允许写：

- 本仓库本地可验证事实。
- 已知但标注为“待在线核验”的草稿。
- 明确保守的风险提示。
- 从本地 SDK、源码、类型定义、OpenAPI/protobuf、lockfile、编译器得到的 API 事实。

离线时禁止写：

- 最新能力、最新价格、最新版本、最新限制。
- “官方已经支持/不支持”的确定性断言。
- 安全、隐私、合规方面的保证性断言。
- 未经本地编译或官方文档确认的新 API 名称、参数和配置键。

资料核验记录：本节规则来源于项目 `AGENTS.md` 退避规则与第 9 节权威资料基线：`AGENTS.md`

## 9. 小节级执行流程

每个需要校正的小节都按同一流程执行：

| 步骤 | 退出条件 |
|---|---|
| 1. 断言拆解 | 小节中的 high/medium 断言已列出 |
| 2. 来源映射 | 每条 high 断言有官方/权威来源候选 |
| 3. API authority plan | 如涉及外部 API，已识别项目版本、包版本、官方/本地 authority channel |
| 4. 多源核对 | 来源支持、间接支持、冲突或过期状态已判定 |
| 5. 正文或代码修改 | 只写被证据支持的最小断言/API 调用 |
| 6. 依据落点 | 同小节出现“本节校正依据”或“资料核验记录” |
| 7. 自动 gate | `verify_grounded_docs.py` 对 required 文档通过 |
| 8. 项目验证 | `codex package verify`、编译、类型检查、Unity batchmode 或 contract test 通过 |

这条流程故意按小节执行。文末统一 References 只能作为补充，不能替代小节级证据。

资料核验记录：本节规则来源于第 9 节权威资料基线与本项目 gate 设计：`scripts/verify_grounded_docs.py`

## 10. 自动检查策略

本仓库提供 `scripts/verify_grounded_docs.py`，用于阻断最常见的幻觉写法：

- required 文档不存在会失败。
- required 文档没有 URL 或本地证据会失败。
- 包含 high 风险关键词的小节没有证据块会失败。
- 证据块没有 URL、本地路径或命令/测试证据会失败。
- 非 required 文档默认只产生 warning，避免一次性阻断历史文档。

后续应增加的 API 专项 gate：

- 对代码 diff 中新增的外部 namespace/package/import 做 API authority plan 检查；Phase 1 可先使用 `plugins/codex-memory/scripts/api_authority_router.py` 生成只读计划。
- 对 Unity route 检查 `ProjectSettings/ProjectVersion.txt`、`Packages/manifest.json` 和 batchmode 验证记录。
- 对服务器 route 检查 lockfile、OpenAPI/protobuf/schema、build/test/contract test 记录。
- 对 MCP/Context7 使用记录 `libraryId`、版本、query、source type 和 fallback 状态。

推荐命令：

```powershell
py -X utf8 scripts\verify_grounded_docs.py --required docs\LLM_AGENT_MEMORY_HANDBOOK.md --required docs\GROUNDED_FACT_WORKFLOW.md
py -X utf8 scripts\verify_project.py
codex package verify
```

资料核验记录：本节规则来源于第 9 节权威资料基线与本项目验证入口：`scripts/verify_project.py`

## 11. 权威资料基线

本流程的设计参考了以下资料，并按 2026-05-06 只读核对：

- OpenAI：`https://openai.com/index/why-language-models-hallucinate/`
- OpenAI Evals：`https://platform.openai.com/docs/guides/evals`
- OpenAI Evaluation best practices：`https://platform.openai.com/docs/guides/evaluation-best-practices`
- OpenAI Citation formatting：`https://platform.openai.com/docs/guides/citation-formatting`
- OpenAI Model Spec：`https://model-spec.openai.com/`
- NIST AI 600-1 Generative AI Profile：`https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf`
- NIST AI Risk Management Framework：`https://www.nist.gov/itl/ai-risk-management-framework`
- OWASP LLM09:2025 Misinformation：`https://genai.owasp.org/llmrisk/llm092025-misinformation/`
- OWASP Top 10 for LLM Applications：`https://genai.owasp.org/llm-top-10/`
- Google Cloud Vertex AI Grounding：`https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/overview`
- Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks：`https://arxiv.org/abs/2005.11401`
- OpenAI Codex MCP：`https://developers.openai.com/codex/mcp`
- OpenAI Docs MCP：`https://developers.openai.com/learn/docs-mcp`
- Unity Scripting API：`https://docs.unity3d.com/ScriptReference/index.html`
- Context7 README：`https://github.com/upstash/context7`
- Context7 API Guide：`https://context7.com/docs/api-guide`

核心结论：

- OpenAI 资料把 hallucination 视为模型可能生成自信但不真实内容的风险，并强调评估与验证。
- NIST Generative AI Profile 将 confabulation、信息完整性、provenance 和可追溯性纳入生成式 AI 风险治理。
- OWASP 将 misinformation、overreliance 和 RAG/向量链路弱点视为 LLM 应用安全风险。
- Google Cloud grounding 文档把 grounding 描述为让模型输出连接到可验证来源的工程机制。
- RAG 能引入外部知识，但检索命中不等于每条生成断言都被证据直接支持。
- API 幻觉需要额外约束项目版本、SDK 版本、官方文档、本地类型/源码和编译测试；MCP 与 Context7 只能作为 authority channel，不能替代最终验证。
