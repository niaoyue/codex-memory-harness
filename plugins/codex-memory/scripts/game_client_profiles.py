from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

COMMANDS_FILE = ".codex/harness/commands.json"
PROFILE_FILE = ".codex/harness/project_profile.json"
GAME_CLIENT_FILE = ".codex/harness/game-client.json"
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def build_template(engine: str, project_cwd: str, prefix: str) -> dict[str, Any]:
    command_ids = {
        "quick": f"{prefix}_{engine}_quick",
        "diagnostic": f"{prefix}_{engine}_diagnostic",
        "release": f"{prefix}_{engine}_release",
    }
    profile_ids = {
        "quick": f"{prefix}_quick",
        "diagnostic": f"{prefix}_diagnostic",
        "release": f"{prefix}_release",
    }
    commands = {
        command_ids["quick"]: command_spec(engine, project_cwd, "quick"),
        command_ids["diagnostic"]: command_spec(engine, project_cwd, "diagnostic"),
        command_ids["release"]: command_spec(engine, project_cwd, "release"),
    }
    return {
        "commands": commands,
        "profiles": {
            profile_ids["quick"]: [command_ids["quick"]],
            profile_ids["diagnostic"]: [command_ids["diagnostic"]],
            profile_ids["release"]: [command_ids["release"]],
        },
        "game_client": {
            "version": 1,
            "engine": engine,
            "project_cwd": project_cwd,
            "verification_profiles": profile_ids,
            "ai_diagnostics": {
                "enabled_by_default": False,
                "release_must_be_disabled": True,
                "scopes": ["flow", "state", "validation", "asset_loading"],
            },
        },
    }


def command_spec(engine: str, project_cwd: str, profile: str) -> dict[str, Any]:
    scripts = {
        "unity": unity_script(project_cwd, profile),
        "laya": laya_script(project_cwd, profile),
        "cocos": cocos_script(project_cwd, profile),
    }
    return {
        "description": f"{engine} {profile} verification profile. Requires local engine executable env var.",
        "argv": [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", scripts[engine]],
        "cwd": project_cwd,
        "timeout_seconds": 600 if profile == "release" else 240,
        "touched_paths": [project_cwd],
    }


def unity_script(project_cwd: str, profile: str) -> str:
    method = {"quick": "VerifyQuick", "diagnostic": "VerifyDiagnostic", "release": "VerifyRelease"}[profile]
    return (
        "if (-not $env:UNITY_EXE) { throw 'Set UNITY_EXE to Unity Editor executable.' }; "
        "$projectPath = (Resolve-Path -LiteralPath '.').Path; "
        f"& $env:UNITY_EXE -batchmode -quit -projectPath $projectPath "
        f"-executeMethod CodexHarness.{method} -logFile -"
    )


def laya_script(project_cwd: str, profile: str) -> str:
    method = {"quick": "verifyQuick", "diagnostic": "verifyDiagnostic", "release": "verifyRelease"}[profile]
    return (
        "if (-not $env:LAYA_IDE_EXE) { throw 'Set LAYA_IDE_EXE to LayaAirIDE executable.' }; "
        "$projectPath = (Resolve-Path -LiteralPath '.').Path; "
        f"& $env:LAYA_IDE_EXE \"--project=$projectPath\" --script CodexHarness.{method}"
    )


def cocos_script(project_cwd: str, profile: str) -> str:
    config = {"quick": "codex-quick", "diagnostic": "codex-diagnostic", "release": "codex-release"}[profile]
    return (
        "if (-not $env:COCOS_CREATOR_EXE) { throw 'Set COCOS_CREATOR_EXE to Cocos Creator executable.' }; "
        "$projectPath = (Resolve-Path -LiteralPath '.').Path; "
        f"& $env:COCOS_CREATOR_EXE --project $projectPath --build "
        f"'configPath=build/{config}.json'"
    )


def init_profiles(project_root: Path, engine: str, project_cwd: str, prefix: str, overwrite: bool) -> dict[str, Any]:
    template = build_template(engine, project_cwd, prefix)
    commands_path = project_root / COMMANDS_FILE
    profile_path = project_root / PROFILE_FILE
    game_client_path = project_root / GAME_CLIENT_FILE
    commands_payload = read_json(commands_path) or {"version": 1, "commands": {}}
    profile_payload = read_json(profile_path) or {"version": 1, "verification": {}}
    actions = []

    commands = commands_payload.setdefault("commands", {})
    for name, spec in template["commands"].items():
        if overwrite or name not in commands:
            commands[name] = spec
            actions.append({"action": "write_command", "id": name})
        else:
            actions.append({"action": "keep_command", "id": name})
    verification = profile_payload.setdefault("verification", {})
    for name, command_names in template["profiles"].items():
        if overwrite or name not in verification:
            verification[name] = command_names
            actions.append({"action": "write_profile", "id": name})
        else:
            actions.append({"action": "keep_profile", "id": name})
    write_json(commands_path, commands_payload)
    write_json(profile_path, profile_payload)
    if overwrite or not game_client_path.exists():
        write_json(game_client_path, template["game_client"])
        actions.append({"action": "write_game_client_config", "path": str(game_client_path)})
    else:
        actions.append({"action": "keep_game_client_config", "path": str(game_client_path)})
    return {"ok": True, "engine": engine, "project_cwd": project_cwd, "actions": actions}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate game client harness profile templates.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("command", choices=["init", "template"])
    parser.add_argument("--engine", required=True, choices=["unity", "laya", "cocos"])
    parser.add_argument("--project-cwd", default=".")
    parser.add_argument("--profile-prefix", default="client")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.command == "template":
        result = {"ok": True, "template": build_template(args.engine, args.project_cwd, args.profile_prefix)}
    else:
        result = init_profiles(Path(args.project_root).resolve(), args.engine, args.project_cwd, args.profile_prefix, args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
