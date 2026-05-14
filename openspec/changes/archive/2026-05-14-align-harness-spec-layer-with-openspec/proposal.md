## Why

Harness currently has two durable specification surfaces: OpenSpec artifacts
under `openspec/` and Kiro-like Codex specs under `.codex/specs/`. Both are
source-controlled planning/specification layers, but their directory structures
and lifecycle semantics differ, which makes it easy for agents and maintainers
to choose the wrong location or treat backlog documents as behavior specs.

This change aligns the Harness spec layer with the latest OpenSpec `spec-driven`
workflow from `@fission-ai/openspec@1.3.1`, while preserving Harness as the
execution, memory, routing, verification, review, and archive-readiness runtime.

## What Changes

- **BREAKING**: Stop treating `.codex/specs` as the default durable spec layer
  for new Harness planning or change-contract documents.
- Make `openspec/` the canonical root for durable specs and change contracts.
- Adopt the latest OpenSpec `spec-driven` artifact order:
  `proposal -> specs -> design -> tasks`.
- Introduce Harness-specific OpenSpec extension artifacts inside each change:
  `harness.json` for machine-readable runtime binding and `harness.md` for
  human-readable runtime notes.
- Add a pinned upstream snapshot under `openspec/upstream/openspec/` for
  official OpenSpec schema, templates, license, README, and package metadata,
  with a manifest and update command.
- Update governance docs and installer guidance so future agents write new
  durable specs to `openspec/changes/<change-id>/...` and stable behavior specs
  to `openspec/specs/<capability>/spec.md`.
- Preserve runtime-only state under `.codex/harness/tasks/`,
  `.codex/memories/`, and generated shared-memory proposals outside the OpenSpec
  spec model.
- Update Harness adapters and tests so OpenSpec evidence recognizes
  `harness.json`, latest schema metadata, and archive readiness without
  replacing Harness execution gates.

## Capabilities

### New Capabilities

- `harness-spec-layer`: Defines the canonical OpenSpec-compatible directory
  model for Harness durable specs, change contracts, deprecated `.codex/specs`
  behavior, and Harness extension artifacts.

### Modified Capabilities

- `change-governance`: Updates durable change contract requirements to align
  with the latest OpenSpec `spec-driven` artifact order and to require Harness
  runtime binding evidence when a change is executed by Harness.

## Impact

- Affected docs and governance: `AGENTS.md`, `README.md`,
  `docs/SKILL_ROUTING_AND_DEFAULT_GOVERNANCE.md`, `docs/USER_GUIDE.md`, and
  compatibility stubs that currently point to `.codex/specs`.
- Affected OpenSpec artifacts: `openspec/project.md`,
  `openspec/specs/change-governance/spec.md`, and this change's delta specs.
- Affected runtime adapters: `plugins/codex-memory/scripts/governance_adapter.py`
  and tests around OpenSpec contract evidence.
- Affected backlog/progress reader: `unfinished_task_summary.py` keeps reading a
  Harness backlog source, but that source must no longer be described as the
  formal durable spec layer.
- External dependency: official OpenSpec is invoked through
  `npx -y @fission-ai/openspec@1.3.1` with `OPENSPEC_TELEMETRY=0` and
  `DO_NOT_TRACK=1`; the harness keeps a pinned, attributed upstream snapshot for
  schema/templates but does not edit or rewrite OpenSpec core behavior.
