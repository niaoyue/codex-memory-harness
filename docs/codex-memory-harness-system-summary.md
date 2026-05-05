# Codex Memory / Harness 体系总结

## 1. 文档目的

本文总结 Codex Memory Harness 的独立项目形态，包括外部记忆、Harness 运行时、验证回写、PowerShell 无感启动、打包安装和安全边界。

该体系的目标不是修改模型内部记忆，而是在用户本机建立一套可控的外部增强层，让 Codex 在跨窗口、跨任务、跨项目协作时具备更稳定的上下文连续性。

## 2. 总体结论

当前系统已经形成独立可分发项目：

```text
codex-memory-harness/
```

普通用户安装后继续使用：

```powershell
codex
```

诊断入口：

```powershell
codex-memory-doctor
```

回退入口：

```powershell
codex-raw
```

打包入口：

```powershell
codex package build
```

安装入口：

```bat
install.bat
```

POSIX shell：

```sh
sh ./install.sh
```

`install.sh` 只是 POSIX shell 入口包装；当前 hook/MCP 运行时仍依赖名为 `powershell` 的 PowerShell launcher。

## 3. 能力边界

Codex Memory Harness 只增强外部可控层，不干涉模型内部参数、训练态记忆或服务端行为。

当前覆盖四层：

| 层级 | 能力 | 当前实现 |
|---|---|---|
| 1 | 会话工作记忆 | `hook_runner.py` 维护 task state、working set、constraints、next step |
| 2 | 外部混合检索 | SQLite、JSONL、summary、distilled asset、路径检索和全文检索 |
| 3 | 提示层与上下文编排 | `context_builder.py` 基于预算构建 context pack |
| 4 | 蒸馏写回 | `on_task_complete` 写入 task summary 和 distilled asset |

额外增强：

- Harness 生命周期管理。
- Verification Runner 验证回写。
- Bootstrap / Doctor 启动自检。
- PowerShell profile wrapper。
- 用户级安装、卸载和打包。

## 4. 分层架构

| 层级 | 名称 | 作用 |
|---|---|---|
| 1 | 用户入口层 | `codex`、`codexm`、`codex-raw`、`codex-memory-doctor` |
| 2 | PowerShell wrapper 层 | 在 profile 中注册函数，不修改真实 Codex CLI |
| 3 | Bootstrap / Doctor 层 | 识别项目、检查安装、初始化 `.codex` 配置 |
| 4 | 全局规则层 | 写入 `~/.codex/AGENTS.md` 的通用 memory 使用规则 |
| 5 | 项目规则层 | 项目内 `AGENTS.md` 和 `.codex/harness` 配置 |
| 6 | Memory 插件层 | 存储、检索、上下文包、蒸馏 |
| 7 | Harness 层 | 任务 start/checkpoint/complete 生命周期 |
| 8 | Verification 层 | 配置化验证、脱敏摘要、artifact 回写 |
| 9 | 角色协作协议层 | 记录 SubAgent 角色分工产物；当前不是自动调度器 |
| 10 | Bundled skills 层 | vendor openai/skills curated 子集和本项目 release gate skill，安装到 `~/.agents/skills` |
| 11 | 打包分发层 | `build_release.py` 生成 zip，`install.bat` / `install.sh` 安装 |

## 5. 安装后的本机布局

全局插件入口：

```text
<USER_HOME>/plugins/codex-memory
```

全局规则：

```text
<USER_HOME>/.codex/AGENTS.md
```

Bundled Codex skills：

```text
~/.agents/skills/security-best-practices
~/.agents/skills/security-threat-model
~/.agents/skills/cli-creator
~/.agents/skills/migrate-to-codex
~/.agents/skills/gh-fix-ci
~/.agents/skills/gh-address-comments
~/.agents/skills/harness-release-gate
```

全局 marketplace：

```text
<USER_HOME>/.agents/plugins/marketplace.json
```

PowerShell 7 profile：

```text
<USER_HOME>/Documents/PowerShell/Microsoft.PowerShell_profile.ps1
```

Windows PowerShell profile 可选：

```text
<USER_HOME>/Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1
```

项目私有层：

