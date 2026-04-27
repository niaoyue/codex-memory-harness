# Codex 外脑插件任务清单

## 1. 使用说明

本清单用于驱动逐步实施，状态定义如下：

- `todo`：未开始
- `doing`：进行中
- `done`：已完成
- `blocked`：受阻

当前策略：一次只推进一个主任务，避免并行改动过多导致上下文污染。

## 2. 主任务清单

| ID | 阶段 | 任务 | 产出物 | 依赖 | 状态 |
|---|---|---|---|---|---|
| T00 | 0 | 创建插件目录骨架 | `plugins/codex-memory/` 目录结构 | 无 | done |
| T01 | 0 | 创建 `.codex-plugin/plugin.json` 占位清单 | 插件入口清单 | T00 | done |
| T02 | 0 | 创建 `mcp/` 最小服务入口 | `memory_server.py` 骨架 | T00 | done |
| T03 | 0 | 创建 `storage/` 与初始化脚本 | 本地存储骨架 | T00 | done |
| T04 | 1 | 定义任务状态模型 | 状态 schema 文档或代码 | T02,T03 | done |
| T05 | 1 | 实现任务状态读写 | `task state` 读写接口 | T04 | done |
| T06 | 1 | 实现项目决策读写 | `repo decisions` 读写接口 | T04 | done |
| T07 | 1 | 实现任务结束总结回写 | `summary` 生成与持久化 | T05,T06 | done |
| T08 | 2 | 实现精确检索 | 文件名/符号/关键词检索 | T02,T03 | done |
| T09 | 2 | 实现全文检索 | FTS 检索与证据包输出 | T08 | done |
| T10 | 2 | 预留语义检索接口 | embedding 检索占位接口 | T09 | done |
| T11 | 3 | 实现 context pack 构建 | 统一上下文装配逻辑 | T05,T07,T09 | done |
| T12 | 3 | 实现注入预算控制 | 上下文裁剪与分层策略 | T11 | done |
| T13 | 4 | 实现任务蒸馏输出 | 模式归档与技能草稿占位 | T07,T11 | done |
| T14 | 4 | 写回蒸馏资产索引 | `distilled/` 与结构化记录 | T13 | done |
| T15 | 5 | 实现 hooks 自动触发 | 自动读取、更新、回写 | T05,T11,T13 | done |
| T16 | 5 | 增加失败降级与容错 | 无记忆模式回退能力 | T15 | done |
| T17 | 5 | 补充验证脚本与示例流程 | 本地验收脚本或文档 | T16 | done |
| T18 | 6 | 对齐 Codex 插件市场接入 | repo/home marketplace 与本机插件入口 | T15 | done |
| T19 | 6 | 对齐官方 hooks 入口格式 | `hooks.json` 与 `hook_bridge.py` | T15 | done |
| T20 | 6 | 落地无感使用默认工作流 | 安装脚本、仓库 AGENTS 与自动兜底 | T18,T19 | done |
| T21 | 7 | 实现全局/项目记忆隔离 | 全局 `.codex/memories` 与项目 `.codex/memories` | T20 | done |
| T22 | 8 | 实现最小 Harness Controller | start/checkpoint/complete 三段式控制器 | T21 | done |
| T23 | 8 | 增加项目 harness 配置 | `.codex/harness` 配置与命令注册 | T22 | done |
| T24 | 9 | 增加 Harness Verification Runner | 配置化验证执行、危险命令拦截、checkpoint 回写 | T23 | done |
| T25 | 10 | 增加全局 Bootstrap / Doctor | 窗口启动自检、项目初始化、状态诊断 JSON | T24 | done |
| T26 | 11 | 增加 PowerShell codexm 启动器 | 全局 profile 函数、doctor/init 后启动真实 Codex | T25 | done |
| T27 | 12 | 增加 PowerShell codex 包装函数 | profile 级 codex wrapper、codex-raw 回退、禁用开关 | T26 | done |

## 3. 当前推荐执行步

当前执行状态如下：

### Step 1（已完成）

- 目标：完成阶段 0 的插件脚手架。
- 范围：T00、T01、T02、T03。
- 不做：状态模型、检索、上下文编排、蒸馏逻辑。
- 验收：
  - 插件目录存在。
  - `plugin.json` 存在。
  - MCP 服务入口存在。
  - 存储目录存在。

### Step 2（已完成）

- 目标：完成阶段 1 的状态模型与最小读写接口。
- 范围：T04、T05、T06、T07。
- 不做：混合检索、上下文编排、蒸馏逻辑。
- 验收：
  - 任务状态 schema 明确。
  - 可读写 `task state`。
  - 可读写 `repo decisions`。
  - 可写回任务总结。

### Step 3（已完成）

- 目标：完成阶段 2 的代码优先最小混合检索。
- 范围：T08、T09、T10。
- 不做：上下文编排、蒸馏逻辑、hooks 自动触发。
- 验收：
  - 可对本地代码和文档执行精确检索。
  - 可对本地文本执行全文检索。
  - 检索输出可组织成统一证据包。
  - 语义检索接口保留占位，但不强行接入远程依赖。

### Step 4（已完成）

- 目标：完成阶段 3 的 context pack 与注入预算控制。
- 范围：T11、T12。
- 不做：蒸馏逻辑、hooks 自动触发。
- 验收：
  - 可从任务状态、项目决策、证据包构建统一 context pack。
  - 注入内容按层分组，而不是原始拼接。
  - 预算控制可裁剪低优先级证据。

### Step 5（已完成）

