# AI 诊断日志策略

## 1. 目的

AI 写代码时需要可观察性。很多流程、状态机、资源加载、网络分支和平台差异，单靠静态阅读很难判断是否正确。

因此项目应允许在开发和 AI 调试阶段临时打开诊断日志，让 Codex 能根据运行反馈修正判断。

但诊断日志不是发布能力。发布、生产、渠道包和正式热更构建必须默认关闭，并在 release gate 中检查。

## 2. 定义

AI 诊断日志是面向开发者和 AI 代理的短期观测信号，用来说明流程是否进入预期分支、关键状态是否改变、验证输入输出摘要是否符合预期。

它不同于业务运行日志、审计日志、埋点日志和崩溃日志。它不承诺长期保留，也不应该进入生产观测体系。

## 2.1 DEBUG 日志验证规则

DEBUG/AI 诊断日志是一等验证依据，不是可选装饰。新增或修改功能时，必须补充足够可定位的 DEBUG 级诊断点，让测试验证能够根据日志判断关键分支、输入输出摘要、降级原因、状态转换和完成结果是否符合预期。

验证阶段不能只依赖静态阅读或最终返回值。对状态机、任务编排、路由、SubAgent 调度、安装/卸载、降级路径、资源加载、网络摘要和 release gate 等流程，diagnostic profile 或本地调试运行应能输出脱敏摘要，证明功能按预期路径执行。

如果缺少必要 DEBUG/AI 诊断日志，验证结论必须标记为不完整，并优先补日志或补 diagnostic profile，再继续判断功能是否完善。Release profile 仍必须确认这些诊断开关关闭，不能把调试观测能力带入正式构建。

## 3. 核心原则

- 必须有统一开关，不能散落在多个脚本、组件或模块里。
- 必须经过统一封装，不能随手写裸 `print`、`console.log`、`Debug.Log` 或等价调用。
- 本地开发和 AI 调试可以开启。
- CI 默认关闭，除非运行专门的 diagnostic profile。
- Release、生产构建、渠道包和正式热更必须关闭。
- 关闭时应低成本，避免仍然拼接字符串、序列化 JSON 或扫描大对象。
- 日志只写最小摘要，不写密钥、令牌、生产地址、完整 payload、原始资源或个人信息。

## 4. 推荐配置抽象

不同技术栈可以有不同实现，但应收敛到同一类配置语义：

```text
ai_diagnostics.enabled
ai_diagnostics.level
ai_diagnostics.scopes
ai_diagnostics.sink
ai_diagnostics.release_must_be_disabled
```

项目配置示例：

```json
{
  "ai_diagnostics": {
    "enabled_by_default": false,
    "local_override": true,
    "release_must_be_disabled": true,
    "scopes": ["flow", "state", "network_summary", "asset_loading"],
    "forbidden_fields": ["token", "password", "secret", "cookie", "authorization"]
  }
}
```

这只是语义示例，不要求所有项目使用同一个文件名。业务项目可以放在自己的 `.codex/harness`、应用配置、构建配置或引擎设置里。

## 5. 开关矩阵

| 场景 | 默认策略 | 说明 |
|---|---|---|
| 本地开发 | 可开启 | 用于复现、定位流程和验证假设 |
| AI 代码任务 | 可临时开启 | 诊断点应有 scope、feature 或 task 标记 |
| CI quick profile | 默认关闭 | 需要时单独跑 diagnostic profile |
| CI diagnostic profile | 可开启 | 输出应被裁剪并做敏感字段过滤 |
| Release profile | 必须关闭 | 检查失败应阻断发布 |
| 生产构建 | 必须关闭 | 不允许携带 AI 诊断 sink 或调试宏 |

## 6. 日志内容规范

推荐记录：

- 关键流程进入和退出。
- 状态机状态变化。
- 配置选择结果的摘要。
- 资源加载、热更新、网络请求的结果摘要。
- 验证输入、输出和分支判断的脱敏摘要。
- 性能敏感点的计数、耗时和阈值结果。

禁止记录：

- token、password、secret、cookie、authorization。
- 生产域名、内部仓库地址、渠道签名、支付配置。
- 完整请求体、完整响应体、完整策划表、完整资源内容。
- 原始美术资产、二进制摘要、可还原素材片段。
- 未经确认的个人身份信息。

## 7. 代码接入要求

