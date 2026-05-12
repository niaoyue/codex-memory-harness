# Workspace 自适应路由设计

## 1. 背景

真实游戏研发仓库经常不是单一项目。一个 workspace 下面可能同时存在：

- 游戏客户端：Unity、LayaBox/LayaAir、Cocos Creator。
- 游戏服务器：Go、Java、C#、Node.js、Python 等。
- 后台服务：运营后台、GM、支付、账号、日志、数据看板。
- Web 管理端：React、Vue、Angular 或内部低代码系统。
- 文档设计：策划案、技术方案、接口文档、数值说明。
- 美术工程：Unity Art 工程、Spine、Texture、Shader、特效、模型导入工程。
- 构建发布：CI、渠道包、热更新、资源 CDN、版本管理。

因此路由不能只问“这个项目是不是游戏客户端”。更准确的问题是：

1. 当前 workspace 下有哪些子项目？
2. 当前任务涉及哪些子项目？
3. 当前 SubAgent 正在处理哪个子项目或哪类综合事务？
4. 每个子项目应该加载什么规则、流程、验证 profile？
5. 跨项目任务如何汇总验证、处理冲突、形成最终结论？

## 2. 总体结论

推荐从 `Game Client Harness` 升级为：

```text
Workspace Adaptive Routing
```

它不是一个用户必须手动选择的命令，而是 harness 生命周期中的自动路由层。

推荐分层：

```text
Workspace Scanner
  -> Project Inventory
  -> Task Router
  -> SubAgent Route Binding
  -> Workflow Composer
  -> Verification Aggregator
  -> Summary / Memory Writer
```

核心原则：

- 用户不需要手动选择客户端、服务器、后台或文档。
- SubAgent 不应该共享同一个粗粒度规则包，而应按自己处理的子项目加载规则；复杂/应用级/多阶段实现即使只命中单个 route，也应默认生成可供宿主派发的 SubAgent dispatch plan。
- 综合事务需要 coordinator，不应让某个单域 specialist 独自吞掉全局决策。
- 自动识别可以给推荐，但项目显式配置优先。

## 2.1 设计审查结论

当前设计审查后的关键结论：

- `game_client` 只是 workspace routing 的一个 domain，不应作为多项目 workspace 的顶层入口。
- route plan 必须记录 `project_id`、`domain`、`cwd`、`assigned_scope`、`rules`、`verification_profile_ids` 和 `confidence`。
- verification aggregation 需要支持每个子项目自己的执行目录；当前 `verification_runner.py` 已支持 command `cwd`，`workspace_verifier.py` 会按 route plan 聚合执行。
- memory 需要区分 workspace 级事实和子项目级事实，避免把服务器、后台、客户端结论混成一个不可检索的大摘要。
- SubAgent 的 artifact 必须带 route binding，否则后续无法判断它是否越权改了其他项目。
- 代码审核的最终 gate 优先使用 `codex xhigh review --commit <commit-sha>` 审核被审提交；修复循环必须先创建新的修复提交，再 review 新提交本身，避免反复审整个候选范围。大 diff 或长耗时审查优先让 XHigh Review Runner SubAgent 作为并行命令执行器运行该 gate，等待策略按 stdout/stderr 和状态进度观察，不再套固定总时长。通用 SubAgent reviewer 只做 route-bound 或专题辅助审查。

## 2.2 Schema 契约与字段命名

当前阶段已经把文档设计收束为可验证 schema，并实现 scanner、route planner、verification aggregator、SubAgent binding/scope guard/coordinator summary、dispatch plan、游戏客户端 profile 模板、基础诊断 release gate 与 memory lifecycle 软集成。仍未实现真实 SubAgent 自动执行器和发布级完整验证平台。

Schema 文件：

```text
schemas/workspace_project_inventory.schema.json
schemas/workspace_routing_config.schema.json
schemas/workspace_route_plan.schema.json
schemas/subagent_route_binding.schema.json
schemas/verification_aggregation.schema.json
```

字段命名约定：

