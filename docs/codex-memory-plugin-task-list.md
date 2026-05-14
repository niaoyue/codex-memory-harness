# Codex 外脑插件任务清单

> 迁移说明：这份 Codex 生成的任务/进度清单已经迁移到 `.codex/harness/backlog/tasks.md`。

`docs/` 只保留这个兼容入口，避免旧链接失效。后续维护主任务清单、未完成 Task 进度、Step 记录和 HarnessTest dogfood 证据时，请更新：

```text
.codex/harness/backlog/tasks.md
```

运行时 `unfinished_task_summary.py` 默认优先读取该 Harness backlog；仅在目标项目没有 `.codex/harness/backlog/tasks.md` 时回退到这个旧路径。这不是正式 OpenSpec spec 层；正式规格与 change contract 位于 `openspec/`。
