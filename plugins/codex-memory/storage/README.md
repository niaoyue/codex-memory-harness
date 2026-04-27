# Storage

本目录用于保存 Codex 外脑插件的本地状态数据。

当前阶段约定的内容如下：

- `memory.db`: SQLite 数据库
- `events.jsonl`: 事件日志
- `summaries/`: 任务总结
- `distilled/`: 蒸馏资产

初始化由 `scripts/init_storage.py` 负责。