- `verification_profiles`：只用于配置层，表示别名到 profile id 的映射，或 fallback profile id 列表。
- `verification_profile_ids`：用于 route plan、SubAgent binding 和 verification plan，表示已经解析、准备执行的 profile id。
- `routes[]`：route plan 的主结构；即使是单项目任务，也写成一个 route，避免后续多项目和综合事务另起格式。
- SubAgent route binding 使用扁平 canonical schema，通过 `route_plan_id`、`route_id` 和 `project_id` 关联 route plan，不再使用嵌套 `route` 对象作为正式 artifact。

## 3. 子项目发现

Workspace Scanner 应把工作区扫描成 project inventory。

建议输出：

```json
{
  "workspace_root": "H:/workspace/game",
  "projects": [
    {
      "id": "client-unity",
      "path": "client",
      "cwd": "client",
      "domain": "game_client",
      "engine": "unity",
      "confidence": 0.95,
      "signals": ["client/Assets", "client/ProjectSettings/ProjectVersion.txt"]
    },
    {
      "id": "server-game",
      "path": "server",
      "cwd": "server",
      "domain": "game_server",
      "language": "go",
      "confidence": 0.88,
      "signals": ["server/go.mod", "server/cmd"]
    },
    {
      "id": "admin-web",
      "path": "admin",
      "cwd": "admin",
      "domain": "backoffice_web",
      "framework": "vue",
      "confidence": 0.82,
      "signals": ["admin/package.json", "admin/src"]
    },
    {
      "id": "design-docs",
      "path": "docs",
      "cwd": "docs",
      "domain": "design_docs",
      "confidence": 0.78,
      "signals": ["docs/**/*.md"]
    }
  ]
}
```

### 3.1 常见识别信号

| Domain | 信号 |
|---|---|
| Unity 客户端 | `Assets/`、`ProjectSettings/`、`Packages/manifest.json`、`*.asmdef`、`AddressableAssetsData/` |
| Laya 客户端 | `src/`、`bin/`、`release/`、`.laya/`、LayaAir 构建脚本、laya 依赖 |
| Cocos 客户端 | `assets/`、`settings/`、`profiles/`、`assets/**/*.prefab`、Cocos 构建配置 |
| 游戏服务器 | `go.mod`、`pom.xml`、`.csproj`、`package.json`、`cmd/`、`proto/`、`api/` |
| 后台服务 | `admin`、`gm`、`ops`、`payment`、`account`、`dashboard`、数据库迁移 |
| Web 管理端 | `src/views`、`src/router`、`vite.config.*`、`next.config.*`、`vue.config.*` |
| 文档设计 | `docs/`、`design/`、`gdd/`、`策划/`、`*.md`、`*.xlsx` |
| 美术工程 | `Art/`、`Spine/`、`Textures/`、`Shaders/`、`Effects/`、`FBX`、`PSD`、`AEP` |
| 构建发布 | `.github/`、`.gitlab-ci.yml`、`Jenkinsfile`、`build/`、`ci/`、`release/` |
| Workspace 元工程 | 仓库根 `AGENTS.md`、`README.md`、`pyproject.toml`、`scripts/`、`plugins/` |

识别必须支持多项目同类并存，例如多个 Unity 客户端、多个服务器服务、多个后台应用。

## 4. 项目配置

推荐新增 workspace 级配置：

```text
.codex/harness/workspace-routing.json
```

示例：

```json
{
  "$schema": "local://codex-memory-harness/schemas/workspace_routing_config.schema.json",
  "version": 1,
  "workspace": {
    "name": "game-workspace"
  },
  "projects": [
    {
      "id": "client-unity",
      "path": "client",
      "cwd": "client",
      "domain": "game_client",
      "engine": "unity",
      "rules": ["workspace/base", "game_client/base", "game_client/unity"],
      "verification_profiles": {
        "quick": "client_quick",
        "release": "client_release"
      }
    },
    {
      "id": "server-game",
      "path": "server",
      "cwd": "server",
      "domain": "game_server",
      "rules": ["workspace/base", "game_server/base", "server/go"],
      "verification_profiles": {
        "quick": "server_unit",
        "integration": "server_integration"
      }
    },
    {
      "id": "admin-web",
      "path": "admin",
      "cwd": "admin",
      "domain": "backoffice_web",
      "rules": ["workspace/base", "backoffice/base", "web/vue"],
      "verification_profiles": {
        "quick": "admin_lint_test",
        "release": "admin_build"
      }
    }
  ],
  "fallback": {
    "rules": ["workspace/generic"],
    "verification_profiles": ["primary"]
  }
}
```

