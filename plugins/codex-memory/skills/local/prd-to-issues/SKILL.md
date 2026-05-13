---
name: prd-to-issues
description: Break a PRD into independently grabbable implementation slices and materialize them as GitHub issues or local Markdown issue drafts. Use when user wants to convert a PRD to issues, create implementation tickets, or break down a PRD into work items.
---

# PRD To Issues

Break a PRD into independently grabbable vertical slices.

## Process

### 1. Locate the PRD

Accept any of these sources:

- A GitHub issue number or URL
- A local Markdown file path
- PRD text already pasted into the conversation

If the PRD is not in context:

- Use `gh issue view <number>` when the user points to GitHub and `gh` is configured
- Read the local file when the user points to Markdown

### 2. Explore the codebase

If you have not already explored the codebase, do so to understand the current architecture, integration seams, and durable decisions.

### 3. Draft vertical slices

Break the PRD into tracer-bullet slices. Each slice must cut through every relevant layer end to end, not just one layer.

Slices may be:

- `AFK`: can be implemented without further human input
- `HITL`: requires a human decision or review

Rules:

- Each slice is narrow but complete
- A slice should be demoable or verifiable on its own
- Prefer many thin slices over few thick slices

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each slice show:

- Title
- Type (`AFK` or `HITL`)
- Blocked by
- User stories covered

Iterate until the user approves the breakdown.

### 5. Materialize the slices

Preferred path:

- If `gh` is available and the repo is GitHub-backed, create issues with `gh issue create` in dependency order

Fallback path:

- Create local Markdown issue drafts in `./plans/issues/`
- Name files with an ordered prefix, for example `01-user-onboarding-slice.md`

Use this template for both GitHub issues and local drafts:

<issue-template>
## Parent PRD

Reference the parent PRD issue, file path, or short identifier.

## What to build

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Blocked by

- Blocked by another slice if applicable

Or "None - can start immediately" if there are no blockers.

## User stories addressed

Reference the user stories from the parent PRD.
</issue-template>

Do not close or modify the parent PRD as part of this skill.
