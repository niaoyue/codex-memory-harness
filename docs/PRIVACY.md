# 隐私与数据边界

Codex Memory Harness 是本地工具包，默认不上传数据，不调用网络服务，不把 memory 数据发送到外部。

## 本地写入位置

项目级 memory：

```text
<项目根目录>/.codex/memories
```

全局 memory：

```text
C:\Users\<你>\.codex\memories
```

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

## 写入原则

- 只写任务需要的最小摘要。
- 优先写结构化事实、决策、约束、下一步。
- 项目事实默认留在项目 memory。
- 跨项目偏好才写全局 memory。
- 验证输出应做长度裁剪和敏感字段脱敏。

## 网络边界

本项目核心脚本不需要网络。若未来增加 embedding、远程同步或云端评测，必须默认关闭，并提供显式配置、脱敏策略和回退路径。