- 目标：完成阶段 4 的任务蒸馏与资产写回。
- 范围：T13、T14。
- 不做：hooks 自动触发。
- 验收：
  - 任务完成后可生成模式化输出。
  - 蒸馏结果可写回 `distilled/`。
  - 蒸馏资产有结构化索引可读。

### Step 6（已完成）

- 目标：完成阶段 5 的 hooks 自动触发、失败降级与示例验收。
- 范围：T15、T16、T17。
- 不做：更复杂的远程协同或副模型训练。
- 验收：
  - hooks 可触发读取、更新、回写流程。
  - 失败时可降级到无记忆模式。
  - 有一套本地示例流程或验收脚本可复现。

### Step 7（已完成）

- 目标：完成“无感使用”的默认接入，减少用户手动调用插件脚本的成本。
- 范围：T18、T19、T20。
- 不做：真实远程语义检索、平台私有 hook 能力扩展、模型训练。
- 验收：
  - repo 级 marketplace 可发现 `codex-memory`。
  - home 级 marketplace 与本机插件入口可安装并校验。
  - `hooks.json` 按 Codex 插件样例格式工作，并桥接到内部记忆事件。
  - 仓库级 `AGENTS.md` 规定默认自动使用流程。

### Step 8（已完成）

- 目标：完成全局记忆与项目记忆的存储隔离。
- 范围：T21。
- 不做：远程同步、多用户权限系统、向量库。
- 验收：
  - 默认项目记忆写入 `<项目根目录>/.codex/memories/`。
  - 显式全局记忆写入 `C:/Users/<USER>/.codex/memories/`。
  - `hook_runner.py` 与 `memory_server.py` 均支持 `--memory-scope`。
  - `.codex/memories/` 不进入检索证据包。

### Step 9（已完成）

- 目标：按 Harness Engineering 思路落地最小任务运行时。
- 范围：T22、T23。
- 不做：多 agent 调度、远程环境、复杂 eval 平台。
- 验收：
  - `harness_controller.py start` 可创建 task spec 并加载上下文。
  - `harness_controller.py checkpoint` 可记录 structured artifact 并写入 after_tool。
  - `harness_controller.py complete` 可执行 checklist、写总结并触发蒸馏。
  - `.codex/harness/commands.json` 与 `project_profile.json` 存在且可解析。

### Step 10（已完成）

- 目标：把验证命令纳入 harness runtime，让 Codex 在收尾前自动运行配置化验证并记录证据。
- 范围：T24。
- 不做：远程 eval 平台、沙箱容器、多 agent 调度。
- 验收：
  - `verification_runner.py list` 可列出配置化命令。
  - `verification_runner.py run --profile primary` 可执行项目验证配置。
  - 传入 `--task-id` 时可自动写入 harness checkpoint。
  - 明显危险命令会被拒绝。

### Step 11（已完成）

- 目标：让所有 Codex 窗口具备统一启动自检和项目初始化入口。
- 范围：T25。
- 不做：强制拦截真实 `codex` 命令、远程守护进程、宿主私有 hook。
- 验收：
  - `codex_bootstrap.py --doctor` 可输出当前窗口 memory/harness 状态。
  - `codex_bootstrap.py --init-project` 可创建缺失的项目 memory/harness 配置，且不覆盖已有配置。
  - 当前项目 primary 验证包含 bootstrap doctor。
  - 全局与项目说明包含 bootstrap/doctor 使用入口。

### Step 12（已完成）

- 目标：提供低风险 PowerShell 启动器，让 Codex 启动前自动执行 bootstrap/doctor。
- 范围：T26。
- 不做：覆盖真实 `codex` 命令、修改 PATH 顺序、强制 shell hook。
- 验收：
  - `codexm.ps1 -DoctorOnly` 可输出 doctor JSON。
  - PowerShell profile 中注册 `codexm` 函数。
  - `codexm.ps1` 可定位真实 `codex` 命令，且不递归调用自身。
  - 当前项目 primary 验证包含 `codexm_doctor`。

### Step 13（已完成）

- 目标：让 PowerShell 中输入 `codex` 也自动经过 memory bootstrap，但不改写真实 Codex 安装文件。
- 范围：T27。
- 不做：修改 npm-global `codex.ps1` / `codex.cmd`、调整 PATH 顺序、删除真实 Codex shim。
- 验收：
  - PowerShell profile 中注册 `codex` 函数，调用 `codexm.ps1`。
  - `codex-raw` 可绕过 wrapper 调用真实 Codex。
  - `CODEX_MEMORY_DISABLE_WRAPPER=1` 可作为禁用开关。
  - `codexm.ps1` 仍可跳过函数并定位真实外部 Codex 命令。

## 4. 每步完成后的固定动作

每完成一个主步，都执行以下动作：

1. 更新本清单状态。
2. 记录新增文件与目的。
3. 记录是否影响下一步边界。
4. 如有阻塞，明确写出阻塞原因和替代方案。

## 5. 暂不进入本轮的事项

以下事项明确不进入第一步：

- 复杂向量检索
- 远程数据库
- 副模型训练
- 高级 rerank
- 云端同步

## 6. 当前状态与下一步

阶段 6 已完成，当前状态如下：

- Step 6 已完成
- Step 7 已完成
- Step 8 已完成
- Step 9 已完成
- Step 10 已完成
- Step 11 已完成
- Step 12 已完成
- Step 13 已完成
- 如需继续增强，下一轮再进入 eval suite、真实宿主 hook 覆盖扩展、语义检索接入、记忆迁移或更强的上下文编排