发布包内的完整模板位于 `templates/project/.codex/harness/workspace-routing.json`，示例同时覆盖 Unity、LayaBox/LayaAir、Cocos Creator 客户端、游戏服务器、后台 Web、设计文档和美术工程。业务项目落地时应删除不存在的示例项目，并把 profile id 对齐到本项目 `.codex/harness/commands.json`。

自动识别结果不能覆盖这个配置。优先级：

1. 用户本次明确指定。
2. SubAgent 任务输入明确指定。
3. `workspace-routing.json` 显式项目配置。
4. 自动扫描结果。
5. 通用 fallback。

## 5. 任务路由

Task Router 要综合以下信号：

- 用户请求文本。
- 当前工作目录。
- working set。
- diff / touched paths。
- 最近 task summary。
- SubAgent role 和 assigned scope。
- 项目 inventory。

输出应该是 route plan：

```json
{
  "version": 1,
  "task_id": "fix-login-flow",
  "mode": "single_project",
  "primary_project": "client-unity",
  "affected_projects": ["client-unity"],
  "task_type": "ui",
  "risk_level": "medium",
  "routes": [
    {
      "route_id": "client-unity-ui",
      "project_id": "client-unity",
      "domain": "game_client",
      "cwd": "client",
      "engine": "unity",
      "task_type": "ui",
      "assigned_scope": ["client/Assets/Scripts/UI", "client/Assets/Prefabs/UI"],
      "rules": ["workspace/base", "game_client/base", "game_client/unity", "game_client/ui"],
      "verification_profile_ids": ["client_quick", "client_ui_smoke"],
      "diagnostic_logging": {
        "allowed": true,
        "required_scopes": ["flow", "state"],
        "release_must_be_disabled": true
      },
      "confidence": 0.91,
      "reasons": ["touched path client/Assets/Scripts/UI/LoginPanel.cs"]
    }
  ],
  "confidence": 0.91,
  "reasons": [
    "request mentions login panel",
    "touched path client/Assets/Scripts/UI/LoginPanel.cs"
  ]
}
```

### 5.1 路由模式

| Mode | 场景 | 处理方式 |
|---|---|---|
| `single_project` | 只涉及一个子项目 | 直接绑定该项目规则和验证 |
| `multi_project_parallel` | 多个子项目可并行处理 | 分派多个 specialist，各自 route 和验证 |
| `cross_project_contract` | 客户端、服务器、后台共享接口或协议 | 先由 coordinator 锁定契约，再分域实现 |
| `workspace_meta` | 文档、规范、CI、目录整理 | 使用 workspace 规则，不绑定单一业务项目 |
| `release_train` | 多端发版、热更、渠道包、服务器部署 | release coordinator 汇总所有 gate |
| `unknown_low_confidence` | 证据不足 | 走只读分析或请求用户确认 |

### 5.2 Route Plan Artifact

route plan 应写入 harness artifact，便于审查和复现：

