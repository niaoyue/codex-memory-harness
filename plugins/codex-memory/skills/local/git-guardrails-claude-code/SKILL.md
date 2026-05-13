---
name: git-guardrails-claude-code
description: Prevent destructive git operations in Codex sessions and provide a reusable validator script for scripted commands. Use when user wants git safety guardrails, wants Codex to refuse push/reset/clean commands, or wants a reusable command checker for automations.
---

# Git Guardrails For Codex

Codex skills cannot install Claude Code's `PreToolUse` hooks. Adapt this skill in two layers:

1. Enforce an in-session refusal policy: do not run blocked git commands.
2. Optionally install the bundled validator script for repo-local or global automations.

## Blocked patterns

- `git push` and `push --force`
- `git reset --hard`
- `git clean -f` and `git clean -fd`
- `git branch -D`
- `git checkout .`
- `git restore .`

## Workflow

### 1. Ask scope

Ask whether the user wants:

- Session-only guardrails for the current Codex conversation
- A repo-local reusable validator script
- A global reusable validator script

### 2. Enforce the session policy

If the user asks for a blocked command, refuse it, say which pattern matched, and offer a safe alternative such as:

- `git status`
- `git diff`
- `git switch -c <branch>`
- `git stash push`
- Non-destructive inspection commands

### 3. Install the reusable validator

The bundled script is at [scripts/block-dangerous-git.py](scripts/block-dangerous-git.py).

Copy it to one of these locations when the user wants a reusable validator:

- Repo-local: `.codex/scripts/block-dangerous-git.py`
- Global: `$CODEX_HOME/scripts/block-dangerous-git.py` or `~/.codex/scripts/block-dangerous-git.py`

The validator accepts either:

- A raw command string passed as CLI arguments
- A JSON blob on stdin containing `tool_input.command`

### 4. Customize patterns

Only edit `DANGEROUS_PATTERNS` when the user explicitly wants to add or remove patterns. Keep push/reset --hard/clean/branch -D/checkout-dot/restore-dot blocked by default.

### 5. Verify

Examples:

```bash
python scripts/block-dangerous-git.py "git push origin main"
echo '{"tool_input":{"command":"git reset --hard"}}' | python scripts/block-dangerous-git.py
```

Blocked commands should exit with code `2` and print a `BLOCKED` message to stderr.

## Notes

- Skills can guide Codex behavior immediately, but cannot attach a hidden platform hook to every shell command.
- If the user needs host-level enforcement outside Codex, recommend shell aliases, wrapper scripts, or CI checks that call the bundled validator before executing scripted git commands.
