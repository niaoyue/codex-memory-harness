# Upstream Reuse Decision: OpenSpec and BMAD

## Status

Decision date: 2026-05-11

Status: accepted for planning, pending runtime implementation.

This decision completes the T86 documentation slice. It does not copy upstream
source code and does not implement runtime integration.

## Sources Checked

OpenSpec:

- Official repository: `https://github.com/Fission-AI/OpenSpec`
- Latest release observed: `v1.3.1`
- Latest release tag observed: `c95caf063c834b9c1d3bfb59bd94911d7c44c92b`
- Main branch observed: `053d8a59d587f3c027a06ad80503a6b43d4f2a92`
- Package name: `@fission-ai/openspec`
- CLI bin: `openspec`
- License: MIT
- Runtime requirement: Node.js `>=20.19.0`
- Notable dependencies: `commander`, `@inquirer/*`, `fast-glob`, `yaml`,
  `zod`, `posthog-node`
- Telemetry: anonymous command/version telemetry, disabled by setting
  `OPENSPEC_TELEMETRY=0` or `DO_NOT_TRACK=1`

BMAD-METHOD:

- Official repository: `https://github.com/bmad-code-org/BMAD-METHOD`
- Latest release observed: `v6.6.0`
- Latest release tag observed: `cff7e1db5f4de82e272f303e4d5dacc5ff67ace6`
- Main branch observed: `b5b33c08fa3ed094f994415887b963b56b68a292`
- Package name: `bmad-method`
- CLI bins: `bmad`, `bmad-method`
- License: MIT
- Trademark notice: `BMad` and `BMAD-METHOD` are trademarks of BMad Code, LLC
- Runtime requirement: Node.js `>=20.0.0`; README also lists Python 3.10+ and
  `uv` as prerequisites for full use
- Notable dependencies: `commander`, `@clack/*`, `glob`, `ignore`, `js-yaml`,
  `yaml`, `csv-parse`, `xml2js`, `semver`

## Decision

Use a staged reuse policy:

1. Use command adapters first.
2. Keep upstream code outside harness runtime until a separate implementation
   task proves command adapters are insufficient.
3. If vendoring becomes necessary, vendor pinned upstream source under a
   dedicated third-party boundary with original license and attribution.
4. Never directly rewrite upstream core logic inside harness modules.
5. Put all Codex Memory Harness behavior in local adapters and mappers.

## OpenSpec Reuse Decision

Preferred mode: command adapter around official `openspec`.

Rationale:

- OpenSpec already publishes a Node CLI with the artifact model this project
  wants to reuse.
- Its package exports and CLI bin make it suitable for an adapter that invokes
  upstream commands and reads generated `openspec/` artifacts.
- The harness only needs to map OpenSpec change ids, specs, tasks, and archive
  state into existing harness metadata.
- Telemetry can be disabled by environment variables in all harness-managed
  invocations.

Initial adapter behavior:

- Resolve `openspec` from PATH or use `npx -y @fission-ai/openspec@<pinned>`.
- Set `OPENSPEC_TELEMETRY=0` and `DO_NOT_TRACK=1`.
- Run only in the project root or an isolated managed worktree.
- Read and validate generated artifacts; do not mutate unrelated files.
- Map:
  - change id -> `metadata.openspec_change_id`
  - `proposal.md` -> task objective and requirements summary
  - `design.md` -> architecture notes and risk notes
  - `tasks.md` -> harness checklist
  - spec deltas -> requirements context and archive/sync inputs

Vendoring condition:

- Only vendor OpenSpec if command adapter cannot support required artifact
  operations offline or deterministically.
- If vendored, pin to an upstream commit or release tag and keep the upstream
  `LICENSE`, package metadata, and local `NOTICE`.
- Do not edit vendored files for harness-specific behavior.

## BMAD Reuse Decision

Preferred mode: command/module adapter around official `bmad-method`.

Rationale:

- BMAD is larger than a single coding library. It contains workflows, modules,
  agent definitions, installers, documentation, and method assets.
