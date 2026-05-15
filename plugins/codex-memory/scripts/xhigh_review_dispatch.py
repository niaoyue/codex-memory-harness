from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_PYTHON_MAJOR = 3
REQUIRED_PYTHON_MINOR = 11
PYTHON_RUNTIME_CANDIDATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("py", ("-3",)),
    ("python", ()),
    ("python3", ()),
)
XHIGH_REVIEW_IDLE_SECONDS = 1800
XHIGH_REVIEW_COMMIT_REF = "HEAD"
XHIGH_REVIEW_COMMIT_ENV = "CODEX_XHIGH_REVIEW_COMMIT"
CODEX_MEMORY_CWD_ENV = "CODEX_MEMORY_CWD"
REVIEW_COMMIT_CWD_KEYS = ("project_root", "workspace_root", "memory_cwd")
XHIGH_REVIEW_ALIAS_COMMAND = f"codex xhigh review --commit {XHIGH_REVIEW_COMMIT_REF}"
XHIGH_REVIEW_FALLBACK_COMMAND = (
    f'codex-raw -- review -c model_reasoning_effort="xhigh" --commit {XHIGH_REVIEW_COMMIT_REF}'
)
DISPATCH_PERMISSION_SOURCE = "AGENTS.md standing user authorization and review gate policy"
REVIEW_RUNNER_RATE_LIMIT_BACKOFF_SECONDS = 20
REVIEW_RUNNER_TRANSIENT_BACKOFF_SECONDS = 2
REVIEW_RUNNER_UNLIMITED_RESUME_ATTEMPTS: int | None = None
REVIEW_RUNNER_MAX_RESUME_ATTEMPTS = 1
REVIEW_RUNNER_RESUME_MESSAGE = (
    "Continue the same xhigh review gate session after the recoverable infrastructure failure. "
    "Do not restart the review gate while this XHigh Review Runner session is still active. "
    "Reuse the existing transcript and already observed review progress; only re-read the diff if needed. "
    "A capacity, 5xx, or timeout interruption is not a passing review result."
)


@dataclass(frozen=True)
class PythonRuntime:
    command: str
    prefix_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewCommitTarget:
    ref: str
    cwd: Path | None = None


def build_dispatch_plan(route_plan: dict[str, Any]) -> dict[str, Any]:
    task_id = string(route_plan.get("task_id")) or "workspace-route"
    route_plan_id = string(route_plan.get("route_plan_id"))
    dispatch_id = "dispatch-xhigh-review-runner"
    commit_target = review_commit_target(route_plan)
    commit_ref = commit_target.ref
    command = runner_command(commit_ref=commit_ref, cwd=commit_target.cwd)
    alias = alias_command(commit_ref)
    fallback = fallback_command(commit_ref)
    message = (
        "Role: XHigh Review Runner\n"
        "Standing user authorization: AGENTS.md and review gate policy authorize the host to start this specified-role SubAgent when host_spawn_requests are present; do not ask the user to repeat the SubAgent request.\n"
        "Do not modify files, commit, push, format, or revert anything.\n"
        f"Run this explicit runner command in the repository root: {command}\n"
        f"Review commit ref: {commit_ref}. Review only the changes introduced by this commit.\n"
        f"After creating a follow-up fix commit, set {XHIGH_REVIEW_COMMIT_ENV} to that new commit SHA or store review_commit_ref in the route plan before rerunning the gate.\n"
        "Do not replace the explicit runner command with the review alias unless explicitly asked; non-interactive SubAgent shells may bypass the PowerShell profile wrapper.\n"
        "If this XHigh Review Runner SubAgent is still active after a model capacity, 5xx, or timeout failure, the host must send this same runner a continue instruction before starting a new review gate.\n"
        f"Use per-failure backoff from recoverable_failure_policy: model capacity or 429 waits {REVIEW_RUNNER_RATE_LIMIT_BACKOFF_SECONDS} seconds and may continue while the session stays active; 5xx or timeout waits {REVIEW_RUNNER_TRANSIENT_BACKOFF_SECONDS} seconds and is resumed at most once.\n"
        f"Use this continue instruction after the selected backoff: {REVIEW_RUNNER_RESUME_MESSAGE}\n"
        f"Use the codex-raw fallback command ({fallback}) only when the runner session is closed, missing, unrecoverable, or the reviewed commit ref changed.\n"
        f"Monitor stdout/stderr with a {XHIGH_REVIEW_IDLE_SECONDS}-second idle/no-output observation window; this is not a fixed total timeout.\n"
        "Ongoing output means the review is still active.\n"
        "Do not wrap the SubAgent or review runner in any fixed timeout. Host wait windows are observation polls only; continue observing instead of interrupting solely because a wait window expires.\n"
        "Return the command, fallback status, exit code, blocking findings, key findings, and timeout/failure reason."
    )
    return {
        "version": 1,
        "task_id": task_id,
        "route_plan_id": route_plan_id,
        "status": "ready",
        "execution_model": "host_subagent_or_manual",
        "autostart": False,
        "host_spawn_requests": [
            {
                "dispatch_id": dispatch_id,
                "binding_id": "binding-xhigh-review-runner",
                "subagent_id": "agent-xhigh-review-runner",
                "role": "XHigh Review Runner",
                "agent_type": "XHigh Review Runner",
                "fork_context": True,
                "specified_role_subagent_required": True,
                "standing_user_authorization": True,
                "dispatch_permission_source": DISPATCH_PERMISSION_SOURCE,
                "host_tool_mapping": "spawn_agent.agent_type",
                "dependencies": [],
                "message": message,
                "checkpoint_required": True,
                "scope_guard_required": False,
                "command": command,
                "alias_command": alias,
                "fallback_command": fallback,
                "review_commit_ref": commit_ref,
                "recoverable_failure_policy": recoverable_failure_policy(),
                "timeout_policy": "progress_output_observation",
                "idle_policy": "stdout_stderr_no_progress_only",
                "total_timeout_policy": "none",
                "observation_window_policy": "poll_only_never_interrupt",
                "no_fixed_total_timeout": True,
            }
        ],
        "items": [
            {
                "dispatch_id": dispatch_id,
                "binding_id": "binding-xhigh-review-runner",
                "subagent_id": "agent-xhigh-review-runner",
                "role": "XHigh Review Runner",
                "binding_mode": "review_gate_runner",
                "status": "queued",
                "dependencies": [],
                "prompt": message,
            }
        ],
        "completion_gate": {
            "requires_checkpoint": True,
            "requires_scope_guard": False,
            "requires_verification": False,
        },
    }


