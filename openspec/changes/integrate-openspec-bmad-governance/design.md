# Design: OpenSpec and BMAD Governance Integration

## Architecture

```text
BMAD upstream planning
  -> Requirements Integrity Gate
  -> OpenSpec change contract
  -> Harness execution
  -> Verification / review / commit gate
  -> Spec sync / archive
```

OpenSpec becomes the default change-contract layer. BMAD remains the upstream
planning layer for work that is not yet clear, small, or testable enough for one
OpenSpec change.

## Evidence Snapshot

As of 2026-05-11, official OpenSpec materials show:

- `openspec/changes/<change>/` with proposal, design, tasks, and spec deltas
- review and refinement before code is written
- a lightweight, iterative process rather than rigid phase gates
- MIT license on the GitHub repository

As of 2026-05-11, official BMAD materials show:

- phased planning across analysis, planning, solutioning, and implementation
- PRD, UX spec, architecture, epics/stories, and readiness checks
- quick-dev intent compression before autonomous work
- adversarial review patterns
- MIT license on the GitHub repository

These facts support using OpenSpec as the default downstream change contract and
BMAD as the upstream planning method. They do not remove the need for a local
Requirements Integrity Gate because this harness must enforce project-specific
blocking rules before editing files.

## Requirements Integrity Gate

The gate runs before OpenSpec apply and before any implementation write.

Inputs:

- user request and any attached requirement text
- existing `openspec/specs/**`
- existing planning docs and task lists
- related implementation facts from code, tests, and harness metadata
- current workspace routing and requirements gate result

Outputs:

- `passed`
- `needs_clarification`
- `needs_bmad_upstream`
- `blocked_by_conflict`

Required report fields:

- `assumptions`
- `missing_requirements`
- `logical_conflicts`
- `acceptance_gaps`
- `scope_gaps`
- `non_goals`
- `implementation_spec_mismatches`
- `safety_security_migration_rollback_gaps`
- `recommended_next_step`

Blocking conditions:

- conflicting requirements that cannot both be true
- missing acceptance criteria for feature or system changes
- hidden product, data, security, release, or migration assumptions
- mismatch between requested behavior and current implementation without an
  explicit migration decision
- broad product or architecture request that needs BMAD upstream planning

## BMAD Trigger Policy

Use BMAD-style upstream artifacts when the request is not ready for OpenSpec
implementation.

Recommended mapping:

| Trigger | BMAD-style artifact |
|---|---|
| product idea, unclear value, market/user uncertainty | Product Brief or PRFAQ |
| requirements unclear but product direction known | PRD |
| UX or interaction risk | UX spec |
| architecture or cross-module risk | Architecture + ADRs |
| broad work needing implementable slices | Epic and story split |
| unclear readiness | Implementation readiness decision |

The output of BMAD upstream planning becomes input to an OpenSpec change. The
OpenSpec change remains the per-change implementation contract.

## OpenSpec Change Contract

Each significant change should have:

```text
openspec/changes/<change-id>/
  proposal.md
  design.md
  tasks.md
  specs/<capability>/spec.md
```

`proposal.md` defines intent, goals, non-goals, requirements, and acceptance.

`design.md` defines architecture, tradeoffs, integration points, security,
migration, validation, and rollback.

`tasks.md` defines implementation, verification, review, commit, and archive
steps.

`specs/<capability>/spec.md` defines added, modified, or removed requirements
and scenarios.

## Harness Integration

Future runtime adapter should map OpenSpec and BMAD data into existing harness
metadata instead of replacing harness structures.

Mapping:

| OpenSpec/BMAD concept | Harness concept |
|---|---|
| change id | `openspec_change_id` in task metadata |
| proposal/design/tasks | task objective, acceptance, working set, checklist |
| spec delta | route planning context and implementation contract |
| Requirements Integrity Gate | `requirements_gate` before write |
| BMAD readiness decision | route fallback or planning prerequisite |
| tasks checklist | harness checkpoint and verification plan |
| archive/sync | spec update plus task completion summary |

The existing `requirements_gate.py` can remain the first runtime hook, but the
new OpenSpec/BMAD gate must be stricter for detailed requirements. It should
check logical consistency and implementation/spec conflicts, not only field
presence.

## Upstream Core Reuse Strategy

Preferred approach:

1. Verify upstream license, version, commit, entrypoints, dependencies,
   telemetry behavior, storage paths, and security boundaries.
2. Prefer invoking upstream commands or adapting upstream plugin artifacts.
3. If vendoring is needed, place pinned upstream code under a dedicated vendor
   boundary and keep original license and attribution.
4. Implement harness adapters that depend on stable interfaces:
   `RequirementGateProvider`, `ChangeContractProvider`,
   `UpstreamPlanningProvider`, and `HarnessMetadataMapper`.
5. Do not edit vendored upstream core logic for local behavior. Patch through
   adapters or upstream-compatible configuration.

Fallback approach:

- If upstream code cannot be reused safely, keep protocol compatibility with
  OpenSpec/BMAD artifact formats and implement only the smallest local adapter.

The current upstream reuse decision is recorded in:

```text
openspec/changes/integrate-openspec-bmad-governance/upstream-reuse-decision.md
```

That decision selects command adapters as the first runtime implementation mode
for both OpenSpec and BMAD. Pinned vendoring remains allowed only after a
separate boundary review proves command adapters are insufficient.

## Security and Compliance

- Do not upload project data to external services during planning.
- Do not persist secrets, tokens, internal links, raw logs, or sensitive payloads
  in OpenSpec or BMAD artifacts.
- Preserve upstream licenses and notices before vendoring.
- Keep telemetry decisions explicit and configurable if upstream tools are
  invoked from harness commands.
- Treat all vendored code as third-party code with update, audit, and packaging
  boundaries.

## Migration Plan

Phase 1 is documentation-only:

- create OpenSpec baseline and change artifacts
- update the project task list
- do not implement runtime commands
- do not copy third-party source code

Phase 2 investigates upstream reuse:

- pin upstream versions
- review license and dependency boundaries
- decide command adapter versus vendored adapter
- define interface contracts

Phase 2 decision for this change: start with command adapters, disable
OpenSpec telemetry in harness-managed executions, treat BMAD outputs as planning
artifacts, and block vendoring until adapter limitations are proven.

Phase 3 implements runtime:

- add strict requirements integrity command
- map OpenSpec change id into harness task metadata
- connect gate output to before-write lifecycle
- drive harness checklist from `tasks.md`
- add verification and review tests

## Risks

- Copying upstream code too early can create license, update, or packaging risk.
- Rewriting upstream behavior locally can drift from official tools and recreate
  known bugs.
- Treating BMAD roles as implemented runtime would overstate current harness
  capabilities.
- Making every small task run a heavy planning flow would slow normal work.

## Decision

Proceed with an OpenSpec-first governance structure, a stricter local
Requirements Integrity Gate, BMAD as conditional upstream planning, and
adapter-first upstream reuse. Runtime implementation is deferred until upstream
license and boundary review is complete.
