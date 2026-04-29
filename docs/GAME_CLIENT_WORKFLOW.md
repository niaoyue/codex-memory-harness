# 游戏客户端专项工作流

## 1. 文档目的

本文面向游戏客户端项目，目标引擎包括：

- Unity
- LayaBox / LayaAir
- Cocos Creator

本文只讨论客户端研发增强，不试图覆盖完整游戏工作室的全部职责。服务端、运营后台、买量投放、剧情制作、音频制作、美术资产生产等内容只在影响客户端工程时进入边界。

## 2. 外部资料读取状态

本次参考资料：

| 来源 | 读取状态 | 可取点 |
|---|---|---|
| `https://github.com/bmad-code-org/BMAD-METHOD` | 已读取 README | 规模自适应流程、结构化工作流、专业 agent、完整生命周期 |
| `https://github.com/bmad-code-org/bmad-module-game-dev-studio` | 已读取 README 和 workflows 文档 | Quick Flow / Full Production、GDD、架构、sprint/story、测试工作流 |
| `https://github.com/Donchitos/Claude-Code-Game-Studios` | 已读取 README | 游戏工作室式角色层级、路径规则、hooks、技能目录、会话状态、质量门禁 |
| Unity 官方文档 | 已读取命令行参数说明 | batchmode、executeMethod、projectPath、logFile、buildTarget 等可自动化入口 |
| Cocos Creator 官方文档 | 已读取命令行构建说明 | `--project`、`--build`、`configPath`、平台构建参数和退出码 |
| LayaAir 官方文档 | 已读取命令行发布说明 | `LayaAirIDE --project`、`--script`、`BuildTask.start(...)` 等可自动化入口 |

文档只提炼公开工程方法，不复制外部项目模板，也不引入外部项目依赖。

## 3. 不直接照搬的原因

BMAD 和 Claude-Code-Game-Studios 都覆盖完整游戏制作流程，而本仓库定位是 Codex Memory / Harness 的本地增强层。直接照搬会产生三个问题：

- 范围过大：完整工作室模板包含美术、音频、叙事、社区、发行等角色，不适合作为每个客户端任务的默认上下文。
- 生态不一致：外部项目围绕 BMad 或 Claude Code 的技能、slash command、hook 机制设计，本项目应保持 `codex memory`、`codex harness`、`codex package` 风格。
- 验证差异大：Unity、LayaBox、Cocos Creator 的命令、工程结构、构建产物和资源导入机制不同，必须以项目配置为准。

因此本项目应吸收方法论，而不是吸收目录结构。

## 4. 可取之处

### 4.1 从 BMAD / BMGD 吸收

| 外部做法 | 客户端适配 |
|---|---|
| Scale-Domain-Adaptive | 小修走轻量检查，大功能走设计、架构、实现、验证、回归 |
| Quick Flow / Full Production | 原型或 bugfix 用 Quick Flow；系统、战斗、UI 框架、热更新走 Full Production |
| GDD / brief / architecture | 客户端任务必须能追溯到玩法目标、交互规格、资源规范或技术架构 |
| story-driven development | 把玩法需求拆成可验收 story，而不是一次改完整系统 |
| QA / performance workflows | 把冒烟、自动化、性能预算和设备适配纳入 harness verification |
| correct-course | 当实现偏离设计或引擎约束时，记录纠偏结论和迁移动作 |

### 4.2 从 Claude-Code-Game-Studios 吸收

| 外部做法 | 客户端适配 |
|---|---|
| 工作室角色层级 | 收敛为客户端 Planner、Architect、Engine Specialist、Gameplay、UI、Performance、QA、Release |
| Engine Specialist | 拆成 Unity、LayaBox、Cocos Creator 三类引擎专项规则 |
| Path-scoped rules | 按目录启用规则：玩法、UI、资源、网络、热更新、测试、工具 |
| Hooks / gates | 用 `.codex/harness/commands.json` 配置验证，不默认写死具体引擎命令 |
| Session state | 复用本项目 task state、artifact、summary、distilled asset |
| Collaborative, not autonomous | 角色提供选项和证据，关键设计、资源和上线策略仍由用户确认 |

