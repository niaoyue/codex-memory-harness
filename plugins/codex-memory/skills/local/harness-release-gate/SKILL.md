---
name: harness-release-gate
description: Run the Codex Memory Harness release and commit gate. Use when the user asks for final verification, release gate, submit gate, pre-commit validation, or to prepare a local commit for this package or a project using this harness.
---

# Harness Release Gate

Use this workflow for changes that need to be verified before a local commit.

## Workflow

1. Inspect `git status --short` and identify which files belong to the current task.
2. Run the project verification command:

   ```powershell
   python -X utf8 scripts\verify_project.py
   ```

3. Run the final Codex review gate:

   ```powershell
   codex xhigh review --uncommitted
   ```

4. Fix all blocking findings, then rerun the failed gate.
5. Create a local git commit only after verification and xhigh review pass.

## Rules

- Do not commit unrelated user changes.
- Treat DEBUG/AI diagnostic logs as required verification evidence for functional changes; missing diagnostics for key branches, state transitions, fallback reasons, input/output summaries, or completion results are a verification gap.
- Use diagnostic profile or local debug output to confirm behavior before final release checks, while still requiring release profile to prove diagnostic logging is disabled.
- Do not set a fixed total timeout for SubAgent or review-runner work; any timeout is only an observation window.
- Do not delete `.codex/memories`, `.codex/harness/tasks`, SQLite databases, JSONL logs, `dist`, or cache directories as part of the gate.
- If `scripts\verify_project.py` is not present, use the repository's configured primary verification profile and report that fallback.
