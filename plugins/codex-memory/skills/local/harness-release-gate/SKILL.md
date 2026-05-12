---
name: harness-release-gate
description: Run the Codex Memory Harness release and candidate-commit review gate. Use when the user asks for final verification, release gate, submit gate, candidate commit validation, or to prepare a local commit for this package or a project using this harness.
---

# Harness Release Gate

Use this workflow for changes that need to be verified, committed locally, and reviewed as a commit before push.

## Workflow

1. Inspect `git status --short` and identify which files belong to the current task.
2. Run the project verification command:

   ```powershell
   python -X utf8 scripts\verify_project.py
   ```

3. Create a local candidate commit that contains only the current task files.
4. Capture the commit SHA before review:

   ```powershell
   git rev-parse HEAD
   ```

5. Run the final Codex review gate against the commit. After follow-up fix commits, capture the new commit SHA and review that new commit:

   ```powershell
   codex xhigh review --commit HEAD
   ```

6. Fix all blocking findings, then create a new local commit or redo the unpushed candidate commit.
7. Rerun `codex xhigh review --commit <commit-sha>` for the new commit until there are no new blocking findings.

## Rules

- Do not commit unrelated user changes.
- Treat DEBUG/AI diagnostic logs as required verification evidence for functional changes; missing diagnostics for key branches, state transitions, fallback reasons, input/output summaries, or completion results are a verification gap.
- Use diagnostic profile or local debug output to confirm behavior before final release checks, while still requiring release profile to prove diagnostic logging is disabled.
- Do not set a fixed total timeout for SubAgent or review-runner work; any timeout is only an observation window.
- Do not delete `.codex/memories`, `.codex/harness/tasks`, SQLite databases, JSONL logs, `dist`, or cache directories as part of the gate.
- If `scripts\verify_project.py` is not present, use the repository's configured primary verification profile and report that fallback.