## 5. 客户端任务分级

| 等级 | 适用任务 | 推荐流程 |
|---|---|---|
| Quick Fix | 小 bug、小 UI 文案、小配置修正 | 读上下文、改最小文件、运行相关检查、写 summary |
| Feature Story | 单个玩法、单个 UI 面板、单个资源加载链路 | story、验收条件、实现、冒烟、回归点 |
| System Change | 战斗框架、UI 框架、资源系统、热更新、网络协议、SDK 接入 | 设计说明、架构评审、分阶段实现、专项验证 |
| Release Gate | 提包、热更、渠道包、小游戏平台提交 | 冻结变更、构建验证、资源检查、版本与回滚策略 |

默认策略：

- Quick Fix 不强制写大文档。
- Feature Story 必须有验收条件。
- System Change 必须有架构说明和迁移方式。
- Release Gate 必须有构建证据和回滚说明。

## 6. 推荐角色

| 角色 | 职责 | 产物 |
|---|---|---|
| Game Client Planner | 明确任务等级、验收条件、涉及平台和风险 | task spec、acceptance、risk list |
| Client Architect | 判断模块边界、生命周期、资源和性能影响 | architecture note、migration note |
| Unity Specialist | 处理 Unity 场景、Prefab、C#、Addressables、Assembly Definition、Player Settings | Unity-specific findings |
| LayaBox Specialist | 处理 LayaAir TypeScript、场景、Prefab、资源包、小游戏平台构建 | Laya-specific findings |
| Cocos Creator Specialist | 处理 Cocos TypeScript、Scene、Prefab、Asset Bundle、构建配置 | Cocos-specific findings |
| Gameplay Implementer | 实现玩法逻辑、状态机、输入、技能、数值连接 | code diff、test notes |
| UI/UX Implementer | 实现 HUD、弹窗、背包、商城、引导、适配 | UI diff、screen/adaptation notes |
| Asset Pipeline Reviewer | 检查资源命名、GUID、meta、压缩、bundle、冗余资源 | asset audit |
| Performance Reviewer | 检查 GC、DrawCall、包体、加载、首帧、内存、网络频率 | perf findings |
| Game QA | 设计冒烟、回归、自动化和真机验证 | verification payload |
| Release Manager | 管理版本号、渠道包、热更、回滚、提交过滤 | release checklist |

当前项目没有内建这些角色的调度器。角色结论应通过 harness artifact 或任务 summary 记录。

## 7. 路径规则建议

不同项目目录差异很大，以下是推荐规则，不是固定约定。

### Unity

| 路径 | 规则 |
|---|---|
| `Assets/Scripts/Gameplay/**` | 禁止 UI 直接持有玩法状态；数值必须来自配置或可追溯常量 |
| `Assets/Scripts/UI/**` | UI 不拥有核心游戏状态；必须考虑多分辨率、刘海屏、本地化 |
| `Assets/AddressableAssetsData/**` | 改动必须说明 bundle、分组、远程加载和热更新影响 |
| `Assets/**/*.prefab` / `Assets/**/*.unity` | 避免无意义序列化 churn；必须检查 `.meta` 和引用关系 |
| `Packages/**` | 升级必须说明兼容性、锁定版本和回退方式 |
| `ProjectSettings/**` | 视为高风险改动；必须记录平台和构建影响 |

### LayaBox / LayaAir

| 路径 | 规则 |
|---|---|
| `src/**` | TypeScript 逻辑必须模块化；热路径避免频繁分配和反复查找节点 |
| `assets/**` | 资源命名、压缩、分包、平台限制必须可追踪 |
| `scene/**` / `prefab/**` | 编辑器生成内容要避免无意义 churn；检查引用路径 |
| `bin/**` / `release/**` / `build/**` | 构建产物默认不提交，除非项目明确追踪 |
| `scripts/**` 或 IDE 脚本 | 构建脚本要参数化，不把渠道密钥写死 |

