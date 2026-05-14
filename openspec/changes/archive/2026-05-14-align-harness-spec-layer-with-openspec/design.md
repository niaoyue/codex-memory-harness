## Context

OpenSpec `@fission-ai/openspec@1.3.1` reports the default `spec-driven`
schema as `proposal -> specs -> design -> tasks`. The local Harness repository
already has `openspec/` artifacts, but it also has `.codex/specs/` with a
Kiro-like `requirements.md`, `design.md`, and `tasks.md` triple. That duplicate
shape creates two competing homes for durable specifications.

Harness also owns runtime behavior that OpenSpec does not replace: memory
lifecycle, workspace routing, session worktree guard, verification runner,
review gate, task state, and archive-readiness evidence. The aligned model must
therefore use OpenSpec for durable specs and changes while preserving Harness as
the execution and evidence runtime.

## Goals / Non-Goals

**Goals:**

- Make `openspec/` the only canonical durable spec and change-contract root.
- Align new change contracts with the latest OpenSpec `spec-driven` artifact
  order.
- Preserve Harness runtime binding through change-local extension artifacts.
- Stop presenting `.codex/specs` as the formal spec layer.
- Keep runtime task state and private memory out of OpenSpec artifacts.
- Keep official OpenSpec schema/templates available locally through a pinned
  upstream snapshot that can be refreshed from npm.
- Update adapters and tests so archive readiness can require both OpenSpec
  contract evidence and Harness verification/review evidence.

**Non-Goals:**

- Do not vendor or rewrite OpenSpec core.
- Do not replace Harness lifecycle, routing, verification, review, or memory
  controls with OpenSpec.
- Do not migrate runtime task state, event logs, caches, or memory databases into
  `openspec/`.
- Do not automatically archive old `.codex/specs` content without explicit
  mapping to a stable behavior capability or compatibility stub.

## Decisions

### Decision 1: Use `openspec/` as the canonical spec root

Selected design: all new durable specs and change contracts use `openspec/`.
Stable behavior lives under `openspec/specs/<capability>/spec.md`; work in
progress lives under `openspec/changes/<change-id>/`.

Alternatives considered:

- Keep both `.codex/specs` and `openspec/`: rejected because it preserves the
  confusing dual-spec model.
- Make `.codex/specs` mimic OpenSpec layout: rejected because external OpenSpec
  tooling still expects `openspec/`, and the path would remain non-standard.
- Move Harness runtime state into OpenSpec: rejected because runtime events and
  private memory are not durable behavior specs.

### Decision 2: Represent Harness linkage as OpenSpec change extensions

Each Harness-executed change gets:

```text
openspec/changes/<change-id>/
  harness.json
  harness.md
```

`harness.json` is the machine-readable binding used by adapters and tests.
`harness.md` is the human-readable audit note. Neither file replaces OpenSpec
artifacts.

The minimal `harness.json` contract is:

```json
{
  "version": 1,
  "harness_task_id": "align-openspec-spec-layer",
  "risk_level": "high",
  "working_set": ["openspec/**"],
  "verification_profile_ids": ["primary"],
  "review_gate": {
    "type": "codex_xhigh_review_commit",
    "required": true
  },
  "memory_policy": {
    "scope": "project",
    "write_shared_summary": false
  },
  "archive_gate": {
    "requires_passed_verification": true,
    "requires_clean_review": true,
    "requires_openspec_validate": true
  }
}
```

### Decision 3: Deprecate `.codex/specs` without mixing it into OpenSpec

`.codex/specs` is no longer a valid destination for new durable specs. Existing
files are either:

- migrated into `openspec/changes` or `openspec/specs` when they define durable
  behavior, or
- converted into compatibility stubs or Harness backlog/runtime documentation
  when they describe task progress rather than behavior.

The unfinished task summary reader may continue to read a Harness backlog source,
but that source must not be described as the formal spec layer.

### Decision 4: Keep upstream OpenSpec command-adapter-first

Harness invokes official OpenSpec through the installed command or
`npx -y @fission-ai/openspec@1.3.1`, with `OPENSPEC_TELEMETRY=0` and
`DO_NOT_TRACK=1`. Harness adapters read artifacts and validate evidence; they do
not copy or rewrite OpenSpec core behavior.

### Decision 5: Sync official schema/templates as pinned upstream assets

Harness keeps a local upstream snapshot at:

```text
openspec/upstream/openspec/
  manifest.json
  LICENSE
  NOTICE.md
  README.md
  package.json
  schemas/spec-driven/schema.yaml
  schemas/spec-driven/templates/*.md
```

The snapshot is created from `@fission-ai/openspec@1.3.1` and records npm
integrity, shasum, file hashes, license, node engine, schema name, telemetry
policy, and an update command. Harness-specific behavior stays in local adapter
code; upstream files are not edited by hand.

The command-level integration is:

```text
codex openspec upstream sync --version 1.3.1
codex openspec upstream verify
codex openspec upstream status
```

## Risks / Trade-offs

- **Existing docs reference `.codex/specs` heavily** -> Update public and
  repository-local guidance in one migration slice and leave compatibility stubs
  where old links are useful.
- **Backlog content is not a behavior spec** -> Keep backlog/progress sources
  separate from OpenSpec baseline specs and document that distinction.
- **OpenSpec archive could be run before Harness gates pass** -> Make
  `governance_adapter.py` require passed verification and clean review before
  reporting `safe_to_archive=true`.
- **External OpenSpec version can drift** -> Pin the currently verified version
  in docs, adapter examples, and `openspec/upstream/openspec/manifest.json`;
  keep command invocation telemetry disabled and refresh through the sync
  command.
- **Large migration can touch many docs** -> Use targeted replacements and tests
  rather than broad rewrites of unrelated documentation.

## Migration Plan

1. Create this OpenSpec change contract using the latest `spec-driven` workflow.
2. Add `harness.json` and `harness.md` for this change.
3. Update `openspec/project.md` and baseline/delta specs to define the aligned
   model.
4. Replace new-spec guidance in `AGENTS.md`, README, installer guidance, and
   skill governance docs so they point to OpenSpec.
5. Convert old `.codex/specs` planning files into compatibility stubs or migrate
   behavior requirements into OpenSpec capability specs.
6. Sync official OpenSpec upstream schema/templates into
   `openspec/upstream/openspec/`.
7. Update Harness adapter/tests for `harness.json` and upstream snapshot
   evidence.
8. Run OpenSpec validate, targeted tests, project verification, and the final
   candidate-commit review gate if committing.
9. Archive this OpenSpec change only after validation and Harness evidence are
   clean.

## Open Questions

- None blocking. The user explicitly requested full alignment with latest
  OpenSpec while preserving Harness linkage.
