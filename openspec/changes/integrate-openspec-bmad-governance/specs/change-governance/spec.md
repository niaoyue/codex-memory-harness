# change-governance Delta

## ADDED Requirements

### Requirement: OpenSpec Change Contract

Codex Memory Harness MUST support OpenSpec-style change contracts as the default
durable agreement for significant changes.

#### Scenario: Change contract is created

- GIVEN a non-trivial change request
- WHEN requirements are ready for implementation
- THEN the repository MUST have a change folder containing proposal, design,
  tasks, and spec delta artifacts
- AND implementation MUST use those artifacts as the change boundary

### Requirement: Requirements Integrity Gate

Codex Memory Harness MUST run a stricter Requirements Integrity Gate before
OpenSpec apply or implementation writes when the request contains detailed
requirements.

#### Scenario: Detailed request lacks testable acceptance

- GIVEN a detailed feature or system-change request
- WHEN the request lacks testable acceptance criteria
- THEN the gate MUST return `needs_clarification`
- AND implementation MUST stop before writing files

#### Scenario: Detailed request is logically inconsistent

- GIVEN a request contains requirements that conflict with each other
- WHEN no explicit product or architecture decision resolves the conflict
- THEN the gate MUST return `blocked_by_conflict`
- AND the conflict MUST be recorded before any implementation work continues

#### Scenario: Request needs upstream planning

- GIVEN a request is product-level, cross-module, architecture-level, or too
  broad for one implementation change
- WHEN it cannot be converted into a complete OpenSpec contract
- THEN the gate MUST return `needs_bmad_upstream`
- AND the next step MUST produce BMAD-style planning artifacts

### Requirement: BMAD Upstream Planning

Codex Memory Harness MUST treat BMAD as the upstream planning method for work
that is not yet ready for an OpenSpec implementation contract.

#### Scenario: PRD or architecture is needed

- GIVEN a request needs product requirements, UX decisions, architecture, epics,
  stories, or implementation readiness
- WHEN those artifacts are missing
- THEN the harness MUST route the task to BMAD-style planning before
  implementation

### Requirement: Upstream Core Reuse

Codex Memory Harness MUST prefer official upstream OpenSpec and BMAD core code
or command entrypoints over local rewrites.

#### Scenario: Upstream code has not been reviewed

- GIVEN a task proposes copying OpenSpec or BMAD source code
- WHEN license, version, dependency, entrypoint, storage, telemetry, security,
  and packaging boundaries have not been verified
- THEN copying MUST be blocked
- AND the task MUST first produce an upstream reuse decision record

#### Scenario: Upstream reuse is approved

- GIVEN license and boundary review approves upstream reuse
- WHEN code is imported or wrapped
- THEN the upstream core MUST be pinned and attributed
- AND harness-specific behavior MUST live in adapters rather than direct local
  modifications to upstream core logic

## MODIFIED Requirements

### Requirement: Harness Execution Boundary

OpenSpec and BMAD artifacts extend the existing harness workflow but do not
replace task lifecycle, workspace routing, session worktree governance,
verification runner, memory safety, or final review gate.

#### Scenario: Change is ready for implementation

- GIVEN requirements have passed the integrity gate
- WHEN implementation begins
- THEN existing harness execution gates remain authoritative
- AND the OpenSpec change id SHOULD be recorded in harness task metadata