### Cocos Creator

| 路径 | 规则 |
|---|---|
| `assets/scripts/**` | TypeScript 逻辑按模块拆分；组件生命周期和事件解绑必须明确 |
| `assets/resources/**` | 默认资源加载路径要谨慎，避免包体膨胀和不可控常驻 |
| `assets/bundles/**` | Bundle 改动必须说明远程、版本、依赖和热更新影响 |
| `assets/**/*.prefab` / `assets/**/*.scene` | 检查 UUID、引用和序列化 churn |
| `settings/**` / `profiles/**` | 构建配置改动必须说明平台影响 |
| `build/**` | 构建产物默认不提交 |

## 8. AI 诊断日志策略

游戏客户端任务经常需要运行时反馈。AI 在处理流程、状态机、资源加载、热更新、网络分支和平台差异时，可以临时打开诊断日志来验证判断。

诊断日志必须有统一开关，不能散落裸 `Debug.Log`、`console.log`、`print` 或等价调用。发布包、渠道包、正式热更和生产构建必须关闭。

建议每个客户端项目抽象出统一门面：

```text
DiagnosticLog
AiDiagnosticLogger
ProjectLogger.Diagnostics
```

不同引擎的建议：

| 引擎 | 推荐开关 | 发布要求 |
|---|---|---|
| Unity | Scripting Define Symbols、构建配置、ScriptableObject 或 debug menu | release define 必须关闭，热路径避免关闭后仍产生 GC |
| LayaBox / LayaAir | 构建环境变量、编译常量、发布脚本参数或启动配置 | 正式包不能输出到公开控制台或远端 diagnostic sink |
| Cocos Creator | 构建配置、宏定义、启动参数或项目配置 | Asset Bundle、热更新和小游戏构建必须检查诊断关闭 |

诊断日志只写脱敏摘要。禁止输出 token、渠道签名、支付配置、SDK secret、生产地址、完整 payload、完整策划表和原始资源内容。

Release Gate 必须检查诊断开关已关闭，并检查是否出现绕过统一门面的新增裸日志。完整策略见：

```text
docs/AI_DIAGNOSTIC_LOGGING.md
```

## 9. 验证 profile 建议

游戏客户端验证不应写死在本仓库，而应由业务项目 `.codex/harness/commands.json` 配置。建议分 profile：

| Profile | 目的 | 示例 |
|---|---|---|
| `client_quick` | 快速检查 | TypeScript/C# 编译、lint、少量单测 |
| `client_assets` | 资源检查 | 命名、引用、Bundle/Addressables、包体阈值 |
| `client_smoke` | 冒烟 | 打开关键场景、启动主流程、跑关键 UI |
| `client_perf` | 性能 | GC、帧率、DrawCall、加载时间、内存峰值 |
| `client_diagnostic` | AI 调试观测 | 临时开启指定 scope，输出脱敏流程和状态摘要 |
| `client_release` | 发版 | 构建、版本号、渠道配置、热更清单、回滚包 |

引擎命令示例只作为项目配置参考：

- Unity 可用 batch mode、`-projectPath`、`-executeMethod`、`-buildTarget`、`-logFile` 等入口；测试或构建方法应放在项目自己的 Editor 脚本中。
- LayaAir 可通过 `LayaAirIDE --project=<path> --script=<Script.Method>` 执行后台脚本，脚本中调用 `IEditorEnv.BuildTask.start(...)`。
- Cocos Creator 可通过 `CocosCreator --project <path> --build "platform=...;configPath=..."` 执行构建，平台参数建议从 Build 面板导出的配置文件维护。

`client_release` 应检查 AI 诊断日志开关、调试宏和临时 sink 均已关闭。`client_diagnostic` 只能用于开发或 CI diagnostic profile，不能作为发布通过条件。

## 10. 项目配置生成器

