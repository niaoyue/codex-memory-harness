---
id: "2026-05-13-migrate-planning-docs-to-codex-specs-2026051-route-workspace-release_train-57ac2929c2"
scope: "workspace"
project_id: "workspace"
domain: "release_train"
status: "proposed"
confidence: "medium"
source: "task:migrate-planning-docs-to-codex-specs-20260513"
supersedes: ""
updated_at: "2026-05-13"
---

# Workspace route summary for migrate-planning-docs-to-codex-specs-20260513

## Summary
Completed correction and review loop for Codex-generated planning docs canonical directory.

Results:
- Canonical durable specs directory is `.codex/specs/`, specifically `.codex/specs/backlog-governance/` for the migrated backlog governance docs.
- `.codex/harness/` remains runtime-only and is not used for durable specs.
- Follow-up review findings from commit 265ecbb were fixed in commit 44ffa00e61e6d070a9181b2ec1735a910baffa32.
- Release packaging now includes `.codex/specs/**` while continuing to exclude `.codex/harness/**`, `.codex/memories/**`, `.codex/shared/**`, `.codex/evals/**`, and `dist/**`.
- External HarnessTest runtime artifact absolute paths were removed from source-controlled specs and replaced with sanitized checkpoint references.
- `codex xhigh review --commit 44ffa00e61e6d070a9181b2ec1735a910baffa32` passed with no blocking findings.
- Unfinished task summary was regenerated and includes progress fields for T55, T59, T81, T83, and T87.

Verification:
- git diff --check passed.
- unittest tests.test_unfinished_task_summary tests.test_project_behaviors.BuildReleaseTests passed, 8 tests OK.
- py_compile passed for scripts/build_release.py, scripts/verify_project.py, tests/test_project_behaviors.py.
- release zip boundary smoke: `.codex/specs/backlog-governance/tasks.md` included, runtime `.codex/harness`, `.codex/memories`, `.codex/shared` excluded.
- verification_runner primary passed: 3 passed, 0 failed.

Intentionally uncommitted:
- `.codex/shared/**` runtime memory/routing files and `.codex/shared/index.json` remain uncommitted.

## Route
- Mode: `release_train`
- Affected projects: `design-docs, workspace-meta-root, test-suite, release-tooling, plugin-runtime`
- Verification profiles: `primary`

## Review
- Status: proposed; review before accepting as shared memory.
