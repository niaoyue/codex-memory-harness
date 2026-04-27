# Codex Memory Harness 独立项目任务清单

说明：本任务按规则应优先使用 `shrimp-task-manager`。当前环境没有可用的 shrimp 工具入口，因此降级为本地 Markdown 任务清单。

## 已完成

- [x] 在 `H:\dev\company` 下创建独立项目目录 `codex-memory-harness`。
- [x] 从原业务项目复制通用 `plugins/codex-memory` 源码。
- [x] 排除 `__pycache__`、`.pyc`、`memory.db`、`events.jsonl`、`summaries`、`distilled` 和 harness runtime tasks。
- [x] 迁移历史总结、执行计划和任务清单到 `docs/`。
- [x] 增加顶层 `.gitignore`。
- [x] 升级插件 manifest，移除 TODO 元数据。
- [x] 增强安装器：支持 home plugin、marketplace、全局 AGENTS、PowerShell profile、doctor check、卸载和旧安装迁移。
- [x] 拆分安装支持模块，保证代码文件不超过 500 行。
- [x] 增加 `install.ps1` 和 `uninstall.ps1`。
- [x] 增加 `scripts/build_release.py` 生成可分发 zip。
- [x] 增加 `scripts/verify_project.py` 项目健康检查。
- [x] 增加 `README.md`、`docs/USER_GUIDE.md`、`docs/PRIVACY.md`。

## 验证结果

- [x] 运行项目健康检查。
- [x] 运行 bootstrap 初始化新项目 `.codex/harness`。
- [x] 运行安装器 `--check`。
- [x] 构建 release zip。
- [x] 检查 zip 不包含 runtime memory 数据和缓存。

## 当前注意事项

- 当前机器的 `C:\Users\<USER>\plugins\codex-memory` 已可通过 `.\install.ps1 -ReplaceExisting` 迁移到独立项目。
- 迁移后所有加载当前用户 PowerShell profile 的新 Codex 窗口都会使用独立项目入口。

## 后续增强

- [ ] 增加 `.codex/evals` 失败任务回放。
- [ ] 增加 memory archive/cleanup。
- [ ] 增加强制脱敏扫描器。
- [ ] 增加多项目模板生成器。
- [ ] 增加可选本地语义检索接口。
