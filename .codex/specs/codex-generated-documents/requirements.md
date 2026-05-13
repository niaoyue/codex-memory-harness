# Requirements Document

## Introduction

Codex Memory Harness needs a stable home for documents that Codex generates during planning and execution. Those documents include requirements, designs, task plans, PRDs, RFCs, change specs, review plans, and implementation plans that exist to drive the agent workflow rather than to serve as public user documentation.

The project will use a Kiro-like specs layout under `.codex/specs/<feature-slug>/`. Each durable Codex-generated feature spec should contain `requirements.md`, `design.md`, and `tasks.md`. Public, user-facing, or long-lived handbook content may still live under `docs/`, while runtime memory and task artifacts remain excluded under `.codex/memories/` and `.codex/harness/tasks/`.

## Glossary

- **Codex_Generated_Document**: A durable planning document produced by Codex, including requirements, design notes, task plans, PRDs, RFCs, implementation plans, and change specs.
- **Codex_Spec**: A feature-scoped directory under `.codex/specs/<feature-slug>/`.
- **Feature_Slug**: A lowercase kebab-case identifier for a coherent change or feature.
- **Kiro_Triple**: The `requirements.md`, `design.md`, and `tasks.md` files inside one spec directory.
- **Public_Project_Document**: Documentation intended for repository users or maintainers, usually stored in `docs/` or `README.md`.
- **Runtime_Artifact**: Generated task, memory, event, database, cache, or verification artifact that should not be committed.
- **Task_Progress_Summary**: A summary of an unfinished task that includes status, recent checkpoint or update time, completed and remaining acceptance work, blockers, next step, and evidence source.

## Grill-Me Self-Check

The requirements review found no blocking question that must be sent back to the user before implementation.

- **Resolved from user request:** Codex-generated requirements, designs, and task documents must be moved under `.codex`.
- **Resolved from Kiro-style reference layout:** `.kiro/specs/<feature-slug>/` uses one feature directory with `requirements.md`, `design.md`, and `tasks.md`.
- **Resolved from this repository:** `.gitignore` currently ignores `.codex/*`, so `.codex/specs/**` must be explicitly allowed if these specs are intended to be committed.
- **Resolved from existing governance:** `.codex/memories/`, `.codex/harness/tasks/`, and database/event artifacts remain runtime-only and must not be mixed with specs.

## Requirements

### Requirement 1 - Specs home for Codex-generated documents

**User Story:** As a maintainer, I want Codex-generated planning documents to live under `.codex/specs`, so that agent workflow documents are separated from public documentation and runtime memory.

#### Acceptance Criteria

1. WHEN Codex creates a durable requirements, design, task, PRD, RFC, implementation plan, or change-spec document, THE repository rules SHALL direct it to `.codex/specs/<feature-slug>/` by default.
2. IF the user explicitly requests a public user document, THEN THE document MAY be written to `docs/`, `README.md`, or another user-specified path.
3. IF the artifact is runtime state, memory, database, event log, cache, or harness task execution data, THEN THE artifact SHALL NOT be placed under `.codex/specs/`.
4. WHEN a spec directory is created, THE feature slug SHALL be stable, lowercase, kebab-case, and scoped to one coherent change.

### Requirement 2 - Kiro-like triple format

**User Story:** As a maintainer, I want each spec to use a predictable three-file shape, so that requirements, design, and execution state can be reviewed independently.

#### Acceptance Criteria

1. WHEN a new Codex_Spec is created, THE directory SHALL contain `requirements.md`, `design.md`, and `tasks.md` unless the user explicitly requests a narrower artifact.
2. WHEN writing `requirements.md`, THE file SHALL include an Introduction, Glossary when useful, Requirements, user stories, and EARS-style acceptance criteria.
3. WHEN writing `design.md`, THE file SHALL describe overview, architecture, components, data or document models, lifecycle, boundaries, risks, and verification strategy.
4. WHEN writing `tasks.md`, THE file SHALL use checkboxes and map each implementation item back to requirement IDs.

### Requirement 3 - Skill-first requirements quality

**User Story:** As a maintainer, I want generated requirements to expose uncertainty and contradictions early, so that Codex does not hide planning gaps inside implementation prose.

#### Acceptance Criteria

1. WHEN Codex writes requirements or planning specs, THE workflow SHALL apply `grill-me` style review before finalizing the document.
2. IF a question can be answered from local code, existing docs, configuration, or provided references, THEN Codex SHALL answer it and include the assumption or evidence in the spec.
3. IF a question cannot be answered safely, THEN Codex SHALL list it as a user-facing open question with blocking severity.
4. WHEN creating an API, CLI, schema, protocol, or cross-module contract, THE workflow SHALL use `design-an-interface` first unless the task is purely documentary and does not define an interface.

### Requirement 4 - Git and packaging boundary

**User Story:** As a maintainer, I want specs to be commit-friendly while runtime artifacts stay excluded, so that source control contains durable governance but not local session data.

#### Acceptance Criteria

1. WHEN `.codex/specs/**` is used as a formal spec directory, THE `.gitignore` rules SHALL allow it to be tracked.
2. WHEN package and repository boundaries mention excluded `.codex` paths, THE rules SHALL continue excluding `.codex/memories/`, `.codex/harness/tasks/`, database files, JSONL event logs, caches, and build output.
3. IF `.codex/shared` contains generated runtime proposals or facts unrelated to the current change, THEN the current change SHALL NOT include those files.
4. WHEN a release package is built, THE packaging boundary SHALL avoid including runtime state while preserving source-controlled specs if package policy allows project docs.

### Requirement 5 - Unfinished task summaries include progress

**User Story:** As a maintainer, I want unfinished task summaries to include progress evidence, so that "not done" still tells the next agent what remains.

#### Acceptance Criteria

1. WHEN Codex outputs an unfinished Task summary, THE summary SHALL include each task's status, recent checkpoint or update time, completed acceptance work, remaining acceptance work, blockers, next step, and evidence source.
2. IF progress evidence is missing, THEN THE summary SHALL mark the missing field as unknown rather than inventing a percentage.
3. WHEN a spec `tasks.md` contains unfinished work, THE unfinished item SHALL include enough local progress context for the next agent to resume.
4. WHEN task progress is represented in `.codex/specs/backlog-governance/tasks.md`, THE spec SHALL keep task IDs and step references aligned with that list; `docs/codex-memory-plugin-task-list.md` SHALL be treated only as a compatibility stub.

### Requirement 6 - Rule propagation

**User Story:** As a maintainer, I want this document-location rule to survive future installs and new Codex windows, so that the convention is not only local to one chat.

#### Acceptance Criteria

1. WHEN repository-local rules are read, THE root `AGENTS.md` SHALL mention `.codex/specs/<feature-slug>/requirements.md`, `design.md`, and `tasks.md` as the default location for Codex-generated planning docs.
2. WHEN the installer writes global Codex Memory guidance, THE generated AGENTS block SHALL include the same default document-location rule.
3. WHEN user-facing project docs describe core capabilities, THE README SHALL mention source-controlled `.codex/specs` as distinct from `.codex/memories` and `.codex/shared`.
4. IF a future task changes the specs convention, THEN it SHALL update this spec or supersede it with a new `.codex/specs/<feature-slug>/` spec.
