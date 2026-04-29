# Codex Shared Memory

This directory is the reviewable project shared memory layer.

Use it for stable, non-sensitive project facts, decisions, workflows, and routing summaries. Do not put raw task state, logs, credentials, production endpoints, private repository URLs, or generated databases here.

Suggested folders:

- `decisions/`: accepted or deprecated architecture and product decisions.
- `facts/`: stable module boundaries, ownership, and implementation facts.
- `workflows/`: verification, release, rollback, and operational workflows.
- `routes/`: workspace routing summaries and project/domain scope notes.

Each shared memory entry should be a small Markdown file with front matter matching `schemas/shared_memory.schema.json` in the Codex Memory Harness package.
