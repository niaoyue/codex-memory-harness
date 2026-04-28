# 隐私与数据边界

Codex Memory Harness 是本地工具包，默认不上传数据，不调用网络服务，不把 memory 数据发送到外部。

## 本地写入位置

项目私有层：

```text
<项目根目录>/.codex/memories
```

用户全局层：

```text
C:\Users\<你>\.codex\memories
```

项目共享层：

```text
<项目根目录>/.codex/shared
```

用户全局层和项目私有层默认不上传。项目共享层可以进入 Git，但必须只保存脱敏、稳定、经过 review 的团队事实。

PowerShell profile：

```text
C:\Users\<你>\Documents\PowerShell\Microsoft.PowerShell_profile.ps1
C:\Users\<你>\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1
```

插件入口：

```text
C:\Users\<你>\plugins\codex-memory
```

## 不应写入 memory 的内容

- 密钥、令牌、密码、cookie。
- 内部链接、私有仓库地址、生产环境地址。
- 原始敏感日志。
- 未经用户确认的个人身份信息。
- 大段原文或版权受限内容。
- 渠道包密钥、支付配置、SDK secret、CDN 凭证和发布签名材料。
- 原始美术源文件内容、未压缩商业素材、可还原资产的长片段或二进制摘要。

## 写入原则

- 只写任务需要的最小摘要。
- 优先写结构化事实、决策、约束、下一步。
- raw 项目任务状态默认留在项目私有层。
- 跨项目个人偏好才写用户全局层。
- 团队共享事实必须提升到项目共享层，不能直接提交 `.codex/memories`。
- 验证输出应做长度裁剪和敏感字段脱敏。

## 三层记忆隐私边界

| 层级 | 隐私边界 | 禁止内容 |
|---|---|---|
| 用户全局层 | 当前用户本机私有，不上传 | 项目内部事实、生产地址、私有仓库、密钥 |
| 项目私有层 | 当前项目本机 raw 运行态，不提交 | 密钥、完整日志、低置信结论的共享化 |
| 项目共享层 | 可提交但必须 review | 原始日志、原始资产、token、生产域名、未验证结论 |

项目共享层适合写入架构决策、模块边界、验证规则、发布流程和跨项目契约。它应使用 Markdown 和结构化 metadata，避免 SQLite、JSONL 或大文件进入 Git。

## Workspace 路由边界

Workspace 自适应路由会读取目录结构、配置文件名、变更路径和验证 profile，用于判断当前任务涉及哪些子项目。Scanner 必须保持只读，不复制原始资产，不上传文件内容，也不把业务仓库的内部链接、生产地址或渠道信息写入记忆。

Route plan 可以记录：

- `workspace_id`、`project_id`、`domain`、`cwd`、`assigned_scope`。
- 路由置信度、识别信号摘要、验证 profile 名称。
- 跨项目契约、发布顺序、回滚策略的最小摘要。

Route plan 不应记录：

- 密钥、令牌、生产域名、私有仓库地址。
- 原始策划表、原始美术资产、完整构建日志。
- 可复现商业素材或渠道包配置的细节。

Memory 写入应分层：

- workspace 级 memory 只写跨项目契约、综合事务 summary、route plan 摘要。
- 子项目 memory 只写该项目相关事实，必须带 `project_id`、`domain` 和 scope。
- 低置信度识别只写判断依据和不确定性，不能写成确定事实。

## 网络边界

本项目核心脚本不需要网络。若未来增加 embedding、远程同步或云端评测，必须默认关闭，并提供显式配置、脱敏策略和回退路径。