```text
<PROJECT_ROOT>/.codex/memories
```

用户全局层：

```text
<USER_HOME>/.codex/codex-memory-harness/memories
```

官方 Codex Memories：

```text
<USER_HOME>/.codex/memories
```

项目共享 memory 建议位置：

```text
<PROJECT_ROOT>/.codex/shared
```

三者边界：

| 层级 | 是否提交 | 内容 |
|---|---|---|
| 官方 Codex Memories | 不提交 | 官方自动生成的个人长期记忆 |
| 用户全局层 | 不提交 | 跨项目偏好、通用工作流、长期个人规则 |
| 项目私有层 | 不提交 | 本地任务状态、事件、summary、distilled 草稿 |
| 项目共享层 | 可提交，需审查 | 团队确认的项目事实、架构决策、流程、路由摘要 |

完整分层策略见：

```text
docs/MEMORY_LAYERING.md
```

## 6. 使用方式

普通使用：

```powershell
codex
```

显式 memory wrapper：

```powershell
codexm
```

只做诊断：

```powershell
codex memory doctor
codex-memory-doctor
```

绕过 wrapper：

```powershell
codex-raw
```

临时禁用 wrapper：

```powershell
$env:CODEX_MEMORY_DISABLE_WRAPPER = "1"
codex
```

## 7. 项目初始化

进入任意项目后，doctor 只读检查：

```powershell
codex memory doctor
```

初始化项目 memory 和 harness：

```powershell
codex memory init
```

初始化会创建：

```text
<PROJECT_ROOT>/.codex/memories/
<PROJECT_ROOT>/.codex/harness/commands.json
<PROJECT_ROOT>/.codex/harness/project_profile.json
```

不会覆盖已有 harness 配置。

## 8. Memory 插件

核心脚本：

| 文件 | 作用 |
|---|---|
| `memory_store.py` | task state、repo decision、task summary 读写 |
| `retrieval_store.py` | 路径、精确内容、全文检索 |
| `context_builder.py` | 构建 context pack 和注入预算 |
| `distillation_store.py` | 任务完成后的蒸馏资产 |
| `hook_runner.py` | before_task、after_tool、before_response、on_task_complete |
| `init_storage.py` | 初始化 SQLite、JSONL、summary 和 distilled 目录 |
| `memory_server.py` | MCP stdio 服务入口 |

最小任务生命周期：

```powershell
codex memory hook before_task --memory-scope project --memory-cwd <PROJECT_ROOT> --payload-file payload.json
codex memory hook after_tool --memory-scope project --memory-cwd <PROJECT_ROOT> --payload-file payload.json
codex memory hook before_response --memory-scope project --memory-cwd <PROJECT_ROOT> --payload-file payload.json
codex memory hook on_task_complete --memory-scope project --memory-cwd <PROJECT_ROOT> --payload-file payload.json
```

PowerShell 中优先使用 `--payload-file`，避免内联 JSON 引号转义问题。

## 9. Harness Controller

Harness Controller 提供三段式任务运行时：

```powershell
codex harness start --task-file task.json
codex harness checkpoint --task-id <TASK_ID> --result-file result.json
codex harness complete --task-id <TASK_ID> --summary-file summary.md
```

它会维护：

```text
<PROJECT_ROOT>/.codex/harness/tasks/<TASK_ID>/task_spec.json
<PROJECT_ROOT>/.codex/harness/tasks/<TASK_ID>/run_state.json
<PROJECT_ROOT>/.codex/harness/tasks/<TASK_ID>/artifacts.jsonl
```

这些运行态文件不进入打包产物。

## 10. Verification Runner

验证配置来自：

```text
<PROJECT_ROOT>/.codex/harness/commands.json
<PROJECT_ROOT>/.codex/harness/project_profile.json
```

列出命令：

```powershell
codex harness verify list
```

运行默认 profile：

```powershell
codex harness verify run --profile primary
```

绑定任务回写：

```powershell
codex harness verify run --task-id <TASK_ID> --profile primary
```

安全策略：

- 输出摘要有长度限制。
- 常见敏感字段会脱敏。
- 拒绝明显危险命令模式。
- 验证失败时返回结构化结果，而不是吞掉错误。