```json
{
  "tool_name": "workspace_router",
  "phase": "routing",
  "summary": "Detected single Unity client UI task.",
  "signals": {
    "route_plan": {
      "mode": "single_project",
      "primary_project": "client-unity",
      "affected_projects": ["client-unity"],
      "routes": [
        {
          "route_id": "client-unity-ui",
          "project_id": "client-unity",
          "domain": "game_client",
          "cwd": "client",
          "assigned_scope": ["client/Assets/Scripts/UI", "client/Assets/Prefabs/UI"],
          "rules": ["workspace/base", "game_client/base", "game_client/unity", "game_client/ui"],
          "verification_profile_ids": ["client_quick", "client_ui_smoke"],
          "diagnostic_logging": {
            "allowed": true,
            "required_scopes": ["flow", "state"],
            "release_must_be_disabled": true
          }
        }
      ],
      "task_type": "ui",
      "risk_level": "medium",
      "confidence": 0.91
    }
  },
  "touched_paths": [],
  "next_step": "Load Unity UI rules and run client_quick/client_ui_smoke after edits."
}
```

这个 artifact 是后续 SubAgent route binding、验证聚合和 summary 的共同依据。

## 6. SubAgent 路由绑定

SubAgent 运行时不能只继承主任务的大规则包。每个 SubAgent 应有自己的 route binding。

推荐结构：

```json
{
  "version": 1,
  "task_id": "fix-login-flow",
  "route_plan_id": "route-fix-login-flow",
  "subagent_id": "agent-review-client-ui",
  "role": "UI Reviewer",
  "binding_mode": "specialist",
  "route_id": "client-unity-ui",
  "project_id": "client-unity",
  "domain": "game_client",
  "cwd": "client",
  "engine": "unity",
  "task_type": "ui",
  "assigned_scope": ["client/Assets/Scripts/UI", "client/Assets/Prefabs/UI"],
  "rules": ["workspace/base", "game_client/base", "game_client/unity", "game_client/ui"],
  "verification_profile_ids": ["client_quick", "client_ui_smoke"],
  "artifact_policy": {
    "required_fields": ["project_id", "domain", "assigned_scope", "touched_paths"],
    "forbid_raw_sensitive_output": true,
    "checkpoint_required": true
  }
}
```

### 6.1 Specialist SubAgent

Specialist 只负责一个明确项目或目录集合：

- Unity UI Reviewer：只看 Unity 客户端 UI。
- Server Contract Reviewer：只看服务器接口、协议、数据模型。
- Admin Web Implementer：只改后台 Web。
- Asset Pipeline Reviewer：只看资源导入、压缩、bundle、meta。

规则：

- 不能改自己 scope 外文件。
- 如果发现必须跨项目修改，输出 `cross_project_dependency`，交给 coordinator。
- 验证只运行自己项目相关 profile。
- checkpoint 必须包含 `project_id`、`domain`、`assigned_scope` 和 touched paths。

### 6.2 Coordinator SubAgent

综合事务需要 coordinator，例如：

- 登录链路：客户端 UI + 账号服务器 + 后台账号配置 + 接口文档。
- 新活动上线：客户端活动入口 + 服务器活动规则 + 后台活动配置 + 策划文档。
- 热更新发版：客户端资源 + CDN + 版本配置 + 后台开关。
- 协议升级：proto/schema + 客户端解析 + 服务器实现 + GM 后台展示。

Coordinator 职责：

- 拆 route plan。
- 定义跨项目契约。
- 分配 specialist。
- 汇总 artifact。
- 判断验证是否完整。
- 处理冲突和最终迁移说明。

Coordinator 不应直接吞掉所有实现，除非任务很小。

## 7. 综合事务流程

以“新增一个限时活动”为例：

```text
User request
  -> Task Router: cross_project_contract
  -> Coordinator:
       1. 读取策划文档和接口说明
       2. 生成 route plan
       3. 分配客户端、服务器、后台、文档 specialist
  -> Client Specialist:
       修改活动入口、UI、资源加载
       运行 client_quick/client_ui_smoke
  -> Server Specialist:
       修改活动规则、协议、数据存储
       运行 server_unit/server_integration
  -> Backoffice Specialist:
       修改活动配置页面和权限
       运行 admin_lint_test/admin_build
  -> Docs Specialist:
       更新接口文档、运营配置说明
  -> Coordinator:
       汇总验证、冲突、发布顺序、回滚策略
```

最终 summary 不能只说“已完成”。必须写：

