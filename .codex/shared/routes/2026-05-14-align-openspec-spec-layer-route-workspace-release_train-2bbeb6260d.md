---
id: "2026-05-14-align-openspec-spec-layer-route-workspace-release_train-2bbeb6260d"
scope: "workspace"
project_id: "workspace"
domain: "release_train"
status: "proposed"
confidence: "medium"
source: "task:align-openspec-spec-layer"
supersedes: ""
updated_at: "2026-05-14"
---

# Workspace route summary for align-openspec-spec-layer

## Summary
完成 OpenSpec spec 层严格对齐收口：正式 durable spec/change contract 迁移到 openspec/，保留 Harness adapter/harness binding；OpenSpec upstream snapshot 通过官方 npm sync/verify 管理；review evidence 绑定不可变 commit SHA；check/candidate commit/commit review gate 默认执行。最终候选提交 b8becddc2f79f3bc9532be2a4163a4739beeb849。验证通过：py_compile、57 个定向单测、OpenSpec sync smoke、OpenSpec strict validate 3/3、openspec upstream verify、scripts/verify_project.py 653 tests OK、verification_runner primary 3/3。xhigh review --commit b8becddc2f79f3bc9532be2a4163a4739beeb849 clean，0 findings。剩余未提交仅 .codex/shared/** 运行态文件。

## Route
- Mode: `release_train`
- Affected projects: `workspace-meta-root, plugin-runtime, design-docs, test-suite, release-tooling`
- Verification profiles: `primary`

## Review
- Status: proposed; review before accepting as shared memory.