## 11. SubAgent 角色协作

当前项目没有实现宿主级并发 SubAgent 执行器。它支持的是通过 harness artifact 记录不同角色产物，让主 agent 或宿主环境提供的 SubAgent 能力按统一协议协作；同时可以通过 `codex workspace schedule` 从 route plan 生成 coordinator/specialist dispatch plan。

推荐角色：

| 角色 | 职责 |
|---|---|
| Task Planner | 明确目标、验收标准、工作集和风险 |
| Architect | 判断模块边界、接口方向和迁移策略 |
| Implementer | 执行最小必要代码或文档修改 |
| Reviewer | 做限定 scope 的专题审查；不替代 Codex CLI xhigh review |
| XHigh Review Runner | 并行执行 `codex xhigh review --uncommitted`，必要时降级到 `codex-raw -- review -c model_reasoning_effort="xhigh" --uncommitted`，按 stdout/stderr 和状态进度观察且不套固定总时长，回传退出状态和 findings |
| Verifier | 运行配置化验证并解释失败 |
| Documentation Maintainer | 更新 README、用户指南和迁移说明 |
| Security Reviewer | 检查敏感信息、网络边界和危险命令 |
| Release Manager | 过滤提交内容、准备提交说明和发布边界 |

角色产物建议通过 `codex harness checkpoint --task-id <TASK_ID> --result-file role-result.json` 写入同一个任务。完整协议见：

```text
docs/SUBAGENT_WORKFLOW.md
```

## 12. 安装器

核心安装器：

```text
plugins/codex-memory/scripts/install_codex_memory.py
```

顶层安装入口：

```bat
install.bat
```

POSIX shell：

```sh
sh ./install.sh
```

旧安装更新：

```bat
install.bat --update-existing
```

POSIX shell：

```sh
sh ./install.sh --update-existing
```

卸载：

```bat
install.bat --uninstall
```

POSIX shell：

```sh
sh ./install.sh --uninstall
```

安装器行为：

- 默认优先创建 Windows junction。
- 如果当前版本已经安装，返回 `already_installed`，不重复安装插件。
- 如果目标已存在且指向其他目录，默认不覆盖；必须显式传入 `--update-existing` 或 `-UpdateExisting`。
- `--replace-existing` 与 `-ReplaceExisting` 作为兼容别名保留。
- 默认从发布包内的 `plugins/codex-memory/skills/openai-curated` 和 `plugins/codex-memory/skills/local` 离线复制 bundled skills 到 `~/.agents/skills`；目标技能已存在时跳过，不覆盖用户版本。
- 可用 `--skip-skills` 或 `-SkipSkills` 跳过 bundled skills 安装。
- 替换旧普通目录时会备份，不直接删除。
- profile 和 AGENTS 采用标记块写入，降低误改用户内容的风险。
- 旧的未标记全局 AGENTS 规则会保留，不强行覆盖。
- 卸载默认不删除 `~/.agents/skills`，避免误删用户自行安装或修改的技能。

## 13. 打包分发

打包命令：

```powershell
codex package build
```

产物：

```text
dist/codex-memory-harness-<VERSION>.zip
```

打包排除：

- `.git`
- `dist`
- `__pycache__`
- `*.pyc`
- 根目录 `.codex` 运行态
- `plugins/codex-memory/storage/*.db`
- `plugins/codex-memory/storage/*.jsonl`

打包会包含 `plugins/codex-memory/skills/openai-curated/`、`plugins/codex-memory/skills/local/` 和 `plugins/codex-memory/skills/bundled-skills.json`，以便目标机器安装时不依赖 GitHub 网络。

用户安装流程：

```powershell
Expand-Archive .\codex-memory-harness-<VERSION>.zip -DestinationPath .\codex-memory-harness
cd .\codex-memory-harness
.\install.bat
```

已能调用 `powershell` 命令的 POSIX shell 用户可在解压后运行 `sh ./install.sh`。

## 14. 当前验证项

项目健康检查：

```powershell
codex package verify
```

检查内容：

- Python 编译。
- JSON 解析。
- 代码文件行数不超过 500。
- 安装器 `--check` 可运行。