- 影响了哪些子项目。
- 每个子项目改了什么。
- 每个子项目跑了哪些验证。
- 跨项目契约是什么。
- 发布顺序和回滚方式。
- 未验证项和风险。

## 8. 规则加载策略

规则包应按 route plan 动态组合：

```text
workspace/base
project-domain/base
project-platform/base
task-type/rules
risk-level/rules
release-gate/rules
```

例子：

| 场景 | 规则 |
|---|---|
| Unity UI 修复 | `workspace/base`、`game_client/base`、`game_client/unity`、`game_client/ui` |
| Cocos 热更新 | `workspace/base`、`game_client/base`、`game_client/cocos`、`game_client/hot_update`、`release/high_risk` |
| Go 服务器协议 | `workspace/base`、`game_server/base`、`server/go`、`contract/protobuf` |
| 后台配置页 | `workspace/base`、`backoffice/base`、`web/vue`、`security/admin_permission` |
| 文档设计 | `workspace/base`、`docs/design`、`product/requirements` |
| 综合发版 | `workspace/base`、`release/train`、各项目 release rules |

### 8.1 AI 诊断日志规则

AI 诊断日志属于可观察性规则，不应默认进入所有项目。Task Router 应根据任务类型和风险决定是否允许 diagnostic scope。

推荐规则：

- 普通实现任务可以允许临时 `flow`、`state` 或 `validation` scope。
- 性能、资源、热更新和网络任务可以按需允许更窄 scope。
- Specialist SubAgent 只能申请自己 route binding 内的诊断 scope。
- Coordinator 负责记录哪些子项目临时开启过诊断日志。
- `release_train` 和所有 release profile 必须检查诊断日志关闭。

完整策略见：

```text
docs/AI_DIAGNOSTIC_LOGGING.md
```

## 9. 验证聚合

Verification Aggregator 不应该只跑一个 `primary`。

它应该根据 route plan 组合多个 profile：

```json
{
  "verification_plan": [
    {
      "project_id": "client-unity",
      "cwd": "client",
      "verification_profile_ids": ["client_quick", "client_assets"]
    },
    {
      "project_id": "server-game",
      "cwd": "server",
      "verification_profile_ids": ["server_unit", "server_contract"]
    },
    {
      "project_id": "admin-web",
      "cwd": "admin",
      "verification_profile_ids": ["admin_lint_test"]
    }
  ]
}
```

聚合结果要记录：

- 每个子项目验证结果。
- 跳过原因。
- 失败命令。
- 是否阻断最终完成。
- 哪些验证只能人工确认。
- release profile 是否确认 AI 诊断日志、调试宏和临时 sink 已关闭。

### 9.1 当前运行时差距

当前 `verification_runner.py` 是项目级 runner，默认在一个 project root 下执行配置化命令。workspace verify 要真正落地前，必须先补：

- command spec 支持 `cwd` 或 `project_id`。
- profile 支持按 project 分组。
- 输出 artifact 支持多项目结果。
- 危险命令检查必须同时覆盖展示命令和实际 argv。
- 缺失 profile 时必须记录 `verification_gap`，不能回退成“通过”。

这些能力已经落地为最小本地聚合运行时；`codex workspace verify --auto` 作为自动路由规划别名可用。它不代表完整发布验证平台已经完成，release profile 和跨平台构建仍需业务项目显式配置。

### 9.2 Memory 分层策略

workspace routing 会产生两类记忆：

| 记忆类型 | 写入内容 | 作用 |
|---|---|---|
| workspace 级 | 跨项目契约、发布顺序、综合事务 summary、route plan | 让后续综合任务理解全局上下文 |
| 子项目级 | 客户端实现细节、服务器接口细节、后台页面细节、资源处理结论 | 让 specialist 后续任务只读取相关上下文 |

默认策略：

- route plan 和 coordinator summary 写 workspace memory。
- specialist 的实现细节写对应 project memory 或带 `project_id` 的 project-scoped summary。
- 敏感配置、密钥、生产地址、渠道令牌不写入任何 memory。
- 低置信度路由只写“判断依据和不确定性”，不写成确定事实。

