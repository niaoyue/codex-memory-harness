# Change Governance Specification

## Purpose

Define how Codex Memory Harness governs a change before code or durable project
documentation is modified.

## Requirements

### Requirement: Durable Change Contract

Every non-trivial implementation change SHOULD have a durable change contract
stored under `openspec/changes/<change-id>/`.

#### Scenario: Implementation change is requested

- GIVEN a user requests a feature, bug fix, refactor, workflow change, or
  behavior change
- WHEN the change is more than a trivial one-file edit
- THEN the agent SHOULD create or reuse an OpenSpec change contract before
  implementation
- AND the contract SHOULD include proposal, design, tasks, and spec delta files

### Requirement: Requirements Integrity Gate

The harness MUST evaluate detailed requirements before implementation begins.

#### Scenario: Detailed requirement is incomplete

- GIVEN the user provides a detailed request
- WHEN the request lacks acceptance criteria, scope boundaries, non-goals, or
  necessary migration and rollback information
- THEN the requirements gate MUST return a blocking status
- AND implementation MUST stop until the missing requirements are resolved or
  the task is downgraded to a documentation-only planning slice

#### Scenario: Gate returns a strict actionable report

- GIVEN the requirements gate evaluates a request
- WHEN it returns a result
- THEN the result MUST include `version`, `task_intent`, `status`, `blocking`,
  `requirement_sources`, `missing`, `open_questions`, `assumptions`,
  `missing_requirements`, `logical_conflicts`, `acceptance_gaps`, `scope_gaps`,
  `non_goals`, `implementation_spec_mismatches`,
  `safety_security_migration_rollback_gaps`, `recommended_next_step`,
  `assumptions_policy`, and `technical_decision_policy`
- AND the status MUST be one of `passed`, `warning`, `needs_clarification`,
  `needs_bmad_upstream`, or `blocked_by_conflict`
- AND `needs_clarification`, `needs_bmad_upstream`, and
  `blocked_by_conflict` MUST be blocking statuses
- AND `passed` and `warning` MUST be non-blocking statuses

#### Scenario: Requirement conflicts with current behavior

- GIVEN a request conflicts with existing specs, docs, task lists, or verified
  implementation behavior
- WHEN the conflict affects correctness or safety
- THEN the gate MUST return `blocked_by_conflict`
- AND the conflict MUST be recorded in the change design or task list

#### Scenario: Blocking gate stops write permissions

- GIVEN the requirements gate returns a blocking status
- WHEN the harness creates route bindings or evaluates a workspace write guard
- THEN write permissions MUST be disabled before implementation edits are
  allowed
- AND the enforcement result MUST include the gate status, blocking reason, and
  recommended next step

### Requirement: BMAD Upstream Planning Trigger

The harness MUST route unclear, product-level, architecture-level, or high-risk
requests to BMAD-style upstream planning before OpenSpec implementation.

#### Scenario: Request is too broad for one change

- GIVEN a request spans product intent, architecture, UX, multiple modules, or
  multiple projects
- WHEN the objective cannot be converted into a testable change contract
- THEN the gate MUST return `needs_bmad_upstream`
- AND the next step MUST produce PRD, architecture, epic, story, or readiness
  artifacts before implementation

### Requirement: Harness Execution Boundary

OpenSpec and BMAD artifacts MUST not replace existing harness execution gates.

#### Scenario: Change contract is ready

- GIVEN requirements have passed the gate
- WHEN implementation begins
- THEN the harness task lifecycle, workspace routing, session worktree guard,
  verification runner, and final review gate remain authoritative

### Requirement: Upstream Core Reuse Policy

The harness MUST prefer reusing official OpenSpec and BMAD core code or command
entrypoints over rewriting their behavior locally.

#### Scenario: Upstream code is considered for import

- GIVEN an implementation task proposes copying OpenSpec or BMAD code
- WHEN license, version, dependency, entrypoint, storage, security, and
  packaging boundaries have not been verified
- THEN vendoring MUST be blocked
- AND the task MUST first produce an upstream reuse decision record

#### Scenario: License and boundary review passes

- GIVEN upstream reuse is permitted and technically compatible
- WHEN the integration is implemented
- THEN upstream code MUST remain pinned, attributed, and isolated from local
  harness adapters
- AND harness modules MUST depend on adapter interfaces instead of editing
  upstream core logic directly
