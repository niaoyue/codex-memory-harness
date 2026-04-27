# Hooks

本目录用于放置插件自动触发逻辑的定义与实现。

计划中的钩子包括：

- `on_session_start`
- `before_task`
- `after_tool`
- `before_response`
- `on_task_complete`

当前阶段的自动化入口由以下文件提供：

- `../hooks.json`: 事件到 runner 的映射
- `../scripts/hook_bridge.py`: 将 Codex 插件 hook 事件桥接到内部记忆事件
- `../scripts/hook_runner.py`: 统一事件执行器
- `../scripts/run_demo_flow.py`: 本地验收脚本

失败降级策略：

- hook 执行异常时返回结构化 `degraded` 响应
- `before_task` / `before_response` 退化为最小 `context pack`
- `on_task_complete` 退化为最小总结输出

当前 `hooks.json` 已按 Codex 插件示例格式对齐，优先接住 `PostToolUse`，其余开始/结束阶段则通过仓库 `AGENTS.md` 中的默认工作流兜底。
