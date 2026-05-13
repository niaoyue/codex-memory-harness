---
name: git-safe-commit
description: Safely inspect, filter, stage, and commit Git changes across any repository. Use when Codex is asked to commit changes, prepare a clean commit, decide what should or should not be committed, or write a clear commit message while avoiding build artifacts, temp files, secrets, unrelated edits, and other low-signal noise.
---

# Git Safe Commit

## Workflow

### 1. Inspect the repository state

- Run `git status --short --untracked-files=all`.
- Use `git diff --stat` and `git diff --name-status` to understand scope.
- Run `git diff --check` before staging to catch trailing whitespace and malformed patch text.
- If the repository is large or already dirty, inspect ignored files with `git status --ignored --short` before assuming every untracked file is intentional.

### 2. Decide the commit boundary

- Default to the smallest coherent change that satisfies the user's request.
- If unrelated edits are present, stage only the files that belong to the requested task.
- If the user asks to "commit everything", still exclude noise, secrets, and accidental local files.
- Prefer multiple commits over one mixed commit when there are clearly independent changes.
- Do not silently revert user work just to make the commit cleaner.

### 3. Filter out files that should usually stay uncommitted

- Exclude build outputs, caches, coverage, logs, editor noise, temp files, package installs, and binary dumps unless the repository intentionally tracks them.
- Common examples: `bin/`, `obj/`, `dist/`, `build/`, `coverage/`, `.cache/`, `.next/`, `.turbo/`, `node_modules/`, `tmp/`, `temp/`, `.DS_Store`, `Thumbs.db`, `*.log`, `*.tmp`, `*.pid`.
- Exclude local-only secrets and machine configuration such as `.env`, `.env.*`, private keys, tokens, credentials, and debug dumps unless the user explicitly wants a sanitized template version.
- Treat generated files carefully: commit them only when they are part of the repository's reviewed source of truth or clearly required by the requested change.

### 4. Do minimal cleanup before staging

- Fix low-risk whitespace problems reported by `git diff --check`.
- Avoid broad reformatting or cleanup passes unless the user explicitly asked for them.
- Keep cleanup inside the intended commit boundary.

### 5. Stage deliberately

- Use explicit `git add <paths>` when the repository contains mixed work.
- Use `git add -A` only when the entire visible change set belongs to the same task and has already been reviewed.
- Re-check with `git diff --cached --stat`.
- Inspect `git diff --cached` when the commit boundary is ambiguous or the change is large.

### 6. Write the commit message

- Use an imperative subject line.
- Keep the first line concise and specific to one coherent topic.
- Add body paragraphs when the diff is non-trivial, explaining what changed and why.
- State migration expectations clearly when relevant, including explicit "no migration, direct replacement" wording for breaking replacements.
- Use prefixes such as `feat:`, `fix:`, `refactor:`, or `docs:` only when they match the repository style.

### 7. Commit and verify

- Commit with `git commit -m "<subject>"` and extra `-m` paragraphs when useful.
- After commit, run `git status --short` and `git rev-parse --short HEAD`.
- Report the commit hash and summarize anything intentionally left uncommitted.

## Heuristics

### When to commit generated files

- Commit generated code, lockfiles, snapshots, or schema outputs when the repository already treats them as reviewed artifacts.
- Do not commit generated files that are normally ignored and can be recreated locally without losing source information.
- If unsure, inspect whether similar files are already tracked with `git ls-files`.

### When to stop and ask

- Stop if the repository contains possible secrets or credentials and sanitization is unclear.
- Stop if the working tree mixes unrelated user changes and the intended commit boundary cannot be inferred safely.
- Stop if hooks or tests fail in a way that would make the commit misleading.
- Do not use `--no-verify`, `--amend`, force push, or history rewriting unless the user explicitly asks.

## Quick request patterns

- "Commit everything relevant for this task, but exclude junk files."
- "Prepare a clean commit for this refactor and write a good message."
- "Check what should not be committed before you commit."
