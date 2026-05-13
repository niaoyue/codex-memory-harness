# Repository Guidelines

## 必读要点

- 输出统一使用中文。
- 回复开头必须有“前置说明”；如果发生工具调用，末尾补“工具调用简报”。
- 编码前先做 `Sequential-Thinking 分析`，并坚持最小必要改动边界。
- 读写文件统一使用 UTF-8（无 BOM）。
- DEBUG 日志是一等验证依据：新增或修改功能时必须补充足够可定位的 DEBUG 级日志，后续测试验证要能依赖这些日志判断关键分支、输入输出摘要、降级原因、状态转换和完成结果是否符合预期；日志必须最小化，不得记录密钥、令牌、隐私数据、内部链接或完整敏感载荷。
- 禁止危险命令、泄露密钥、上传敏感信息。
- 所有 SubAgent 都不得设置固定总时长；宿主 `wait_agent` 或类似 API 的 timeout 只能作为本次观察窗口，窗口到期后继续观察，不得仅因观察窗口到期而中断、关闭或判失败。只要 SubAgent 有输出、checkpoint、状态更新或可见进度，就视为仍在运行。
- 代码审核采用候选提交后 review：验证通过并确认提交边界后，先在本地创建一个只包含本轮相关文件的 candidate commit，并立即记录被审提交 SHA（通常是 `git rev-parse HEAD`）。最终 gate 使用 Review a commit：`codex xhigh review --commit <commit-sha>`，只审核该提交引入的变更，不能用 `--base` 把整个候选范围反复送审；大 diff 或长耗时审查优先派发 XHigh Review Runner SubAgent 作为并行命令执行器运行该 gate，等待策略按 stdout/stderr 进度输出观察，不使用固定总时长超时，也不得再用 10 分钟外层总时长包住 runner。runner 遇到模型容量、429、5xx 或超时类基础设施错误时，如果宿主持有仍活跃的 runner session，必须先按类型退避并对同一 session 发送继续指令：容量/429 退避 20 秒且只要 session 活跃就可继续，5xx/超时退避 2 秒且最多续跑一次；只有 session 已关闭、无句柄、不可恢复或被审提交 ref 变化时，才重新启动同一个 review gate。通用 SubAgent reviewer 只做窄范围专题/旁路审查，不替代 Codex CLI xhigh review。
- 如果 review 本次提交发现阻断问题，必须修复后创建新的本地提交（或在尚未 push 前重做候选提交），再 review 新提交本身；重复“提交 -> review 该提交 -> 修复 -> 再提交 -> review 新提交”，直到 review 没有新的阻断问题后才允许 push。若工作树包含用户无关改动，必须只提交本轮相关文件或先说明无法安全提交。
- 用户明确选择 SubAgent、分角色或并行代理，任务属于复杂/应用级/多阶段实现，项目 `.codex/harness/project_profile.json` / `.codex/harness/workspace-routing.json` 的 `subagent_runtime_policy` 授权正式 implementation 任务，或通用 planner 基于 `task_intent/task_type/risk_level/complexity` 判定需要派发时，主 Agent 必须读取 `metadata.workspace_routing.subagent_runtime` 与 `subagent_dispatch_plan.host_spawn_requests`；当 `host_dispatch_allowed=true` 且宿主提供 SubAgent 工具时，按请求派发宿主 SubAgent，否则记录降级原因并由主 Agent 串行执行。
- 涉及任务编排、待办、里程碑和状态跟踪时优先使用 `shrimp-task-manager`；当前环境不可用时，明确降级到本地 Markdown。
- 默认采用 skill-first 工作流：任务开始先按 `docs/SKILL_ROUTING_AND_DEFAULT_GOVERNANCE.md` 匹配可用技能；需求/策划文档用 `grill-me` 风格提出不确定、逻辑混乱和逻辑错误清单，能通过本地代码和文档自答的先补齐，不能自答的反馈用户；创建接口、协议、schema、CLI 或跨模块契约前优先用 `design-an-interface` 形成多个接口方向。
- Codex 自己生成的需求、设计、任务、PRD、RFC、change spec 和执行计划等持久规划文档，默认写入 `.codex/specs/<feature-slug>/requirements.md`、`design.md`、`tasks.md`；`docs/` 只放用户可读或长期公开项目文档，`.codex/memories`、`.codex/harness/tasks` 和事件/数据库/缓存仍为运行态，不提交。
- 输出未完成 Task 汇总时，必须为每个未完成 Task 附带进度：状态、最近 checkpoint 或更新时间、已完成/剩余验收、阻塞点、下一步和证据来源；缺证据时标记 `unknown`，不得猜测百分比。
- 需求被拆成多任务时，先分析依赖、决策、环境、接口和验证卡点；除非所有任务都被同一类阻塞卡住，否则按依赖关系使用多 SubAgent 并行推进。每个 SubAgent 必须有明确 scope、cwd、规则、验收和 forbidden paths，并按 harness checkpoint 回写结果。
- 策划需求默认进入完整性审查：目标、状态、边界、异常、验收、多语言、多平台、WebGL/小游戏、性能、包体、安全、迁移和回滚缺口都要列出。技术选择默认支持多语言和全平台，重点考虑 WebGL/小游戏兼容、性能和包体；优先现有约定和官方库，但如果官方方案在关键指标上比第三方稳定方案差约 20% 以上且第三方 license/安全/维护可接受，应优先第三方。避免为抽象而过度封装，模块要可拆卸、可选择性编译和容易裁剪。
- 游戏/客户端资源管理默认限制依赖扩散：一个业务预制体优先只依赖本模块 AB 包，最多再依赖一个公共 AB 包；跨模块公共资源必须有 owner、版本、影响范围和回滚策略。
- 代码文件理想 200-300 行，硬上限 500 行；超过上限必须拆分。
- 默认正确性优先于兼容性。必要时直接替换旧接口，但必须在文档中说明迁移方式。

## 项目定位

本项目是 Codex Memory / Harness 的独立分发项目，不属于任何业务项目。不要把业务项目上下文、历史任务运行态、敏感日志或私有数据写入本仓库。

## 打包边界

打包产物必须排除：

- `.codex/memories/`
- `.codex/harness/tasks/`
- `plugins/codex-memory/storage/*.db`
- `plugins/codex-memory/storage/*.jsonl`
- `__pycache__/`
- `*.pyc`
- `dist/`

## 安装边界

- 不修改真实 Codex CLI 文件。
- 只通过 `~/plugins/codex-memory`、`~/.agents/plugins/marketplace.json`、`$CODEX_HOME/config.toml`、`~/.codex/AGENTS.md`、PowerShell profile 和 `~/.agents/skills/<skill-name>` 接入。
- 替换旧 `~/plugins/codex-memory` 必须显式使用 `--replace-existing` 或 `-ReplaceExisting`。
- 卸载脚本默认不删除用户项目里的 `.codex/memories`。
- 卸载脚本默认不删除 `~/.agents/skills` 中的技能目录。
