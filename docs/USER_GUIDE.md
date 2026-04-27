# 用户指南

## 一句话说明

Codex Memory Harness 让 Codex 在本机获得可控的外部记忆和任务运行时能力。用户正常使用时只需要继续输入 `codex`，不需要手动维护记忆。

## 首次安装

```powershell
cd H:\dev\company\codex-memory-harness
.\install.ps1
```

如果安装器提示 `Home plugin already points elsewhere`，说明机器上已经有旧版本或旧项目的 `codex-memory`：

```powershell
.\install.ps1 -ReplaceExisting
```

这会把 `~/plugins/codex-memory` 迁移到当前项目。它不会修改真实 Codex CLI 文件。

## 日常使用

```powershell
codex
```

`codex` 会先经过 PowerShell profile 注册的 wrapper，执行 bootstrap/doctor，然后启动真实 Codex。

可用入口：

- `codex`：普通无感入口。
- `codexm`：显式 memory wrapper 入口。
- `codex-memory-doctor`：只检查当前窗口接入状态，不启动 Codex。
- `codex-raw`：绕过 memory wrapper，直接启动真实 Codex。

## 项目接入

进入任意项目目录后运行：

```powershell
codex-memory-doctor
```

如果项目缺少 `.codex/memories` 或 `.codex/harness`，正常启动 `codex` 时 wrapper 会自动初始化。也可以显式执行：

```powershell
py -X utf8 C:\Users\<你>\plugins\codex-memory\scripts\codex_bootstrap.py --cwd <项目目录> --init-project
```

项目会获得：

- `.codex/memories/`
- `.codex/harness/commands.json`
- `.codex/harness/project_profile.json`

## 记忆分层

默认写项目级 memory：

```text
<项目根目录>/.codex/memories
```

只有这些内容才应写全局 memory：

- 跨项目长期偏好。
- 反复复用的个人工作流。
- 用户明确要求全局沉淀的规则。

全局 memory 位置：

```text
C:\Users\<你>\.codex\memories
```

## 打包给别人

维护者在项目根目录运行：

```powershell
py -X utf8 scripts\build_release.py
```

把 `dist/codex-memory-harness-0.1.0.zip` 发给用户。用户解压后运行：

```powershell
.\install.ps1
```

发布包不会包含维护者本机的根目录 `.codex` 运行态；用户项目的 `.codex/memories` 和 `.codex/harness` 由 bootstrap 在目标机器上初始化。

## 验证安装

```powershell
py -X utf8 plugins\codex-memory\scripts\install_codex_memory.py --check
codex-memory-doctor
```

`--check` 只读检查，不会写文件。

## 回退

临时绕过：

```powershell
codex-raw
```

禁用当前命令中的 wrapper：

```powershell
$env:CODEX_MEMORY_DISABLE_WRAPPER = "1"
codex
```

卸载 profile 和 marketplace 接入：

```powershell
.\uninstall.ps1
```

卸载不会删除项目 memory。需要删除某个项目的 memory 时，由用户手动处理对应项目的 `.codex/memories`，不要由自动脚本递归删除。
