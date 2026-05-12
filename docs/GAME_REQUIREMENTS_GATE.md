# 游戏需求与策划质量门

## 1. 目的

本文定义游戏正式项目中 Codex 开发前的需求检查规则。

目标不是要求所有任务都有完整策划文档，而是防止 AI 在需求缺失时自行补玩法、规则、资源、平台或发布设定。

## 2. 任务意图区分

运行时会把任务归入以下意图：

| 意图 | 典型场景 | 是否强制需求来源 |
|---|---|---|
| `bugfix` | 修 bug、崩溃、异常、回归 | 不强制，但需要预期行为可判断 |
| `small_change` | 小文案、小配置、小优化 | 不强制 |
| `feature_story` | 新玩法、新 UI、新活动、新资源链路 | 强制 |
| `system_change` | 框架、协议、资源系统、热更新、SDK、核心模块 | 强制 |
| `release_gate` | 发版、热更、渠道包、生产构建 | 强制 |
| `docs_only` | 只改文档或策划案 | 不强制 |
| `tech_task` | 技术债、测试、工具、CI、内部治理 | 不强制策划，但必须遵守既有工程约定 |

## 3. 需求来源

`feature_story`、`system_change` 和 `release_gate` 必须能追溯到至少一种来源：

- 策划文档、GDD、设计文档。
- issue、story、任务单。
- 用户本轮给出的明确需求说明。
- 已存在实现或配置中的稳定约定。

缺少来源时，Codex 必须提出问题并停止实现。

## 4. 阻断规则

| 意图 | 阻断条件 |
|---|---|
| `feature_story` | 缺需求来源或验收条件 |
| `system_change` | 缺需求来源、验收条件、架构边界、接口或迁移说明 |
| `release_gate` | 缺需求来源或回滚说明 |

阻断时输出 `requirements_gate`，并把 `fallback_action` 设为 `ask_user`。运行时还会把 route binding 的
`permissions.may_write` 降为 `false`，并让 workspace `write-guard` 在绑定写入会话前返回
`requirements_gate_blocked`。

## 5. 需求与技术的处理边界

需求不清时不能猜。包括玩法规则、触发条件、奖励、数值、资源表现、平台差异、网络协议、运营配置、发布范围和回滚策略。

技术选择不清时，先查既有代码、配置、架构文档和项目约定。没有既有设定时，按正式项目方案处理：

- 模块化，而不是写死在调用点。
- 接口化，保留替换和测试边界。
- 配置化，避免把数值、渠道、平台和资源路径硬编码。
- 可验证，补充最小必要测试或验证 profile。
- 可迁移，系统级改动记录迁移方式和兼容影响。

## 6. 运行时字段

Route plan 会包含：

```json
{
  "requirements_gate": {
    "task_intent": "feature_story",
    "status": "needs_clarification",
    "blocking": true,
    "requirement_sources": [],
    "missing": [
      {
        "field": "acceptance_criteria",
        "reason": "缺少可验证的验收条件"
      }
    ],
    "open_questions": [
      "本任务完成后按哪些验收条件判断通过？"
    ]
  },
  "fallback_action": "ask_user"
}
```

`before_response` 会把 blocking gate 汇总为 `requirements_gate` gap。最终答复不能把这类任务说成已完成。