doctor 检查：

```powershell
codex memory doctor
```

PowerShell wrapper 检查：

```powershell
codex memory doctor
codexm memory doctor
```

包内容检查：

- zip entries 正常。
- runtime memory 数据为 0。
- 缓存文件为 0。

## 15. 安全与隐私

默认本地运行，不上传数据。

禁止写入 memory：

- 密钥、令牌、密码、cookie。
- 私有内部链接。
- 原始敏感日志。
- 未经确认的个人身份信息。
- 大段版权受限原文。

建议写入：

- 决策摘要。
- 任务约束。
- 文件路径和变更摘要。
- 验证结论。
- 下一步。

## 16. 记忆检索策略

当前系统不依赖向量数据库。官方 Codex Memories 作为个人自动记忆兼容层存在，不替代 Harness 项目状态、验证 artifact 或团队共享层。基础检索使用：

- SQLite task state、repo decision、task summary。
- JSONL event log。
- Markdown summary 和 distilled asset。
- `rg` 路径、精确内容和全文检索。
- `context_builder.py` 的固定预算裁剪。

暂不默认启用向量库的原因：

- 保持本地离线安装和低依赖。
- 避免 embedding 前泄露密钥、日志、内部链接或 PII。
- 编码任务常依赖精确路径、符号和错误信息，关键词/路径检索更可解释。
- 向量索引需要增量更新、删除、重建、模型版本和召回解释机制。

当前 `retrieval_store.py` 已保留 `semantic` 占位接口，但不会假装可用。完整策略见：

```text
docs/MEMORY_RETRIEVAL_STRATEGY.md
```

## 17. 外部对标

本项目已按 Harness Engineering 思路落地本地 MVP，但没有宣称覆盖全部能力。外部资料对标、已实现能力、缺口和路线见：

```text
docs/EXTERNAL_BENCHMARK.md
```

## 18. 游戏客户端专项路线

针对 Unity、LayaBox/LayaAir、Cocos Creator 客户端项目，本仓库不直接内置引擎命令，而是建议业务项目通过 `.codex/harness/commands.json` 配置自己的验证 profile。

当前已经落地文档：

```text
docs/GAME_CLIENT_WORKFLOW.md
```

该路线吸收 BMAD Game Dev Studio 的 Quick Flow / Full Production、GDD、架构、story、QA、performance 工作流，也吸收 Claude-Code-Game-Studios 的游戏工作室角色、路径规则、hooks、质量门禁和会话状态思路。落地时收敛为客户端专项角色和 profile，不覆盖完整游戏工作室模板。

如果是单一游戏客户端仓库，当前优先使用 workspace 子命令生成模板：

```powershell
codex workspace game-client template --engine unity
codex workspace game-client init --engine unity --project-cwd client
codex workspace game-client init --engine laya --project-cwd client
codex workspace game-client init --engine cocos --project-cwd client
```

如果是多项目 workspace，更推荐 workspace 级自动路由：

```text
docs/WORKSPACE_ADAPTIVE_ROUTING.md
```

## 19. Workspace 自适应路由

当一个 workspace 同时包含游戏客户端、游戏服务器、后台应用、文档设计、美术工程和发布脚本时，路由对象不应该只是“引擎”，而应该是“子项目实例 + 任务域 + SubAgent scope”。

当前已经落地文档：

```text
docs/WORKSPACE_ADAPTIVE_ROUTING.md
```

推荐未来入口：

```powershell
codex workspace doctor
codex workspace route --task-file task.json
codex workspace route --changed
codex workspace verify --auto
```

workspace routing 会先形成 project inventory，再为当前任务生成 route plan。specialist SubAgent 绑定单个子项目 route，coordinator SubAgent 负责跨项目契约、验证聚合、冲突处理和最终 summary。

当前已经落地 `codex workspace doctor/scan/route/verify/bind/scope-check/summarize/schedule/game-client` 的最小本地运行时；仍未实现自动启动真实 SubAgent 和发布级完整验证平台。

详细任务拆分和进度见：

```text
docs/WORKSPACE_ROUTING_TASK_LIST.md
```

## 20. 完整开发流程图

