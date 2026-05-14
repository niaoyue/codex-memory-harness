## ADDED Requirements

### Requirement: Canonical OpenSpec Spec Layer
Codex Memory Harness SHALL use `openspec/` as the canonical source-controlled
root for durable specifications and change contracts. New durable requirements,
design, task, PRD, RFC, and change-spec artifacts that define project behavior
or implementation contracts MUST be represented through the OpenSpec
`spec-driven` artifact model.

#### Scenario: New durable change contract is requested
- **WHEN** a user requests a non-trivial feature, bug fix, refactor, workflow
  change, behavior change, or durable planning artifact
- **THEN** the agent MUST create or reuse
  `openspec/changes/<change-id>/`
- **AND** the change MUST follow the latest supported OpenSpec `spec-driven`
  order: `proposal.md`, `specs/<capability>/spec.md`, `design.md`, and
  `tasks.md`

#### Scenario: Stable behavior specification is needed
- **WHEN** a behavior, workflow, or governance rule is accepted as the current
  project contract
- **THEN** it MUST be represented under
  `openspec/specs/<capability>/spec.md`
- **AND** updates MUST be introduced through an OpenSpec change delta before
  being archived into the baseline spec

#### Scenario: Legacy Codex specs path is considered
- **WHEN** an agent would create a new durable spec under `.codex/specs`
- **THEN** it MUST instead create an OpenSpec change under `openspec/changes`
- **AND** `.codex/specs` MUST be treated as deprecated compatibility material
  rather than the formal spec layer

### Requirement: Harness Runtime Binding Artifacts
Each Harness-executed OpenSpec change SHALL include Harness-specific extension
artifacts that bind the OpenSpec contract to Harness runtime controls without
replacing OpenSpec proposal, delta spec, design, or task artifacts.

#### Scenario: Harness executes an OpenSpec change
- **WHEN** an OpenSpec change is executed through Harness lifecycle tooling
- **THEN** the change directory MUST include `harness.json`
- **AND** `harness.json` MUST include the Harness task id, risk level, working
  set, verification profile ids, review gate requirement, memory policy, and
  archive gate requirements

#### Scenario: Human runtime context is needed
- **WHEN** maintainers need to audit how Harness is connected to an OpenSpec
  change
- **THEN** the change directory MUST include `harness.md`
- **AND** `harness.md` MUST summarize the Harness task id, execution boundary,
  verification command, review gate, memory scope, and archive condition

#### Scenario: OpenSpec artifact roles are evaluated
- **WHEN** `harness.json` or `harness.md` exists inside a change directory
- **THEN** they MUST be treated as Harness extension artifacts
- **AND** they MUST NOT replace `proposal.md`, `specs/<capability>/spec.md`,
  `design.md`, or `tasks.md`

### Requirement: Runtime State Separation
Harness runtime state SHALL remain outside the OpenSpec durable spec model.

#### Scenario: Runtime task state is written
- **WHEN** Harness writes task execution state, checkpoints, event logs,
  generated memory, databases, caches, or temporary artifacts
- **THEN** the artifact MUST remain under the appropriate runtime location such
  as `.codex/harness/tasks/`, `.codex/memories/`, or ignored cache/output paths
- **AND** it MUST NOT be promoted into `openspec/specs` or
  `openspec/changes` unless it is manually distilled into a durable behavior
  requirement or change contract

#### Scenario: Backlog progress is summarized
- **WHEN** Harness outputs unfinished task progress
- **THEN** it MAY read a Harness backlog or runtime-derived source
- **AND** that source MUST NOT be described as the canonical OpenSpec spec layer

### Requirement: Pinned OpenSpec Upstream Snapshot
Harness SHALL keep official OpenSpec core schema and template files in a
pinned, attributed, and updateable upstream snapshot instead of rewriting those
core files locally.

#### Scenario: OpenSpec core files are needed locally
- **WHEN** Harness needs OpenSpec schema, artifact templates, license, or
  package metadata for local validation or distribution
- **THEN** those files MUST be synchronized from the official
  `@fission-ai/openspec` package into `openspec/upstream/openspec/`
- **AND** the snapshot MUST include a manifest with the package version,
  integrity, file hashes, license, schema name, telemetry policy, and update
  command

#### Scenario: Harness evaluates OpenSpec evidence
- **WHEN** Harness prepares or collects governance evidence for an OpenSpec
  change
- **THEN** it MUST validate the pinned upstream manifest and file hashes
- **AND** invalid or missing upstream evidence MUST block archive readiness
