# Design Document

## Overview

This migration separates durable agent planning records from public documentation. The canonical backlog moves to `.codex/specs/backlog-governance/`, while `docs/` retains only compatibility stubs for the three migrated planning documents.

The design keeps existing links usable and updates runtime readers to prefer the new canonical task list. This avoids a split brain where humans update `.codex/specs` but `before_response` still summarizes an obsolete `docs/` task list.

## Document Layout

```text
.codex/specs/backlog-governance/
  requirements.md
  design.md
  tasks.md
  execution-plan.md
  workspace-routing-tasks.md

docs/
  codex-memory-plugin-task-list.md          # compatibility stub
  codex-memory-plugin-execution-plan.md     # compatibility stub
  WORKSPACE_ROUTING_TASK_LIST.md            # compatibility stub
```

## Source Mapping

| Legacy path | Canonical path | Role |
|---|---|---|
| `docs/codex-memory-plugin-task-list.md` | `.codex/specs/backlog-governance/tasks.md` | Main task list and unfinished task source |
| `docs/codex-memory-plugin-execution-plan.md` | `.codex/specs/backlog-governance/execution-plan.md` | Historical execution plan and architecture narrative |
| `docs/WORKSPACE_ROUTING_TASK_LIST.md` | `.codex/specs/backlog-governance/workspace-routing-tasks.md` | Workspace routing task breakdown |

## Runtime Integration

`plugins/codex-memory/scripts/unfinished_task_summary.py` owns the default path used by `before_response` when the payload requests unfinished task progress. Its path resolution changes to:

1. Use an explicit `task_list_path` when supplied.
2. Prefer `.codex/specs/backlog-governance/tasks.md`.
3. Fall back to `docs/codex-memory-plugin-task-list.md`.

The fallback preserves compatibility for external projects or tests that still use the old path.

## Progress Evidence Model

The canonical task list records HarnessTest dogfood evidence for the currently unfinished high-risk items:

| Task | Local evidence | Remaining blocker |
|---|---|---|
| T59 | Generated SubAgent binding and one host spawn request | Host-native SubAgent launch and observation API |
| T81 | `before_first_write` soft event returned `switch_to_effective_cwd` | Host-native pre-write interception and full lifecycle enforcement |
| T83 | Receipt readiness report returned `ready_for_integration`, `auto_merge=false`, with branch metadata | T59/T81 plus automatic specialist branch integration and final gate |
| T87 | Governance adapter collected OpenSpec, BMAD planning, verification, and clean review evidence with `safe_to_archive=true` | Real BMAD upstream execution or user planning material |

## Boundaries

- Do not move `.codex/harness/tasks/`; it is task runtime state.
- Do not include `.codex/shared/**` in this migration; current shared facts/routes are runtime side effects.
- Do not claim blocked host capabilities are complete because local adapter paths were dogfooded.
- Do not keep full planning state in `docs/` after migration; use stubs for compatibility.

## Verification Strategy

- Run targeted unit tests for `unfinished_task_summary.py`.
- Run `git diff --check`.
- Use `rg` to verify old planning paths are either stubs or compatibility references.
- Run the project primary verification profile if time and local environment allow.
- If committing, create a candidate commit first and review that commit with `codex xhigh review --commit <sha>`.
