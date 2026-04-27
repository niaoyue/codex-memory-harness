# Codex Memory Harness

Codex Memory Harness 是从业务项目中抽离出来的独立本地工具包，用于给 Codex 增加可控的外部记忆、任务运行时、验证闭环和蒸馏沉淀能力。

它不修改模型内部记忆，也不替换真实 `codex` 可执行文件。它通过本地插件、全局规则、PowerShell wrapper、项目级 `.codex` 配置和 memory/harness 脚本，让 Codex 在用户机器上获得更稳定的跨窗口协作能力。

## 能力边界

- 会话工作记忆：通过 `hook_runner.py` 维护当前任务状态、约束、工作集和下一步。
- 外部混合检索：通过 SQLite、事件日志、摘要文件和代码/文本检索构建上下文包。
- 提示层与上下文编排：通过 `before_task`、`before_response` 和 context budget 控制注入内容。
- 蒸馏写回：任务完成后沉淀 task summary 和 distilled asset。
- Harness 任务生命周期：通过 `harness_controller.py` 管理 `start`、`checkpoint`、`complete`。
- 验证回写：通过 `verification_runner.py` 执行配置化验证，并把结果写入 harness artifact。
- 无感启动：通过 PowerShell profile 中的 `codex` / `codexm` 函数先执行 bootstrap/doctor，再启动真实 Codex。

## 安装

在项目根目录运行：

```powershell
.\install.ps1
```

如果当前机器已经有旧的 `C:\Users\<你>\plugins\codex-memory` 指向其他目录，需要迁移到本项目：

```powershell
.\install.ps1 -ReplaceExisting
```

如果希望同时写入 PowerShell 7 和 Windows PowerShell profile：

```powershell
.\install.ps1 -ProfileShells all -ReplaceExisting
```

安装脚本会做这些事：

- 把 `~/plugins/codex-memory` 指向本项目的 `plugins/codex-memory`，默认优先创建 Windows junction，失败时可回退复制。
- 更新 `~/.agents/plugins/marketplace.json`。
- 更新当前仓库 `.agents/plugins/marketplace.json`。
- 向 `~/.codex/AGENTS.md` 写入全局 Codex Memory 使用规则，已有旧规则时默认保留，避免覆盖用户内容。
- 向 PowerShell profile 写入 `codex`、`codexm`、`codex-raw`、`codex-memory-doctor` 函数。

## 使用

普通启动：

```powershell
codex
```

显式 memory 启动：

```powershell
codexm
```

诊断当前窗口：

```powershell
codex-memory-doctor
```

绕过 memory wrapper：

```powershell
codex-raw
```

项目初始化或诊断：

```powershell
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\codex_bootstrap.py --cwd <项目目录> --doctor
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\codex_bootstrap.py --cwd <项目目录> --init-project
```

## 打包

生成可分发 zip：

```powershell
py -X utf8 scripts\build_release.py
```

输出位置：

```text
dist/codex-memory-harness-0.1.0.zip
```

用户拿到 zip 后解压，然后运行：

```powershell
.\install.ps1
```

如果用户机器已有旧安装：

```powershell
.\install.ps1 -ReplaceExisting
```

## 验证

项目健康检查：

```powershell
py -X utf8 scripts\verify_project.py
```

插件安装状态检查：

```powershell
py -X utf8 plugins\codex-memory\scripts\install_codex_memory.py --check
```

编译插件 Python 文件：

```powershell
py -X utf8 -c "import py_compile, pathlib; [py_compile.compile(str(p), doraise=True) for p in pathlib.Path('plugins/codex-memory').rglob('*.py') if '__pycache__' not in p.parts]; print('compile-ok')"
```

## 卸载

只移除 marketplace、PowerShell profile 标记块和全局 AGENTS 标记块：

```powershell
.\uninstall.ps1
```

同时移除 `~/plugins/codex-memory`：

```powershell
.\uninstall.ps1 -RemoveHomePlugin
```

卸载不会删除任何项目内 `.codex/memories` 数据，也不会删除用户已经写入的项目记忆。

## 目录结构

```text
plugins/codex-memory/        核心插件、hooks、MCP、memory、harness、verification 脚本
scripts/build_release.py     打包 zip
scripts/verify_project.py    项目健康检查
docs/                        系统总结、用户指南、隐私说明和历史计划
templates/                   repo/project 接入模板
install.ps1                  用户安装入口
uninstall.ps1                用户卸载入口
```

## 维护原则

- 不修改真实 Codex 安装文件，只通过 profile wrapper 接入。
- 默认项目级 memory，只有跨项目偏好或用户明确要求才写全局 memory。
- 不写入密钥、令牌、敏感日志或内部链接。
- 所有写入使用 UTF-8 无 BOM。
- 代码文件保持小模块，单文件硬上限 500 行。
- 打包产物不包含根目录 `.codex` 运行态、`dist`、`memory.db`、`events.jsonl`、`__pycache__` 和 `.pyc`。

更多细节见：

- `docs/USER_GUIDE.md`
- `docs/PRIVACY.md`
- `docs/codex-memory-harness-system-summary.md`