- The harness needs BMAD as upstream planning input, not as a replacement for
  harness execution, workspace routing, verification, or review gates.
- The safest integration is to invoke official BMAD tooling to create planning
  artifacts, then map those artifacts into OpenSpec changes.
- Trademark terms require attribution care even when the code license is MIT.

Initial adapter behavior:

- Resolve `bmad-method` from PATH or use `npx -y bmad-method@<pinned>`.
- Run BMAD planning in a controlled directory, preferably a managed worktree or
  dedicated planning output folder.
- Treat BMAD outputs as planning artifacts:
  - Product Brief / PRFAQ -> OpenSpec proposal background and goals
  - PRD -> OpenSpec requirements and acceptance criteria
  - UX spec -> design notes and user interaction constraints
  - Architecture / ADRs -> OpenSpec design and migration notes
  - Epics / Stories -> OpenSpec tasks or separate OpenSpec changes
  - Readiness result -> Requirements Integrity Gate input
- Do not claim BMAD agents are automatically executed by this harness unless a
  future host-level SubAgent runtime explicitly implements that behavior.

Vendoring condition:

- Only vendor BMAD if command/module adapter cannot expose required planning
  templates or workflows reliably.
- If vendored, keep original license, trademark notice, package metadata, and a
  local `NOTICE`.
- Keep official module content read-only where possible and put harness
  customization in adapters or generated configuration.

## Proposed Local Adapter Interfaces

These are design targets for T87 and later runtime tasks.

```text
UpstreamToolResolver
  - resolve pinned executable or npx command
  - report version and source
  - enforce telemetry and network policy

OpenSpecChangeProvider
  - init/update project OpenSpec assets
  - create/read/validate change contract
  - parse proposal/design/tasks/spec deltas
  - archive/sync specs

BMADPlanningProvider
  - run selected planning workflow
  - collect generated planning artifacts
  - classify readiness for OpenSpec

HarnessChangeMapper
  - map upstream artifacts into task spec metadata
  - map task checklist into harness checkpoints
  - map spec delta into route and requirements context
```

## Security and Compliance Rules

- Do not upload project content to external services.
- Disable OpenSpec telemetry for harness-managed executions.
- Treat BMAD trademark notices as attribution requirements in any user-facing
  documentation or package metadata.
- Pin versions for deterministic installs.
- Block execution if upstream version cannot be reported.
- Block vendoring if license, package metadata, or attribution files are
  missing.
- Do not persist raw upstream command output if it includes sensitive local
  paths, internal links, or project content.
- Run upstream commands from the effective task worktree, not from an unrelated
  dirty checkout.

## Runtime Recommendation

For the next implementation slice, do not copy source code yet.

Implement a small read-only resolver and decision record check first:

1. `codex openspec upstream status`
2. `codex openspec upstream verify --tool openspec`
3. `codex openspec upstream verify --tool bmad`

Only after those commands can report pinned version, license source, executable,
telemetry policy, and install mode should the project add write-capable adapters.

## Rejected Options

### Rewrite OpenSpec/BMAD Core Locally

Rejected because it would drift from upstream behavior, duplicate a large
surface area, and recreate bugs already handled upstream.

### Directly Copy Both Repositories Now

Rejected for this slice because vendoring before a package boundary and update
strategy exists would create unnecessary license, dependency, security, and
maintenance risk.

### Replace Harness Execution With BMAD

Rejected because harness already owns task lifecycle, workspace routing,
session-worktree governance, verification runner, memory safety, and final
review gate. BMAD is upstream planning input, not the harness runtime.

## Follow-Up Tasks

- T87: implement strict Requirements Integrity Gate runtime and before-write
  blocking.
- T87 should also fix the current false positive where documentation/tooling
  governance tasks that mention adapter work are classified as `feature_story`
  and blocked for missing product acceptance criteria.
- Add upstream status/verify commands before any vendoring.
- Add tests that force telemetry opt-out in OpenSpec invocations.
- Add tests that BMAD outputs are planning inputs and do not claim automatic
  SubAgent execution.
- Add a vendoring checklist if command adapters prove insufficient.
