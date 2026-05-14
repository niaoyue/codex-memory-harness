# Harness Binding

- Harness task id: `align-openspec-spec-layer`
- Runtime owner: Codex Memory Harness lifecycle
- OpenSpec version: `@fission-ai/openspec@1.3.1`
- Workflow schema: `spec-driven`
- Artifact order: `proposal -> specs -> design -> tasks`
- Upstream snapshot: `openspec/upstream/openspec/manifest.json`
- Upstream update: `codex openspec upstream sync --version 1.3.1`
- Verification profile: `primary`
- Final review gate: `codex xhigh review --commit <commit-sha>`
- Memory scope: project

## Execution Boundary

OpenSpec owns durable specs and change contracts. Harness remains responsible
for lifecycle checkpoints, workspace routing, write guards, verification runner,
candidate-commit review, memory safety, and archive-readiness evidence.

## Archive Condition

This change may be archived only after:

- OpenSpec strict validation passes.
- Targeted unit tests pass.
- Harness verification evidence passes.
- Final commit-based xhigh review is clean when a candidate commit is created.
- The user or release workflow explicitly requests archive.
