# Tasks: OpenSpec and BMAD Governance Integration

## 1. Governance Docs

- [x] Create local OpenSpec project profile.
- [x] Create baseline `change-governance` spec.
- [x] Create this change proposal.
- [x] Create this change design.
- [x] Create this change task list.
- [x] Create spec delta for the governance change.

## 2. Backlog Alignment

- [x] Add task-list entry for OpenSpec change contract and Requirements
  Integrity Gate.
- [x] Add task-list entry for BMAD upstream planning policy.
- [x] Add task-list entry for upstream OpenSpec/BMAD core reuse investigation.
- [x] Add task-list entry for strict Requirements Integrity Gate runtime.
- [x] Record initial governance docs and keep later T87 runtime fixes explicitly
  scoped in this task list.

## 3. Upstream Verification

- [x] Verify OpenSpec license, latest release/tag, dependency graph, command
  entrypoints, telemetry behavior, and artifact formats.
- [x] Verify BMAD-METHOD license, latest release/tag, dependency graph, command
  entrypoints, module layout, and artifact formats.
- [x] Decide command adapter, pinned vendoring, or protocol-only compatibility
  for each upstream.
- [x] Record upstream reuse decision with attribution and update strategy.

## 4. Runtime Design Follow-Up

- [x] Define `openspec_change_id` metadata mapping for harness task specs.
- [x] Define strict Requirements Integrity Gate output schema.
- [x] Define adapter interfaces for requirement gate, change contract, upstream
  planning, and harness metadata mapping.
- [x] Define before-write enforcement path so blocking gate results stop file
  edits.
- [x] Define archive/sync behavior for updating baseline specs after completion.

## 5. Future Implementation

- [ ] Prototype OpenSpec command or artifact adapter without rewriting upstream
  core logic.
- [ ] Prototype BMAD upstream planning adapter without claiming local automatic
  multi-agent execution.
- [ ] Extend existing `requirements_gate.py` or add a stricter companion module
  for logical consistency, acceptance gaps, and implementation/spec conflicts.
- [x] Fix docs/tooling governance tasks that mention adapter work being
  misclassified as product `feature_story` tasks.
- [x] Prevent verification artifact `touched_paths` from triggering adaptive
  release routing.
- [x] Add tests for `passed`, `needs_clarification`, `needs_bmad_upstream`, and
  `blocked_by_conflict` outputs.
- [ ] Connect final verification and review evidence to spec sync/archive.

## 6. Verification for This Slice

- [x] Run project verification.
- [x] Run targeted requirements gate and workspace hook integration tests.
- [x] Inspect git diff for runtime and documentation scope.
- [x] Run final code review gate because runtime code changes were added.
