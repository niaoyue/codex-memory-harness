---
id: "2026-05-13-commit-first-review-gate-20260512-route-workspace-release_train-3736f8b48c"
scope: "workspace"
project_id: "workspace"
domain: "release_train"
status: "proposed"
confidence: "medium"
source: "task:commit-first-review-gate-20260512"
supersedes: ""
updated_at: "2026-05-13"
---

# Workspace route summary for commit-first-review-gate-20260512

## Summary
已确认 review gate 新流程已经落地，并完成本轮候选提交后的 commit-based xhigh review 闭环。

本轮新增修复提交 79f7f88df9790e9f554aaf5ec060bb3019407071：
- memory_mining: failed evidence no longer auto-promotes into accepted memory.
- retrieval_store: rg/file listing/fulltext/exact/semantic fallback use the selected workspace root.
- skill_bundle: stale skill detection now hashes the full skill directory tree, not only SKILL.md.
- tests: added/updated regression coverage including behavior test mock signature.

验证：
- targeted unittest: 28 tests OK.
- py_compile: target files OK.
- git diff --check: target files OK.
- primary verification_runner: 3 passed, 0 failed.
- codex xhigh review --commit 79f7f88df9790e9f554aaf5ec060bb3019407071: clean, no blocking findings.

未提交：.codex/shared runtime artifacts intentionally left out of the candidate commit.

## Route
- Mode: `release_train`
- Affected projects: `workspace-meta-root, plugin-runtime, design-docs, test-suite`
- Verification profiles: `primary`

## Review
- Status: proposed; review before accepting as shared memory.
