# Implementation Plan

- [x] 1. Register the work in the project task list

  - Add T100 for `.codex/specs` document normalization.
  - Add Step 43 with scope, reference format, and acceptance boundary.
  - _Requirements: 5.4, 6.4_

- [x] 2. Create the Kiro-like spec triple

  - Create `.codex/specs/codex-generated-documents/requirements.md`.
  - Create `.codex/specs/codex-generated-documents/design.md`.
  - Create `.codex/specs/codex-generated-documents/tasks.md`.
  - Include grill-me self-check, boundary rules, task progress requirements, and verification strategy.
  - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2_

- [x] 3. Make `.codex/specs` source-control friendly

  - Update `.gitignore` to allow `.codex/specs/` and `.codex/specs/**`.
  - Preserve runtime exclusions for `.codex/memories/`, `.codex/harness/tasks/`, database files, JSONL event logs, caches, and build output.
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 4. Propagate the rule to repository and installer guidance

  - Update root `AGENTS.md`.
  - Update `plugins/codex-memory/scripts/install_support.py` so generated global AGENTS guidance includes the rule.
  - Update `README.md` and `docs/SKILL_ROUTING_AND_DEFAULT_GOVERNANCE.md` so users and future agents can discover the convention.
  - _Requirements: 1.1, 3.4, 6.1, 6.2, 6.3_

- [x] 5. Verify the change

  - Run targeted status and diff checks.
  - Run Python syntax check for the edited installer helper.
  - Confirm `.codex/specs` files are visible to Git and unrelated `.codex/shared` runtime files are not included in the intended change.
  - _Requirements: 4.1, 4.3, 6.2_

- [x] 6. Close T100

  - Mark T100 and Step 43 done after verification.
  - Include unfinished task progress in the final summary.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
