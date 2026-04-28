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
py -X utf8 scripts\build_release.py
```

安装入口：

```powershell
.\install.ps1
```

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
| 9 | 打包分发层 | `build_release.py` 生成 zip，`install.ps1` 安装 |

## 5. 安装后的本机布局

全局插件入口：

```text
<USER_HOME>/plugins/codex-memory
```

全局规则：

```text
<USER_HOME>/.codex/AGENTS.md
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

项目级 memory：

```text
<PROJECT_ROOT>/.codex/memories
```

全局 memory：

```text
<USER_HOME>/.codex/memories
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
codex memory harness start --task-file task.json
codex memory harness checkpoint --task-id <TASK_ID> --result-file result.json
codex memory harness complete --task-id <TASK_ID> --summary-file summary.md
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
codex memory verify list
```

运行默认 profile：

```powershell
codex memory verify run --profile primary
```

绑定任务回写：

```powershell
codex memory verify run --task-id <TASK_ID> --profile primary
```

安全策略：

- 输出摘要有长度限制。
- 常见敏感字段会脱敏。
- 拒绝明显危险命令模式。
- 验证失败时返回结构化结果，而不是吞掉错误。

## 11. 安装器

核心安装器：

```text
plugins/codex-memory/scripts/install_codex_memory.py
```

顶层安装入口：

```powershell
.\install.ps1
```

旧安装迁移：

```powershell
.\install.ps1 -ReplaceExisting
```

卸载：

```powershell
.\uninstall.ps1
```

安装器行为：

- 默认优先创建 Windows junction。
- 如果目标已存在且指向其他目录，必须显式传入 `--replace-existing` 或 `-ReplaceExisting`。
- 替换旧普通目录时会备份，不直接删除。
- profile 和 AGENTS 采用标记块写入，降低误改用户内容的风险。
- 旧的未标记全局 AGENTS 规则会保留，不强行覆盖。

## 12. 打包分发

打包命令：

```powershell
py -X utf8 scripts\build_release.py
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

用户安装流程：

```powershell
Expand-Archive .\codex-memory-harness-<VERSION>.zip -DestinationPath .\codex-memory-harness
cd .\codex-memory-harness
.\install.ps1
```

## 13. 当前验证项

项目健康检查：

```powershell
py -X utf8 scripts\verify_project.py
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

## 14. 安全与隐私

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

## 15. 当前限制

- 不能修改模型内部记忆。
- 不能保证非 PowerShell 启动方式自动经过 wrapper。
- 旧 Codex 宿主是否自动读取插件 marketplace，仍取决于宿主能力。
- 当前检索是本地 MVP，尚未接入 embedding。
- 当前 eval 回放体系尚未平台化。
- 全局 AGENTS 的旧未标记规则不会被强行改写。

## 16. 后续增强

优先级建议：

1. `.codex/evals`：把失败任务和高价值任务转为可回放评测。
2. memory archive/cleanup：避免长期膨胀。
3. 敏感信息扫描器：写入前强制脱敏。
4. 多项目模板生成器：快速给项目接入 `.codex/harness`。
5. 可选本地语义检索：在不开启网络的前提下增强召回。
6. 安装器 dry-run：让用户安装前预览所有写入。

## 17. 一句话总结

Codex Memory Harness 是一套本地、可控、可打包安装的 Codex 外部记忆与任务运行时系统。它不改变模型内部能力，但通过 memory、context、harness、verification、distillation 和 PowerShell wrapper，把 Codex 的跨任务连续协作能力从“会话内临时上下文”提升为“本机可维护的工程化闭环”。
