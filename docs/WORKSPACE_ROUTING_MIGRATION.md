# Workspace Routing 迁移说明

本文说明如何把已有 Codex Memory Harness 项目升级到 workspace routing。它只覆盖本地 harness 配置、业务模板和验证路由，不会修改业务源码、真实 Codex CLI 文件或用户项目记忆内容。

## 1. 适用场景

适合升级的项目包括：

- 单仓多项目 workspace，例如客户端、服务器、后台、文档、美术和发布脚本共用一个仓库。
- 已经使用 `codex memory init` 或存在 `.codex/harness/commands.json`、`.codex/harness/project_profile.json` 的项目。
- 需要让 route plan、SubAgent binding、scope guard 和 workspace verify 按子项目区分作用域的项目。

不适合直接升级的情况：

- 项目还没有明确子项目边界。
- 业务验证命令尚未确定。
- 配置中需要写入密钥、令牌、内部链接或敏感路径。

## 2. 升级步骤

第一步，确认当前项目 harness 状态：

```powershell
codex memory doctor
```

如果缺少 `.codex/harness` 基础配置，先初始化：

```powershell
codex memory init
```

第二步，按业务域生成模板。游戏客户端仍使用专项入口：

```powershell
codex workspace game-client init --engine unity --project-cwd client --profile-prefix client
```

服务器、后台、文档和美术工程使用通用业务模板入口：

```powershell
codex workspace project-template init --domain game_server --project-cwd server --profile-prefix server --language go
codex workspace project-template init --domain backoffice_web --project-cwd admin --profile-prefix admin --framework vue
codex workspace project-template init --domain design_docs --project-cwd docs --profile-prefix docs
codex workspace project-template init --domain art_pipeline --project-cwd art --profile-prefix art
```

这些命令会合并写入：

- `.codex/harness/commands.json`
- `.codex/harness/project_profile.json`
- `.codex/harness/workspace-routing.json`

默认不会覆盖同名 command、profile 或 project。需要替换已有模板时显式加 `--overwrite`。

第三步，检查 workspace inventory 和 route plan：

```powershell
codex workspace scan
codex workspace route --objective "release server and admin" --working-set server --working-set admin
```

第四步，先做 no-run 聚合，确认 profile 和 command 名称没有缺口：

```powershell
codex workspace verify --objective "release server and admin" --working-set server --working-set admin --no-run
```

第五步，再运行真实验证：

```powershell
codex workspace verify --objective "release server and admin" --working-set server --working-set admin
```

## 3. 模板边界

业务模板只提供可编辑的默认 commands、profiles 和 routing project 配置。

它不会：

- 替业务项目生成 Unity Editor 脚本、Go/Java/C#/Node 服务代码、前端页面、发布流水线或美术导入脚本。
- 自动启动真实 SubAgent。
- 自动把 workspace summary 或子项目事实写入长期 shared memory。
- 绕过 release gate、scope guard 或敏感信息扫描。

它会：

- 为服务器生成 unit、integration、release profile 示例。
- 为后台/Web 生成 lint、test、build profile 示例。
- 为文档生成 UTF-8 和本地 Markdown 链接检查 profile 示例。
- 为美术工程生成资产清单摘要和零字节资产 release 检查 profile 示例。
- 把对应 project 写入 workspace routing config，供 scanner、router、workspace verify 和 SubAgent binding 使用。

## 4. 发布前检查

升级完成后，至少执行：

```powershell
codex workspace scan
codex workspace route --changed
codex workspace verify --changed --no-run
codex package verify
```

发布任务必须确认：

- release route 的 AI 诊断日志 gate 没有阻断项。
- `verification_aggregation.gaps` 为空，或每个 gap 都有明确计划。
- `.codex/memories/`、`.codex/harness/tasks/`、数据库、JSONL 和缓存文件没有进入发布包。
- 业务模板里的示例命令已经替换为项目真实命令，或明确保留为可执行默认命令。

## 5. 回退方式

如果新路由影响当前工作流，可以按最小回退处理：

- 从 `.codex/harness/project_profile.json` 删除新增 verification profile。
- 从 `.codex/harness/commands.json` 删除新增 command。
- 从 `.codex/harness/workspace-routing.json` 删除新增 project。
- 保留 `.codex/memories` 和 `.codex/shared`，不要删除用户记忆。

回退后重新运行：

```powershell
codex memory doctor
codex workspace scan
```

确认 workspace routing 回到预期状态。
