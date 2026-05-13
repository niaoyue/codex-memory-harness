# Integrate OpenSpec and BMAD Governance

## Summary

Introduce OpenSpec-style change contracts as the default governance layer for
Codex Memory Harness changes, add a stricter Requirements Integrity Gate before
OpenSpec implementation, and define BMAD as the upstream planning method for
unclear or high-risk work.

The implementation strategy is adapter-first and upstream-core-first: reuse
official OpenSpec and BMAD core code or command entrypoints where possible, and
write only the harness-specific adapter layer after license and boundary review.

## Background

The harness already has task lifecycle, workspace routing, requirements gate,
session-worktree governance, verification runner, review gate, and memory
writing. What it lacks is a durable repository-level change contract for each
significant change.

OpenSpec addresses the problem that requirements often live only in chat by
creating proposal, design, tasks, and spec deltas before implementation. BMAD
addresses the earlier product and planning problem by progressively producing
analysis, PRD, architecture, epics, stories, and readiness decisions.

Official OpenSpec material shows a lightweight workflow that creates the change
artifacts and asks humans to review and refine them before code is written. It
does not, by itself, give this project a hard, harness-enforced check for
requirement completeness, logical contradictions, acceptance gaps, or conflict
with current implementation. Codex Memory Harness must add that gate explicitly.

## Goals

- Add an OpenSpec directory structure for durable change governance.
- Define Requirements Integrity Gate as a mandatory pre-implementation step for
  detailed requirements.
- Define when BMAD upstream planning is required before OpenSpec apply.
- Keep harness lifecycle, workspace routing, verification, memory, and review
  gates authoritative.
- Prefer upstream OpenSpec/BMAD core reuse through adapters instead of rewriting
  their core logic locally.
- Record future implementation tasks for license review, import strategy, and
  runtime adapter work.

## Non-Goals

- Do not implement a full OpenSpec CLI in this slice.
- Do not copy OpenSpec or BMAD source code in this slice.
- Do not claim that BMAD multi-agent behavior is already implemented by this
  repository.
- Do not replace the candidate-commit `codex xhigh review --commit <commit-sha>`
  final review gate or the local review workflow.
- Do not implement full OpenSpec/BMAD adapters in this slice; T87 runtime edits
  are limited to Requirements Gate and verification-artifact routing false
  positives discovered while dogfooding the governance contract.

## Requirements

### Requirement: Requirements Integrity Gate Before OpenSpec Apply

Detailed user requirements must be checked before implementation for objective,
self-consistency, scope, non-goals, acceptance criteria, safety, migration,
rollback, and conflicts with current specs or implementation.

Gate outputs:

- `passed`
- `needs_clarification`
- `needs_bmad_upstream`
- `blocked_by_conflict`

Any non-`passed` blocking output stops implementation.

### Requirement: BMAD Upstream Trigger Policy

BMAD-style planning is required when:

- the request is only a product idea or product direction
- target users, value, scope, or success criteria are unclear
- the change crosses modules, projects, or architectural boundaries
- UX, security, release, migration, or operational risk is high
- a PRD, architecture, epic/story split, or implementation readiness decision is
  needed before code can be safely changed

### Requirement: OpenSpec Downstream Contract

Every significant change should use:

- `proposal.md` for why the change exists and what changes
- `design.md` for technical approach and tradeoffs
- `tasks.md` for implementation and verification checklist
- `specs/<capability>/spec.md` for requirement deltas

### Requirement: Upstream-Core-First Integration

Future runtime integration must prefer:

1. command or plugin adapter around official upstream tooling
2. pinned vendored upstream code with license, attribution, and version record
3. local protocol/template compatibility only when upstream reuse is blocked

Rewriting OpenSpec or BMAD core behavior directly inside harness modules is the
last resort and requires an explicit decision record.

## Acceptance Criteria

- `openspec/project.md` defines the local OpenSpec/BMAD governance policy.
- A baseline `change-governance` spec exists.
- This change includes proposal, design, tasks, and delta spec artifacts.
- The task list records follow-up implementation work for Requirements
  Integrity Gate, BMAD policy, and upstream core reuse.
- The documentation states that this slice does not copy third-party code and
  does not implement runtime behavior yet.