当前已经提供 workspace 子命令来生成游戏客户端 verification profile 模板：

```powershell
codex workspace game-client template --engine unity
codex workspace game-client init --engine unity --project-cwd client
codex workspace game-client init --engine laya --project-cwd client
codex workspace game-client init --engine cocos --project-cwd client
```

`template` 只输出 JSON 模板，不写文件。`init` 会合并写入业务项目：

```text
.codex/harness/commands.json
.codex/harness/project_profile.json
.codex/harness/game-client.json
```

命令不会写死本机引擎路径。业务项目需要按本机环境设置：

| 引擎 | 环境变量 |
|---|---|
| Unity | `UNITY_EXE` |
| LayaBox / LayaAir | `LAYA_IDE_EXE` |
| Cocos Creator | `COCOS_CREATOR_EXE` |

生成器会提供 `client_quick`、`client_diagnostic` 和 `client_release` profile 的基础模板。真正的编译、构建、冒烟和 release 检查仍应由业务项目自己的 Editor 脚本、构建脚本或 CI 配置实现。

业务项目里可以保留：

```text
.codex/harness/game-client.json
```

建议结构：

```json
{
  "engine": "unity",
  "engine_version": "6000.0",
  "targets": ["android", "ios"],
  "risk_budget": {
    "gc_alloc_per_frame_bytes": 0,
    "max_bundle_size_mb": 200,
    "startup_seconds": 8
  },
  "paths": {
    "gameplay": ["Assets/Scripts/Gameplay"],
    "ui": ["Assets/Scripts/UI"],
    "assets": ["Assets/AddressableAssetsData"]
  },
  "verification_profiles": {
    "quick": "client_quick",
    "diagnostic": "client_diagnostic",
    "release": "client_release"
  },
  "ai_diagnostics": {
    "enabled_by_default": false,
    "release_must_be_disabled": true,
    "scopes": ["flow", "state", "asset_loading"]
  }
}
```

对于 LayaBox 和 Cocos Creator，字段保持一致，只替换路径、构建目标和验证 profile。

在多项目 workspace 中，优先使用 `.codex/harness/workspace-routing.json` 统一描述多个子项目；`game-client.json` 只适合作为单客户端项目的局部配置，或作为 workspace 配置里 `game_client` 项目的扩展字段。

## 11. 与 Workspace 路由的关系

如果 Codex 运行在一个包含多个子项目的 workspace 中，游戏客户端不应该作为唯一顶层入口。更好的方式是先做 workspace 级识别，再把 Unity、LayaBox、Cocos Creator 作为 `game_client` domain 的子路由。

例如一个 workspace 同时有：

- `client/`：Unity 客户端。
- `server/`：游戏服务器。
- `admin/`：运营后台。
- `docs/`：策划和接口文档。
- `art/`：美术工程。

此时任务路由应先判断本次任务涉及哪些子项目，再为每个 SubAgent 绑定对应 route。综合事务由 coordinator 汇总，不能让客户端 specialist 独自处理服务器、后台和文档风险。

workspace 级方案见：

```text
docs/WORKSPACE_ADAPTIVE_ROUTING.md
```

### 11.1 当前运行时覆盖

当前已经落地的游戏客户端专项处理：

- `workspace_scanner.py` 可识别 Unity、LayaBox/LayaAir 和 Cocos Creator 的常见工程信号。
- `workspace_router.py` 会把这些工程归入 `game_client` domain，并在自动扫描路由时补上 `game_client/<engine>` 和任务类型规则，例如 `game_client/unity`、`game_client/ui`、`game_client/assets`。
- `route plan` 会携带 `diagnostic_logging` 策略，release 任务默认不允许开启诊断日志，并要求发布前关闭。
- `workspace bind/scope-check/summarize` 可把客户端 specialist 限定在自己的 assigned scope，并由 coordinator 汇总跨项目影响。
- `codex workspace game-client init/template` 可生成 Unity、LayaBox/LayaAir、Cocos Creator 的基础 verification profile 模板。
- `workspace verifier` 的 release gate 会对 release route 执行基础 AI 诊断日志静态扫描，阻断已开启诊断、临时 sink 和绕过统一门面的裸日志。

