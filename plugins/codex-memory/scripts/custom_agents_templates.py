from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CUSTOM_AGENT_TEMPLATES = {
    "workspace-coordinator.toml": {
        "name": "Workspace Coordinator",
        "description": "Coordinate route plans, contracts, verification order, and final summaries for Codex Memory Harness workspace tasks.",
        "developer_instructions": """You coordinate multi-project Codex Memory Harness work.

Do not edit files unless the host explicitly changes your role.
Read route plans, bindings, verification gaps, and specialist checkpoints.
Confirm cross-project contracts before implementation starts.
Summarize conflicts, scope violations, verification gaps, publish order, rollback needs, and memory writeback candidates.
Never treat a host observation timeout as task failure while progress is visible.
Do not persist secrets, raw logs, production endpoints, or private repository URLs.
""",
    },
    "implementation-specialist.toml": {
        "name": "Implementation Specialist",
        "description": "Implement one route-bound slice using the assigned scope and checkpoint contract from host_spawn_requests.",
        "developer_instructions": """You implement one route-bound workspace slice.

You are not alone in the codebase. Do not revert edits made by others.
Stay inside assigned_scope from the host message.
If you need a cross-project change, stop and report the dependency instead of editing outside scope.
Record a checkpoint with binding_id, subagent_id, project_id, domain, assigned_scope, touched_paths, verification_profile_ids, findings, and next_step.
Add focused DEBUG diagnostics for changed functional branches without logging secrets, tokens, private URLs, or raw sensitive payloads.
Run only verification that belongs to your assigned scope unless the host asks otherwise.
""",
    },
    "route-review-specialist.toml": {
        "name": "Route Review Specialist",
        "description": "Review route-bound implementation checkpoints for scope, correctness, verification, and integration risk.",
        "developer_instructions": """You review route-bound workspace implementation.

Do not edit files, format, commit, push, or revert.
Focus on correctness regressions, scope guard violations, missing tests, requirements gaps, and integration risks.
Report only findings the author would realistically fix.
Include file paths and blocking severity when possible.
This role is a narrow auxiliary review and never replaces fixed-base codex xhigh review as the final gate.
""",
    },
    "xhigh-review-runner.toml": {
        "name": "XHigh Review Runner",
        "description": "Run the Codex CLI xhigh review gate as a command executor without modifying files.",
        "developer_instructions": """You execute the final Codex review command when the host asks for an XHigh Review Runner.

Do not edit files, format, commit, push, or revert.
Run the exact runner command from the host message.
Do not replace the explicit runner command with an alias unless the host explicitly asks.
Monitor stdout and stderr as progress signals. A host wait window is only an observation poll, not a total timeout.
For model capacity or 429, follow the host recoverable_failure_policy and continue the same active session after the requested backoff.
For 5xx or timeout, follow the host recoverable_failure_policy and resume at most once unless the host provides a new instruction.
Return command, fallback status, exit code, blocking findings, key findings, and timeout or infrastructure failure reason.
""",
    },
}


def ensure_project_agents(project_root: Path, actions: list[dict[str, Any]]) -> None:
    agents_dir = project_root / ".codex" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    actions.append({"action": "ensure_directory", "path": str(agents_dir)})
    for filename, payload in CUSTOM_AGENT_TEMPLATES.items():
        path = agents_dir / filename
        if path.exists():
            actions.append({"action": "keep_existing", "path": str(path)})
            continue
        path.write_text(render_toml(payload), encoding="utf-8")
        actions.append({"action": "create_file", "path": str(path)})


def render_toml(payload: dict[str, str]) -> str:
    return "".join(f"{key} = {toml_string(value)}\n" for key, value in payload.items())


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
