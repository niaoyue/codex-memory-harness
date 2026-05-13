---
name: review-fix-merge-branch
description: Runs a branch-quality loop of self-check, review, targeted fixes, commit, and safe merge to the base branch. Use when the user asks to review current branch changes, fix review findings until clean, commit the result, or merge through a dedicated worktree without disturbing other in-progress worktrees.
---

# Review Fix Merge Branch

## Quick start

When asked to "check this branch, review it, fix issues, commit, and merge":

1. Inspect the current branch and worktree safety.
2. Self-check generated files, links, and obvious classification or scope errors.
3. Review the branch diff against the target base branch.
4. Fix concrete findings and repeat review until there are no clear issues.
5. Commit only the task-related files.
6. Merge from a clean worktree for the base branch.

## Workflow

### 1. Establish safe Git boundaries

- Confirm the current branch, worktree path, and working tree status.
- If the original repository already has another dirty worktree, do not use it for merge work.
- Use a separate worktree for merge operations on the base branch such as `main`.

### 2. Run self-check before review

- Validate generated artifacts, document links, and machine-readable indexes.
- Check obvious misclassification, missing files, malformed output, and whitespace issues.
- Prefer fixing generator rules over hand-editing generated documents.

### 3. Review the branch diff

- Review against the target base branch, not just against the last local edit.
- Findings should focus on bugs, misleading documentation, bad boundaries, missing generated output, and unsafe Git steps.
- If a finding is concrete, fix it immediately and re-run the relevant checks.

### 4. Repeat until clean

- Re-run self-check and diff review after each fix.
- Stop only when there are no clear findings left.
- If residual uncertainty remains, state it explicitly as a risk, not as a finding.

### 5. Commit safely

- Stage only the files that belong to the reviewed task.
- Use `git diff --check` before commit.
- Write a specific commit message with a short body when the change is non-trivial.
- After commit, report the commit hash and anything intentionally left uncommitted.

### 6. Merge safely

- Create or reuse a clean worktree for the base branch.
- Prefer `git merge --ff-only <feature-branch>` when possible.
- If fast-forward is impossible, inspect why before creating a merge commit.
- After merge, verify the base branch status and latest commit.

## Output expectations

- State whether the review found issues.
- Summarize each fix that was applied during the loop.
- Report the final commit hash and merge result.
- Mention the worktree paths used for feature work and merge work.