当前实现状态：lifecycle 已把 route plan、memory plan、bindings、scope guard 和 SubAgent runtime decision 写入 task metadata / artifact；任务完成时会按 `memory_plan` 自动把 workspace route summary 与子项目 facts 写入 `.codex/shared` 的 proposed 草稿，并执行脱敏、index rebuild 与 shared validate。需要成为团队长期事实的条目仍应由人工 review 后把 status 从 `proposed` 调整为 `accepted`；低置信 route、原始日志和敏感配置不会被当成 accepted 事实。

## 10. 冲突处理

Workspace 路由必须处理冲突：

| 冲突 | 处理 |
|---|---|
| 多个 SubAgent 修改同一文件 | coordinator 暂停合并，要求一个 owner 处理 |
| 客户端和服务器协议不一致 | contract owner 先定 schema，再分域实现 |
| 文档与实现不一致 | docs specialist 更新文档或标记实现偏差 |
| 资源路径和代码引用不一致 | asset pipeline reviewer 负责核验 |
| 验证 profile 缺失 | 标记 `verification_gap`，不能假装通过 |
| 低置信度路由 | 降级为只读分析或请求用户确认 |

## 11. 建议新增命令

用户日常不需要显式选择项目，但需要调试入口。

建议：

```powershell
codex workspace doctor
codex workspace scan
codex workspace route --task-file task.json
codex workspace route --changed
codex workspace verify --route-file route.json
codex workspace bind --route-file route.json
codex workspace schedule --route-file route.json
codex workspace scope-check --binding-file binding.json --touched-path client/Assets/App.cs
codex workspace summarize --bindings-file bindings.json --artifact-file agent-result.json
codex workspace game-client init --engine unity --project-cwd client
```

命令定位：

| 命令 | 用途 |
|---|---|
| `doctor` | 已实现。只读输出 workspace inventory、项目识别结果和建议 |
| `scan` | 已实现。只读输出 workspace project inventory |
| `route` | 已实现。给定任务、working set 或 diff，输出 route plan，不执行修改 |
| `verify` | 已实现最小版。按 route plan 聚合验证 profile，支持缺失 profile 记录 gap |
| `bind` | 已实现。把 route plan 转换成 SubAgent route bindings，不自动启动 SubAgent |
| `schedule` | 已实现。根据 route plan/bindings 生成 coordinator/specialist dispatch plan 和 `host_spawn_requests`，不由插件自行启动真实 agent |
| `scope-check` | 已实现。检查 touched paths 是否越过 assigned/denied scope |
| `summarize` | 已实现。汇总 SubAgent artifact、同文件冲突、scope 违规和 verification gap |
| `game-client` | 已实现。生成 Unity、LayaBox/LayaAir、Cocos Creator verification profile 模板 |

这比顶层 `codex game-client ...` 更适合多项目 workspace。`game-client` 是 workspace routing 的一个 domain 和模板子命令，而不是顶层唯一入口。

## 12. 实现阶段建议

### 阶段 A：文档和 schema

- 新增 `docs/WORKSPACE_ADAPTIVE_ROUTING.md`。
- 新增 `docs/WORKSPACE_ROUTING_TASK_LIST.md`。
- 定义 `.codex/harness/workspace-routing.json` schema。
- 定义 route plan、SubAgent route binding 和 verification aggregation schema。

当前状态：文档设计、schema 文件和项目配置模板已完成；scanner、route planner、verification aggregator、SubAgent binding/scope guard/coordinator summary、dispatch plan、游戏客户端 profile 模板和 lifecycle 软集成已完成最小 runtime。

### 阶段 B：只读扫描器

- 实现 workspace scanner。
- 支持 project inventory 输出。
- `codex workspace doctor` / `codex workspace scan` 只读，不创建或修改项目文件。

当前状态：已完成最小只读 scanner 和 CLI 入口，支持显式 `workspace-routing.json` 优先，以及 Unity、LayaBox/LayaAir、Cocos Creator、服务器、后台、文档、美术和发布工程的常见信号识别。

