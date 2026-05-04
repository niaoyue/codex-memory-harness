# Repository Guidelines

## 必读要点

- 输出统一使用中文。
- 回复开头必须有“前置说明”；如果发生工具调用，末尾补“工具调用简报”。
- 编码前先做 `Sequential-Thinking 分析`，并坚持最小必要改动边界。
- 读写文件统一使用 UTF-8（无 BOM）。
- 禁止危险命令、泄露密钥、上传敏感信息。
- 所有 SubAgent 都不得设置固定总时长；宿主 `wait_agent` 或类似 API 的 timeout 只能作为本次观察窗口，窗口到期后继续观察，不得仅因观察窗口到期而中断、关闭或判失败。只要 SubAgent 有输出、checkpoint、状态更新或可见进度，就视为仍在运行。
- 代码审核优先使用 `codex xhigh review --uncommitted` 作为最终 review gate；大 diff 或长耗时审查优先派发 XHigh Review Runner SubAgent 作为并行命令执行器运行该 gate，等待策略按 stdout/stderr 进度输出观察，不使用固定总时长超时，也不得再用 10 分钟外层总时长包住 runner。通用 SubAgent reviewer 只做窄范围专题/旁路审查，不替代 Codex CLI xhigh review。
- 代码 review findings 全部修复、最终 review gate 无阻断问题且验证通过后，必须在本地创建一个 git commit 记录当前版本；若工作树包含用户无关改动，必须只提交本轮相关文件或先说明无法安全提交。
- 用户明确选择 SubAgent、分角色或并行代理，任务属于复杂/应用级/多阶段实现，项目 `.codex/harness/project_profile.json` / `.codex/harness/workspace-routing.json` 的 `subagent_runtime_policy` 授权正式 implementation 任务，或通用 planner 基于 `task_intent/task_type/risk_level/complexity` 判定需要派发时，主 Agent 必须读取 `metadata.workspace_routing.subagent_runtime` 与 `subagent_dispatch_plan.host_spawn_requests`；当 `host_dispatch_allowed=true` 且宿主提供 SubAgent 工具时，按请求派发宿主 SubAgent，否则记录降级原因并由主 Agent 串行执行。
- 涉及任务编排、待办、里程碑和状态跟踪时优先使用 `shrimp-task-manager`；当前环境不可用时，明确降级到本地 Markdown。
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
- 只通过 `~/plugins/codex-memory`、`~/.agents/plugins/marketplace.json`、`$CODEX_HOME/config.toml`、`~/.codex/AGENTS.md` 和 PowerShell profile 接入。
- 替换旧 `~/plugins/codex-memory` 必须显式使用 `--replace-existing` 或 `-ReplaceExisting`。
- 卸载脚本默认不删除用户项目里的 `.codex/memories`。