当前仍未落地或只做基础版的专项处理：

- 没有内建 `codex game-client ...` 独立命令。
- 没有直接调用 Unity Editor、LayaAirIDE 或 Cocos Creator 的内置运行时；业务项目仍需在 `.codex/harness/commands.json` 配置自己的编译、构建、冒烟和 release profile。
- AI 诊断日志 release gate 是基础静态扫描，不是完整平台构建宏、渠道包配置和所有引擎 release setting 的全量检查。

## 12. 可选命令路线

如果项目明确是单一游戏客户端仓库，当前仍不建议把游戏客户端作为顶层唯一入口；优先使用 `codex workspace game-client ...` 生成模板，再用 workspace routing 管理验证和 release gate。

未来如果需要单项目快捷入口，可以再评估：

```powershell
codex game-client doctor
codex game-client init --engine unity
codex game-client init --engine laya
codex game-client init --engine cocos
codex game-client verify --profile client_quick
codex game-client release-check
```

命令职责：

| 命令 | 职责 |
|---|---|
| `doctor` | 识别引擎、版本、项目结构、关键配置和可用验证命令 |
| `init` | 生成 `.codex/harness/game-client.json` 和推荐 verification profile |
| `verify` | 映射到 `.codex/harness/commands.json` 里的项目命令 |
| `release-check` | 聚合构建、包体、热更、版本号、渠道配置、诊断日志关闭和回滚策略检查 |

但在多项目 workspace 下，更推荐使用 `codex workspace doctor/scan/route/verify/bind/scope-check/summarize/schedule/game-client` 做识别、路由、验证聚合、SubAgent binding、dispatch plan 和客户端模板。当前已完成 lifecycle 软集成：hook 会自动准备 route plan/bindings、按 touched paths 执行 scope guard，并在回复前输出 routing review；真实 SubAgent 自动执行器和发布级完整验证平台仍在路线中。

## 13. 推荐任务流程

### Quick Fix

1. 识别引擎和受影响路径。
2. 读取最近 task summary、项目决策和相关文件。
3. 只改必要文件。
4. 如需运行时反馈，临时开启诊断日志并记录脱敏摘要。
5. 跑 `client_quick` 或对应最小验证。
6. 写入简短 summary。

### Feature Story

1. 写清玩法或 UI 验收条件。
2. 明确资源、配置、网络、热更新、平台适配影响。
3. Implementer 修改代码。
4. Engine Specialist 检查引擎特有风险。
5. QA 运行冒烟和回归。
6. Performance Reviewer 检查热路径、包体和加载。
7. 如开启过诊断日志，确认最终配置已回到默认关闭。
8. 完成 summary，沉淀设计和验证结论。

### Release Gate

1. 冻结功能范围。
2. 确认版本号、渠道参数、热更清单。
3. 运行 `client_release`。
4. 检查 AI 诊断日志、调试宏和临时 sink 已关闭。
5. 检查构建产物不进入源码提交。
6. 写明回滚方式和已知风险。

## 14. 当前落地建议

短期只需要三件事：

1. 文档层：保留本文作为游戏客户端专项策略入口。
2. 配置层：业务项目按引擎维护 `.codex/harness/commands.json`，不要在本仓库写死 Unity/Laya/Cocos 路径。
3. 运行层：继续使用 `codex harness verify run --profile <profile>` 或 `codex workspace verify --route-file route.json`；多项目 workspace 先用 `codex workspace doctor/scan/route` 识别项目和任务范围，再用 `codex workspace schedule` 生成 SubAgent dispatch plan，必要时用 `codex workspace game-client init` 初始化客户端 profile。

这能保持本仓库通用、低耦合，同时给游戏客户端项目足够明确的增强路线。
