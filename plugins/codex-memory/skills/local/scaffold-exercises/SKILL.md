---
name: scaffold-exercises
description: Create exercise directory structures with sections, problems, solutions, and explainers, then validate them with the repo's exercise checks when available. Use when user wants to scaffold exercises, create exercise stubs, or set up a new course section.
---

# Scaffold Exercises

Create exercise directory structures that match the repository's conventions.

## Directory naming

- Sections: `XX-section-name/` inside `exercises/`
- Exercises: `XX.YY-exercise-name/` inside a section
- Section numbers are `XX`
- Exercise numbers are `XX.YY`
- Use dash-case unless the repo clearly uses another convention

## Exercise variants

Each exercise needs at least one of these subfolders:

- `problem/`
- `solution/`
- `explainer/`

When stubbing and the plan does not specify otherwise, default to `explainer/`.

## Required files

Each variant folder needs a non-empty `readme.md`. A minimal stub is enough:

```md
# Exercise Title

Short description here.
```

If a variant folder contains code, add the minimal code file required by that repository.

## Validation strategy

Detect the repo's validation command in this order:

1. `pnpm ai-hero-cli internal lint` if the repo exposes it
2. A package script or task explicitly dedicated to exercises
3. The nearest general lint/test command that validates the files you touched

If no dedicated validator exists, create the scaffold, run the best available local check, and report that the repo-specific exercise validator was not found.

## Workflow

1. Parse the plan into sections, exercises, and variants
2. Create the directories
3. Create stub `readme.md` files
4. Run the detected validator
5. Fix structural errors until validation passes or no better validation path exists

## Moving or renaming exercises

- Use `git mv` when the paths are already tracked
- Re-run validation after renames
- Update numbering to preserve order