如果所有规划能力都实现，日常开发流程会从用户输入任务开始，自动经过 bootstrap、memory 装载、workspace scanner、task router、SubAgent route binding、实现循环、AI 诊断日志、验证聚合、release gate 和 memory 沉淀。

完整目标流程和 Mermaid 图见：

```text
docs/FULL_DEVELOPMENT_WORKFLOW.md
```

该文档描述目标完整态，不代表当前 runtime 已全部具备。

## 21. AI 诊断日志策略

AI 写代码时需要运行反馈，因此项目允许在开发和 AI 调试阶段临时打开诊断日志。诊断日志必须通过统一门面和统一开关控制，不能散落裸 `print`、`console.log`、`Debug.Log` 或等价调用。

发布、生产、渠道包和正式热更构建必须关闭 AI 诊断日志。Release profile 应检查诊断开关、调试宏和临时 sink 均已关闭。

诊断日志不应写入 memory 原文。Harness artifact 只保存脱敏摘要、验证结论和下一步。

完整策略见：

```text
docs/AI_DIAGNOSTIC_LOGGING.md
```

## 22. 当前限制

- 不能修改模型内部记忆。
- 不能保证非 PowerShell 启动方式自动经过 wrapper。
- 旧 Codex 宿主是否自动读取插件 marketplace，仍取决于宿主能力。
- 当前检索是本地 MVP，尚未接入 embedding。
- 当前没有内建真实 SubAgent 自动执行器；已提供角色协作协议、artifact 记录、route binding、scope guard、coordinator summary 和 dispatch plan。
- 当前已内建 `codex workspace game-client init/template`，但没有顶层 `codex game-client ...` 独立入口，也不内置具体业务项目的引擎脚本。
- 当前没有内建发布级 workspace 平台；已提供只读 workspace scanner、只读 route planner、最小 workspace verification aggregation、SubAgent route binding、scope guard、coordinator summary、dispatch plan、memory lifecycle 软集成、project inventory、routing config、route plan 和验证聚合 schema，以及 `.codex/harness/workspace-routing.json` 模板。
- 当前已内建基础敏感信息扫描器和基础 AI 诊断日志 release gate；release gate 不覆盖所有平台构建配置和完整发布流水线。
- 当前已实现项目共享 memory 初始化模板、promote、validate 和索引重建的最小 runtime；严格 JSON Schema 校验和多人冲突自动处理尚未实现。
- 当前 workspace verifier 已支持每个 route 使用自己的 cwd/profile 聚合执行；发布级完整验证平台仍未实现。
- 当前 eval 回放体系尚未平台化。
- 全局 AGENTS 的旧未标记规则不会被强行改写。
- Bundled skills 固定到 manifest 记录的 upstream commit；更新技能需要重新 vendor 并更新 `skills/bundled-skills.json`。

## 23. 后续增强

优先级建议：

1. 敏感信息扫描器扩展：补 shared validate、索引重建和 release gate 专项检查。
2. `.codex/evals`：把失败任务和高价值任务转为可回放评测。
3. memory archive/cleanup：避免长期膨胀。
4. 项目共享 memory：严格 schema 校验、冲突策略和 review 辅助。
5. 真实 SubAgent 自动执行器：在宿主支持时按 dispatch plan 启动 specialist/coordinator，并回写超时、取消和失败状态。
6. Workspace memory 自动分层写入：把 workspace summary 与子项目事实按 semantic scope 分别沉淀。
7. 多项目业务模板生成器：补服务器、后台、文档、美术工程和发布脚本模板。
8. 发布级完整验证平台：覆盖渠道包、热更、构建产物、回滚材料和平台配置。
9. 可选本地语义检索：在不开启网络的前提下增强召回。
10. 安装器 dry-run：让用户安装前预览所有写入。

## 24. 一句话总结

Codex Memory Harness 是一套本地、可控、可打包安装的 Codex 外部记忆与任务运行时系统。它不改变模型内部能力，但通过 memory、context、harness、verification、distillation 和 PowerShell wrapper，把 Codex 的跨任务连续协作能力从“会话内临时上下文”提升为“本机可维护的工程化闭环”。
