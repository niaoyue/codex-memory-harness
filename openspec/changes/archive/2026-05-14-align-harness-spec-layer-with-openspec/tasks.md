## 1. OpenSpec Contract Setup

- [x] 1.1 Create the OpenSpec proposal, delta specs, design, and tasks artifacts for `align-harness-spec-layer-with-openspec`.
- [x] 1.2 Add `harness.json` and `harness.md` extension artifacts for this change.
- [x] 1.3 Validate the change with `@fission-ai/openspec@1.3.1` strict validation.

## 2. Canonical Spec Layer Migration

- [x] 2.1 Update `openspec/project.md` so the workflow policy uses the latest `proposal -> specs -> design -> tasks` order.
- [x] 2.2 Update repository and installer guidance so new durable specs go to `openspec/changes` and stable behavior specs go to `openspec/specs`.
- [x] 2.3 Deprecate `.codex/specs` as a formal spec layer and convert current `.codex/specs` content to compatibility stubs or non-spec backlog guidance.
- [x] 2.4 Update public docs and compatibility stubs that currently call `.codex/specs` the canonical spec layer.

## 3. Harness Runtime Binding

- [x] 3.1 Update `governance_adapter.py` so OpenSpec evidence includes `harness.json` binding status.
- [x] 3.2 Keep Harness archive readiness gated on passed verification and clean final review evidence.
- [x] 3.3 Update tests for OpenSpec contract evidence and Harness binding requirements.
- [x] 3.4 Add pinned official OpenSpec upstream snapshot sync and verification tooling.
- [x] 3.5 Update Harness governance evidence so missing or drifted upstream OpenSpec assets block archive readiness.

## 4. Verification and Archive Readiness

- [x] 4.1 Run OpenSpec strict validation for this change.
- [x] 4.2 Run targeted Python unit tests for governance adapter and unfinished task summary behavior.
- [x] 4.3 Run project verification through the configured Harness verification runner if local environment allows.
- [x] 4.4 Create a candidate commit and run `codex xhigh review --commit <sha>` as the default final review gate. Earlier gates found P1/P2 issues; the amended candidate `0d6854c4d060e7189ec8bf645bc19153f271f94f` passed cleanly.
- [x] 4.5 Archive this OpenSpec change only after OpenSpec validation, Harness evidence, and commit-based review are clean. The change was archived as `2026-05-14-align-harness-spec-layer-with-openspec` after the clean commit-based review gate.