### 阶段 C：路由计划

- 根据用户请求、working set、diff、inventory 生成 route plan。
- 支持低置信度降级。
- route plan 写入 harness artifact。

当前状态：已完成最小只读 `codex workspace route`，支持 `--task-file`、`--working-set`、`--changed` 和显式 project id；route plan 可选写入 harness artifact，并已接入 lifecycle 软集成和 SubAgent binding runtime。

### 阶段 D：验证聚合

- `codex workspace verify` 根据 route plan 执行多 profile。
- 失败或缺失 profile 结构化回写。

当前状态：已完成最小 verification aggregation runtime，支持每个 route 使用自己的 `cwd`、缺失 profile/command 记录 `gaps[]`，以及可选 checkpoint 写回。

### 阶段 D2：workspace memory 分层写入

- 按 route plan `memory_plan` 把 workspace 级 summary、子项目事实和 coordinator 结论写入正确的 memory scope。
- 对 `.codex/shared` 写入前执行脱敏、front matter 校验和人工 review 流程。
- 避免把低置信 route、原始日志或敏感配置提升成团队事实。

当前状态：已实现自动写入 proposed shared drafts。现有 runtime 在 `on_task_complete` 阶段读取 route plan `memory_plan`，写入 `.codex/shared/routes` 与 `.codex/shared/facts`，失败时降级记录原因而不阻断任务完成。共享层提升为 accepted 仍应走人工审查。

### 阶段 E：SubAgent 运行时集成

- 每个 SubAgent 启动时带 route binding。
- checkpoint 带 `project_id`、`domain`、`scope`、`verification_profile_ids`。
- coordinator 汇总结果。

当前状态：已完成 route binding 生成、scope guard、coordinator summary 和 dispatch plan 生成的最小运行时；`before_task` 会写入 route plan/bindings、`subagent_runtime` 决策，并在显式、route policy、复杂/应用级任务、xhigh review gate 或通用自动判断命中时写入 `subagent_dispatch_plan.host_spawn_requests`。`route policy` 可从 `.codex/harness/project_profile.json` 或 `.codex/harness/workspace-routing.json` 的 `subagent_runtime_policy` 注入 route plan，让单项目正式 implementation 任务也能持久化授权宿主 SubAgent 派发；通用 planner 会按 `task_intent`、`task_type`、`risk_level`、route 数量、scope 大小和复杂度决定普通小修是否留在主 Agent、功能/系统/发布任务是否派发 worker，以及是否额外加入 `Route Review Specialist`；`after_tool` 会按 touched paths 重算 route、记录 route-bound/SubAgent-style artifact 并执行 scope guard；`before_response` 会输出 routing review 和 runtime decision。插件自身尚未实现自动启动/调度真实 SubAgent；用户明确选择、项目 policy 授权、通用 planner 判定需要派发且宿主支持时，由主 agent 消费 host spawn requests 调用宿主 SubAgent。

### 阶段 F：游戏客户端 profile 模板与诊断 release gate

- 为 Unity、LayaBox/LayaAir、Cocos Creator 生成推荐 verification profile。
- release route 检查 AI 诊断日志关闭、临时 sink 和裸日志绕过。

当前状态：已完成 `codex workspace game-client init/template` 基础模板生成器，以及 workspace verifier 的基础 AI 诊断日志 release gate。仍未覆盖所有平台构建配置、渠道包配置和完整发布流水线。

## 13. 与现有文档关系

- `docs/GAME_CLIENT_WORKFLOW.md` 是 `game_client` domain 的专项规则。
- `docs/SUBAGENT_WORKFLOW.md` 定义角色协作与 artifact 协议。
- `docs/FULL_DEVELOPMENT_WORKFLOW.md` 从用户任务到路由、SubAgent、验证、release gate 和 memory 沉淀给出完整流程图。
- 本文定义 workspace 级发现、路由、SubAgent 绑定和综合事务聚合。

未来实现时应以本文为总入口，游戏客户端只是其中一个 domain。
