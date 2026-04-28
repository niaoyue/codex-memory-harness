from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from harness_controller import checkpoint_task


COMMAND_CONFIG = ".codex/harness/commands.json"
PROJECT_PROFILE = ".codex/harness/project_profile.json"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_OUTPUT_CHARS = 1200
DEFAULT_PROFILE = "primary"
BLOCKED_PATTERNS = (
    "rm -rf",
    "git reset --hard",
    "git clean",
    "remove-item -recurse",
    "remove-item -force -recurse",
    "format ",
    "shutdown ",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
)


@dataclass
class CommandSpec:
    name: str
    command: str = ""
    argv: list[str] = field(default_factory=list)
    description: str = ""
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    touched_paths: list[str] = field(default_factory=list)
    allow_shell: bool = False


def _project_root(value: str | None) -> Path:
    return Path(value or os.environ.get("CODEX_MEMORY_CWD") or Path.cwd()).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _as_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=True)


def _display_command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv) if os.name == "nt" else " ".join(shlex.quote(item) for item in argv)


def load_commands(project_root: Path) -> tuple[dict[str, CommandSpec], dict[str, Any]]:
    config = _load_json(project_root / COMMAND_CONFIG)
    settings = config.get("settings") if isinstance(config.get("settings"), dict) else {}
    default_timeout = _as_int(settings.get("default_timeout_seconds"), DEFAULT_TIMEOUT_SECONDS)
    commands: dict[str, CommandSpec] = {}

    raw_commands = config.get("commands") if isinstance(config.get("commands"), dict) else {}
    for name, value in raw_commands.items():
        if isinstance(value, str):
            spec = CommandSpec(name=name, command=value, timeout_seconds=default_timeout)
        elif isinstance(value, dict):
            argv = _string_list(value.get("argv"))
            command = str(value.get("command") or "")
            if argv and not command:
                command = _display_command(argv)
            spec = CommandSpec(
                name=name,
                command=command,
                argv=argv,
                description=str(value.get("description") or ""),
                timeout_seconds=_as_int(value.get("timeout_seconds"), default_timeout),
                touched_paths=_string_list(value.get("touched_paths")),
                allow_shell=bool(value.get("allow_shell", False)),
            )
        else:
            raise ValueError(f"Unsupported command config for {name!r}.")
        if not spec.command.strip() and not spec.argv:
            raise ValueError(f"Command {name!r} is empty.")
        commands[name] = spec
    return commands, settings


def load_profile(project_root: Path) -> dict[str, Any]:
    return _load_json(project_root / PROJECT_PROFILE)


def select_command_names(args: argparse.Namespace, commands: dict[str, CommandSpec]) -> list[str]:
    if args.all:
        return list(commands)
    if args.selected_commands:
        return args.selected_commands

    profile = load_profile(args.project_root_path)
    verification = profile.get("verification") if isinstance(profile.get("verification"), dict) else {}
    profile_name = args.profile or verification.get("default_profile") or DEFAULT_PROFILE
    names = verification.get(profile_name)
    if not names:
        raise ValueError(f"Verification profile not found or empty: {profile_name}")
    return _string_list(names)


def assert_safe_command(spec: CommandSpec) -> None:
    command_texts = [spec.command]
    if spec.argv:
        command_texts.append(_display_command(spec.argv))
    for command_text in [text for text in command_texts if text.strip()]:
        normalized = " ".join(command_text.lower().split())
        blocked = [pattern for pattern in BLOCKED_PATTERNS if pattern in normalized]
        if blocked:
            raise ValueError(f"Command {spec.name!r} contains blocked pattern: {blocked[0]}")
    if spec.allow_shell and not spec.command.strip():
        raise ValueError(f"Command {spec.name!r} allows shell execution but has no command string.")


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _redact(text: Any) -> str:
    redacted = _to_text(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _excerpt(text: Any, limit: int) -> str:
    clean = _redact(text).strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "\n...[truncated]"


def run_command(spec: CommandSpec, project_root: Path, max_output_chars: int) -> dict[str, Any]:
    assert_safe_command(spec)
    start = time.perf_counter()
    timed_out = False
    command: str | list[str]
    if spec.allow_shell:
        command = spec.command
    else:
        command = spec.argv or _split_command(spec.command)
        if not command:
            raise ValueError(f"Command {spec.name!r} is empty.")
    try:
        completed = subprocess.run(
            command,
            cwd=str(project_root),
            shell=spec.allow_shell,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=spec.timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = exc.stdout
        stderr = exc.stderr or f"Command timed out after {spec.timeout_seconds}s."

    duration = round(time.perf_counter() - start, 3)
    return {
        "name": spec.name,
        "description": spec.description,
        "ok": exit_code == 0 and not timed_out,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "timeout_seconds": spec.timeout_seconds,
        "stdout_excerpt": _excerpt(stdout, max_output_chars),
        "stderr_excerpt": _excerpt(stderr, max_output_chars),
        "touched_paths": spec.touched_paths,
    }


def run_verifications(args: argparse.Namespace) -> dict[str, Any]:
    project_root = args.project_root_path
    commands, settings = load_commands(project_root)
    max_output_chars = _as_int(settings.get("max_output_chars"), DEFAULT_MAX_OUTPUT_CHARS)
    names = select_command_names(args, commands)
    missing = [name for name in names if name not in commands]
    if missing:
        raise ValueError(f"Unknown verification command(s): {', '.join(missing)}")

    results = [run_command(commands[name], project_root, max_output_chars) for name in names]
    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    payload = {
        "tool_name": "verification_runner",
        "phase": "verification",
        "summary": f"Verification runner executed {len(results)} command(s): {passed} passed, {failed} failed.",
        "touched_paths": sorted({path for result in results for path in result.get("touched_paths", [])}),
        "exit_code": 0 if failed == 0 else 1,
        "signals": {
            "passed": passed,
            "failed": failed,
            "results": results,
        },
        "next_step": "修复失败验证或完成任务" if failed else "完成任务或继续下一项增强",
    }
    checkpoint = None
    if args.task_id and not args.no_checkpoint:
        checkpoint_args = argparse.Namespace(
            project_root=str(project_root),
            task_id=args.task_id,
            result_file=None,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        checkpoint = checkpoint_task(checkpoint_args)
    return {"ok": failed == 0, "payload": payload, "checkpoint": checkpoint}


def list_commands(project_root: Path) -> dict[str, Any]:
    commands, settings = load_commands(project_root)
    return {
        "settings": settings,
        "commands": [asdict(spec) for spec in commands.values()],
        "profile": load_profile(project_root).get("verification", {}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run configured Codex harness verifications.")
    parser.add_argument("--project-root", help="Project root that contains .codex/harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List configured verification commands.")

    run = subparsers.add_parser("run", help="Run verification commands.")
    run.add_argument("--task-id", help="Harness task id for checkpoint recording.")
    run.add_argument("--command", dest="selected_commands", action="append", help="Command name to run.")
    run.add_argument("--profile", help="Verification profile name from project_profile.json.")
    run.add_argument("--all", action="store_true", help="Run every command in commands.json.")
    run.add_argument("--no-checkpoint", action="store_true", help="Do not write harness checkpoint.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.project_root_path = _project_root(args.project_root)
    if args.command == "list":
        result = list_commands(args.project_root_path)
    elif args.command == "run":
        result = run_verifications(args)
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
