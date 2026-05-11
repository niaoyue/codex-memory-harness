# Codex Memory Harness OpenSpec Profile

## Purpose

This directory records durable change contracts for Codex Memory Harness.

The harness remains the execution, memory, verification, review, and commit
runtime. OpenSpec-style artifacts provide the durable agreement for what will
change before implementation begins.

## Workflow Policy

Default development flow:

1. Requirements Integrity Gate
2. OpenSpec change contract
3. Harness task lifecycle
4. Workspace routing and session worktree guard
5. Implementation or documentation update
6. Verification runner and review gate
7. Spec sync and archive

BMAD is an upstream planning method, not the default implementation runtime.
Use BMAD-style analysis, PRD, architecture, epic, story, or readiness checks
when a request is unclear, product-level, cross-module, high-risk, or not yet
small enough for one OpenSpec change.

## Requirements Integrity Gate

Every detailed request must be checked before implementation for:

- clear objective and user value
- self-consistent requirements
- explicit scope and non-goals
- testable acceptance criteria
- migration, rollback, safety, and security gaps
- conflicts with existing specs, docs, implementation, or harness policy
- need for BMAD upstream planning

The gate may return `passed`, `needs_clarification`, `needs_bmad_upstream`, or
`blocked_by_conflict`. Blocking results stop implementation.

## Upstream Core Reuse

The preferred integration approach is adapter-first and upstream-core-first:

- Do not rewrite OpenSpec or BMAD core behavior when upstream code can be used.
- Do not copy upstream code until license, version, dependency, entrypoint,
  storage, security, and packaging boundaries are verified.
- Prefer wrapping upstream commands or vendoring a pinned upstream copy with
  attribution over forking logic into harness modules.
- Keep harness-specific code in adapters that translate between upstream
  artifacts and existing harness task, routing, memory, verification, and
  review contracts.

If upstream reuse is unsafe or incompatible, the fallback is protocol/template
compatibility with a small local adapter, not a partial untracked fork.

## Current Runtime Boundary

The repository already has a requirements gate, workspace routing, dispatch
plan metadata, scope guard, verification runner, and review gate helpers.

It does not yet have a built-in host-level true SubAgent auto-executor. Any
BMAD role or multi-agent concept must be documented as planning policy or host
runtime integration until that capability is implemented.
