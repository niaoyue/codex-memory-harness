# Repository Guidelines

## 必读要点

- 输出统一使用中文。
- 回复开头必须有“前置说明”；如果发生工具调用，末尾补“工具调用简报”。
- 编码前先做 `Sequential-Thinking 分析`，并坚持最小必要改动边界。
- 读写文件统一使用 UTF-8（无 BOM）。
- 禁止危险命令、泄露密钥、上传敏感信息。
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
- 只通过 `~/plugins/codex-memory`、`~/.agents/plugins/marketplace.json`、`~/.codex/AGENTS.md` 和 PowerShell profile 接入。
- 替换旧 `~/plugins/codex-memory` 必须显式使用 `--replace-existing` 或 `-ReplaceExisting`。
- 卸载脚本默认不删除用户项目里的 `.codex/memories`。