def runner_command(*, commit_ref: str | None = None, cwd: Path | None = None) -> str:
    return command_line(runner_command_parts(commit_ref=commit_ref, cwd=cwd))


def alias_command(commit_ref: str) -> str:
    return f"codex xhigh review --commit {commit_ref}"


def fallback_command(commit_ref: str) -> str:
    return f'codex-raw -- review -c model_reasoning_effort="xhigh" --commit {commit_ref}'


def review_commit_ref(route_plan: dict[str, Any] | None = None, environ: dict[str, str] | None = None) -> str:
    return review_commit_target(route_plan, environ).ref


def review_commit_target(
    route_plan: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> ReviewCommitTarget:
    metadata = route_plan.get("metadata") if isinstance(route_plan, dict) and isinstance(route_plan.get("metadata"), dict) else {}
    configured = (
        string(route_plan.get("review_commit_ref")) if isinstance(route_plan, dict) else ""
    ) or string(metadata.get("review_commit_ref"))
    env = os.environ if environ is None else environ
    cwds = review_commit_cwds(route_plan, env)
    if configured:
        return resolve_git_commit_target(configured, cwd_candidates=cwds)
    return resolve_git_commit_target(
        string(env.get(XHIGH_REVIEW_COMMIT_ENV)) or XHIGH_REVIEW_COMMIT_REF,
        cwd_candidates=cwds,
    )


def review_commit_cwd(route_plan: dict[str, Any] | None, environ: dict[str, str]) -> Path | None:
    return review_commit_cwds(route_plan, environ)[0]


def review_commit_cwds(route_plan: dict[str, Any] | None, environ: dict[str, str]) -> list[Path | None]:
    metadata = route_plan.get("metadata") if isinstance(route_plan, dict) and isinstance(route_plan.get("metadata"), dict) else {}
    candidates: list[str] = []
    if isinstance(route_plan, dict):
        candidates.extend(string(route_plan.get(key)) for key in REVIEW_COMMIT_CWD_KEYS)
    candidates.extend(string(metadata.get(key)) for key in REVIEW_COMMIT_CWD_KEYS)
    candidates.append(string(environ.get(CODEX_MEMORY_CWD_ENV)))
    resolved: list[Path | None] = []
    for candidate in candidates:
        if candidate:
            path = Path(candidate).resolve(strict=False)
            if path not in resolved:
                resolved.append(path)
    current = Path.cwd()
    if current not in resolved:
        resolved.append(current)
    return resolved or [None]


def resolve_git_commit_ref(
    ref: str,
    *,
    cwd: Path | None = None,
    cwd_candidates: list[Path | None] | None = None,
) -> str:
    return resolve_git_commit_target(ref, cwd=cwd, cwd_candidates=cwd_candidates).ref


def resolve_git_commit_target(
    ref: str,
    *,
    cwd: Path | None = None,
    cwd_candidates: list[Path | None] | None = None,
) -> ReviewCommitTarget:
    value = string(ref)
    if not value:
        return ReviewCommitTarget(ref="")
    candidates = cwd_candidates if cwd_candidates is not None else [cwd]
    for candidate in candidates:
        resolved = try_resolve_git_commit_ref(value, cwd=candidate)
        if resolved:
            return ReviewCommitTarget(ref=resolved, cwd=candidate)
    fallback_cwd = candidates[0] if candidates else cwd
    return ReviewCommitTarget(ref=value, cwd=fallback_cwd)


def try_resolve_git_commit_ref(ref: str, *, cwd: Path | None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    resolved = result.stdout.splitlines()[0].strip() if result.returncode == 0 and result.stdout.splitlines() else ""
    return resolved


def recoverable_failure_policy() -> dict[str, Any]:
    return {
        "version": 1,
        "recoverable_failure_types": [
            "model_capacity",
            "http_429",
            "http_5xx",
            "timeout",
        ],
        "failure_rules": [
            {
                "failure_type": "model_capacity",
                "backoff_seconds": REVIEW_RUNNER_RATE_LIMIT_BACKOFF_SECONDS,
                "max_resume_attempts": REVIEW_RUNNER_UNLIMITED_RESUME_ATTEMPTS,
                "attempt_policy": "while_session_active",
            },
            {
                "failure_type": "http_429",
                "backoff_seconds": REVIEW_RUNNER_RATE_LIMIT_BACKOFF_SECONDS,
                "max_resume_attempts": REVIEW_RUNNER_UNLIMITED_RESUME_ATTEMPTS,
                "attempt_policy": "while_session_active",
            },
            {
                "failure_type": "http_5xx",
                "backoff_seconds": REVIEW_RUNNER_TRANSIENT_BACKOFF_SECONDS,
                "max_resume_attempts": REVIEW_RUNNER_MAX_RESUME_ATTEMPTS,
                "attempt_policy": "single_retry",
            },
            {
                "failure_type": "timeout",
                "backoff_seconds": REVIEW_RUNNER_TRANSIENT_BACKOFF_SECONDS,
                "max_resume_attempts": REVIEW_RUNNER_MAX_RESUME_ATTEMPTS,
                "attempt_policy": "single_retry",
            },
        ],
        "primary_action": "send_input_to_active_review_runner",
        "primary_preconditions": [
            "host_has_active_runner_session_handle",
            "runner_session_not_completed_failed_or_closed",
            "review_commit_ref_unchanged_since_runner_start",
            "reviewed_commit_unchanged_since_runner_start",
        ],
        "resume_message": REVIEW_RUNNER_RESUME_MESSAGE,
        "restart_action": "restart_same_review_gate_command",
        "restart_only_when": [
            "runner_session_closed_missing_or_unrecoverable",
            "host_cannot_send_input_to_runner_session",
            "review_commit_ref_changed_during_review",
            "reviewed_commit_changed_during_review",
        ],
        "pass_condition": "review_gate_must_complete_cleanly",
    }


def runner_command_parts(
    script_path: Path | None = None,
    *,
    commit_ref: str | None = None,
    cwd: Path | None = None,
) -> list[str]:
    script = script_path or Path(__file__).resolve().with_name("review_gate_runner.py")
    script = script.resolve()
    runtime = resolve_python_runtime()
    if commit_ref is None:
        target = review_commit_target()
        commit_ref = target.ref
        cwd = cwd or target.cwd
    review_cwd = str((cwd or Path.cwd()).resolve(strict=False))
    parts = [
        runtime.command,
        *runtime.prefix_args,
        "-X",
        "utf8",
        str(script),
        "--effort",
        "xhigh",
        "--idle-seconds",
        str(XHIGH_REVIEW_IDLE_SECONDS),
        "--max-seconds",
        "0",
        "--cwd",
        review_cwd,
        "--",
        "--commit",
        commit_ref,
    ]
    return parts


def resolve_python_runtime() -> PythonRuntime:
    for name, prefix_args in PYTHON_RUNTIME_CANDIDATES:
        command = shutil.which(name)
        if not command:
            continue
        version = python_version(command, prefix_args)
        if version and supports_python_version(version):
            return PythonRuntime(command=command, prefix_args=prefix_args)
    return PythonRuntime(command=sys.executable)


def python_version(command: str, prefix_args: tuple[str, ...]) -> str:
    probe = [
        command,
        *prefix_args,
        "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
    ]
    try:
        result = subprocess.run(
            probe,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.splitlines()[0].strip() if result.stdout.splitlines() else ""


def supports_python_version(version_text: str) -> bool:
    parts = version_text.split(".")
    if len(parts) < 2:
        return False
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except ValueError:
        return False
    return (major > REQUIRED_PYTHON_MAJOR) or (major == REQUIRED_PYTHON_MAJOR and minor >= REQUIRED_PYTHON_MINOR)


def command_line(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return " ".join(shlex.quote(part) for part in parts)


def string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