业务代码应依赖统一门面，例如：

```text
DiagnosticLog
AiDiagnosticLogger
ProjectLogger.Diagnostics
```

门面至少需要支持：

- `enabled` 判断。
- `scope` 或 `tag`。
- 按级别过滤。
- 敏感字段过滤。
- 发布构建硬关闭。
- 关闭时避免执行昂贵参数构造。

禁止把 AI 诊断日志和业务 logger 深度耦合。业务 logger 可以作为 sink，但 AI 诊断开关必须能独立关闭。

## 8. 游戏客户端建议

### Unity

Unity 项目可以通过 Scripting Define Symbols、构建配置、ScriptableObject 配置或运行时 debug menu 控制诊断开关。

正式构建时必须禁用 AI diagnostic define。涉及 Addressables、热更新、支付、登录、SDK、渠道包和生产网络的日志必须只输出脱敏摘要。

性能敏感路径应优先使用编译期裁剪或延迟参数构造，避免关闭日志后仍产生 GC。

### LayaBox / LayaAir

Laya 项目可以通过构建环境变量、编译常量、发布脚本参数或启动配置控制诊断开关。

发布到小游戏平台、渠道包或正式 Web 包时，诊断日志必须关闭，且构建脚本应检查没有 diagnostic sink 指向公开控制台或远端地址。

### Cocos Creator

Cocos 项目可以通过构建配置、宏定义、启动参数或项目配置控制诊断开关。

Asset Bundle、热更新、原生平台构建和小游戏构建都应有 release gate，确认诊断开关关闭且没有裸日志绕过统一门面。

## 9. Workspace 路由要求

在多项目 workspace 中，诊断日志策略应按 route plan 分配，而不是全局一刀切。

Specialist SubAgent 只允许为自己的 route binding 申请诊断 scope。Coordinator 负责汇总哪些子项目临时开启过诊断日志，并在最终验证中确认 release profile 已全部关闭。

推荐 route plan 增加：

```json
{
  "diagnostic_logging": {
    "allowed": true,
    "required_scopes": ["flow", "state"],
    "release_must_be_disabled": true
  }
}
```

综合发版或 release train 中，任何子项目诊断日志未关闭，都应标记为 blocking issue。

## 10. Verification Profile 建议

建议业务项目配置两个不同方向的检查：

| Profile | 用途 | 期望 |
|---|---|---|
| `diagnostic` | AI 调试期观测 | 可开启指定 scope，输出脱敏摘要 |
| `release` | 发布前检查 | 诊断开关关闭，调试宏关闭，无裸日志绕过 |

Release profile 至少检查：

- `ai_diagnostics.enabled` 为 false。
- release 构建没有 diagnostic define、debug flag 或临时启动参数。
- 诊断 sink 未指向控制台、文件或远端收集端。
- 新增代码没有绕过统一门面的裸日志。
- 敏感字段没有被记录到诊断日志。

当前 Codex Memory Harness 已提供基础 release gate runtime：`codex workspace verify` 在 route plan 标记为 `release_blocking` 时，会调用 workspace verifier 的 `diagnostic_logging_disabled` gate，扫描 route scope 内常见客户端代码文件，阻断以下情况：

- `ai_diagnostics.enabled = true`、`diagnostic_logging.enabled = true` 或等价启用标记。
- `ENABLE_AI_DIAGNOSTICS`、`AI_DIAGNOSTICS_ENABLED` 等基础调试宏。
- diagnostic sink 指向 console、file 或 http。
- 新增代码里出现裸 `Debug.Log`、`console.log`、`cc.log`、`print` 等绕过统一门面的调用。

这个 gate 是基础静态检查，不是完整发布平台。它不替代业务项目自己的构建脚本、渠道包配置检查、Unity Player Settings、Laya/Cocos 平台构建配置和真机验证。业务项目仍应在 `client_release` 或自己的 release profile 中补足平台级检查。

## 11. Memory 与 Artifact 边界

诊断日志原文不应写入 memory。Harness artifact 只应保存裁剪后的摘要、验证结论、失败定位和下一步。

如果某次 AI 调试依赖日志得出结论，summary 应记录“观察到的事实”和“影响的决策”，而不是粘贴完整日志。

项目共享 memory 只能保存稳定的诊断策略、开关位置和 release gate 规则。不能提交本地诊断日志、临时任务输出或原始运行态。
