## MODIFIED Requirements

### Requirement: Durable Change Contract
Every non-trivial implementation change MUST have a durable OpenSpec change
contract stored under `openspec/changes/<change-id>/`.

#### Scenario: Implementation change is requested
- **GIVEN** a user requests a feature, bug fix, refactor, workflow change, or
  behavior change
- **WHEN** the change is more than a trivial one-file edit
- **THEN** the agent MUST create or reuse an OpenSpec change contract before
  implementation
- **AND** the contract MUST follow the latest supported OpenSpec `spec-driven`
  artifact order: `proposal.md`, `specs/<capability>/spec.md`, `design.md`,
  and `tasks.md`

#### Scenario: Harness runtime binding is required
- **GIVEN** a change will be executed through Harness lifecycle, routing,
  verification, review, or memory tooling
- **WHEN** the OpenSpec change contract is prepared
- **THEN** the change MUST include Harness extension artifacts
  `harness.json` and `harness.md`
- **AND** those extension artifacts MUST bind the OpenSpec contract to Harness
  runtime controls without replacing OpenSpec artifacts
- **AND** `harness.json` MUST identify the pinned OpenSpec upstream package,
  version, schema, manifest path, and update command used by the change

### Requirement: Harness Execution Boundary
OpenSpec and BMAD artifacts MUST not replace existing harness execution gates.
Harness-specific runtime bindings MUST be represented as extension artifacts
inside the OpenSpec change directory.

#### Scenario: Change contract is ready
- **GIVEN** requirements have passed the gate
- **WHEN** implementation begins
- **THEN** the harness task lifecycle, workspace routing, session worktree guard,
  verification runner, and final review gate remain authoritative
- **AND** the OpenSpec change id MUST be recorded in harness task metadata
- **AND** `harness.json` MUST map OpenSpec artifacts to Harness task,
  verification, review, memory, and archive-readiness controls

#### Scenario: Archive readiness is evaluated
- **GIVEN** implementation work for an OpenSpec change is complete
- **WHEN** Harness evaluates archive readiness
- **THEN** it MUST require passed verification evidence and a clean final review
  gate before reporting the change safe to archive
- **AND** OpenSpec spec sync/archive MUST remain a separate explicit step
