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


@dataclass(frozen=True)
class PythonRuntime:
    command: str
    prefix_args: tuple[str, ...] = ()


def build_dispatch_plan(route_plan: dict[str, Any]) -> dict[str, Any]:
    task_id = string(route_plan.get("task_id")) or "workspace-route"
    route_plan_id = string(route_plan.get("route_plan_id"))
    dispatch_id = "dispatch-xhigh-review-runner"
    command = runner_command()
    message = (
        "Role: XHigh Review Runner\n"
        "Do not modify files, commit, push, format, or revert anything.\n"
        f"Run this explicit runner command in the repository root: {command}\n"
        "Do not replace the explicit runner command with the review alias unless explicitly asked; non-interactive SubAgent shells may bypass the PowerShell profile wrapper.\n"
        "If the explicit runner fails for infrastructure reasons, run codex-raw -- review -c model_reasoning_effort=\"xhigh\" --uncommitted.\n"
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
                "agent_type": "worker",
                "fork_context": True,
                "dependencies": [],
                "message": message,
                "checkpoint_required": True,
                "scope_guard_required": False,
                "command": command,
                "alias_command": "codex xhigh review --uncommitted",
                "fallback_command": 'codex-raw -- review -c model_reasoning_effort="xhigh" --uncommitted',
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


def runner_command() -> str:
    return command_line(runner_command_parts())


def runner_command_parts(script_path: Path | None = None) -> list[str]:
    script = script_path or Path(__file__).resolve().with_name("review_gate_runner.py")
    script = script.resolve()
    runtime = resolve_python_runtime()
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
        ".",
        "--",
        "--uncommitted",
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
