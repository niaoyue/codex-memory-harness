from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import workspace_scanner
from api_authority_common import (
    AUTO_INSTALL_POLICY,
    detect_codex_mcp_servers,
    normalize_path,
    path_in_project,
    read_json_object,
    string_list,
)
from api_authority_sources import (
    build_recommendations,
    global_task_authorities,
    project_authority_plan,
)


VERSION = 1


def build_authority_plan(
    workspace_root: Path,
    task: dict[str, Any] | None = None,
    *,
    max_depth: int = 2,
    installed_mcp_servers: list[str] | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    root = workspace_root.resolve()
    task_payload = normalize_task(task)
    config_home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    mcp_servers = sorted(
        installed_mcp_servers
        if installed_mcp_servers is not None
        else detect_codex_mcp_servers(config_home)
    )
    inventory = workspace_scanner.scan_workspace(root, max_depth=max(max_depth, 0))
    projects = select_relevant_projects(inventory, task_payload)
    project_plans = [
        project_authority_plan(root, project, mcp_servers)
        for project in projects
    ]
    global_plans = global_task_authorities(task_payload, mcp_servers)
    unmatched_project_id = unmatched_explicit_project_id(inventory, task_payload)
    unmatched_paths = unmatched_working_set(inventory, task_payload)
    return {
        "version": VERSION,
        "ok": True,
        "mode": "readonly_authority_plan",
        "workspace_root": str(root),
        "task_id": task_payload.get("task_id") or None,
        "network_used": False,
        "auto_install_performed": False,
        "auto_install_policy": AUTO_INSTALL_POLICY,
        "inventory_source": inventory.get("workspace", {}).get("source"),
        "mcp": {
            "installed_servers": mcp_servers,
            "install_policy": AUTO_INSTALL_POLICY,
            "resources_checked_by_host": False,
        },
        "projects": project_plans,
        "global_authorities": global_plans,
        "recommendations": build_recommendations(project_plans, global_plans),
        "blocked": bool(unmatched_project_id) or bool(unmatched_paths) or (not project_plans and not global_plans),
        "unmatched_working_set": unmatched_paths,
        "unmatched_project_id": unmatched_project_id,
    }


def normalize_task(task: dict[str, Any] | None) -> dict[str, Any]:
    if not task:
        return {}
    result = dict(task)
    result["working_set"] = string_list(
        task.get("working_set")
        or task.get("paths")
        or task.get("files")
    )
    text_parts = (
        string_list(task.get("objective"))
        + string_list(task.get("user_request"))
        + string_list(task.get("text"))
    )
    result["text"] = " ".join(text_parts)
    return result


def select_relevant_projects(inventory: dict[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
    projects = [item for item in inventory.get("projects", []) if isinstance(item, dict)]
    explicit_ids = explicit_project_ids(task)
    if explicit_ids:
        selected = [project for project in projects if project.get("id") in explicit_ids]
        if len(selected) == len(explicit_ids):
            return selected
        return []
    root = Path(str(inventory.get("workspace", {}).get("root") or ".")).resolve(strict=False)
    working_set = [
        normalize_working_set_path(path, root)
        for path in string_list(task.get("working_set"))
    ]
    if not working_set:
        return projects
    child_scopes = [
        str(project.get("cwd") or ".").replace("\\", "/").strip("/")
        for project in projects
        if str(project.get("cwd") or ".").replace("\\", "/").strip("/") not in {"", "."}
    ]
    selected = [
        project for project in projects
        if any(path_matches_project(path, project, child_scopes) for path in working_set)
    ]
    return selected


def unmatched_explicit_project_id(inventory: dict[str, Any], task: dict[str, Any]) -> str | None:
    explicit_ids = explicit_project_ids(task)
    if not explicit_ids:
        return None
    projects = [item for item in inventory.get("projects", []) if isinstance(item, dict)]
    project_ids = {str(project.get("id") or "") for project in projects}
    unmatched = [project_id for project_id in explicit_ids if project_id not in project_ids]
    return ",".join(unmatched) if unmatched else None


def explicit_project_ids(task: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("project_id", "primary_project", "primary_project_id"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    values.extend(string_list(task.get("project_ids")))
    values.extend(string_list(task.get("affected_projects")))
    return sorted(set(values))


def unmatched_working_set(inventory: dict[str, Any], task: dict[str, Any]) -> list[str]:
    projects = [item for item in inventory.get("projects", []) if isinstance(item, dict)]
    explicit_ids = explicit_project_ids(task)
    if explicit_ids:
        projects = [project for project in projects if project.get("id") in explicit_ids]
    root = Path(str(inventory.get("workspace", {}).get("root") or ".")).resolve(strict=False)
    paths = [
        normalize_working_set_path(path, root)
        for path in string_list(task.get("working_set"))
    ]
    child_scopes = [
        str(project.get("cwd") or ".").replace("\\", "/").strip("/")
        for project in projects
        if str(project.get("cwd") or ".").replace("\\", "/").strip("/") not in {"", "."}
    ]
    return [
        path for path in paths
        if not any(path_matches_project(path, project, child_scopes) for project in projects)
    ]


def path_matches_project(path: str, project: dict[str, Any], child_scopes: list[str]) -> bool:
    if path == ".." or path.startswith("../"):
        return False
    cwd = str(project.get("cwd") or ".").replace("\\", "/").strip("/")
    if cwd in {"", "."} and any(path_in_project(path, scope) for scope in child_scopes):
        return False
    return path_in_project(path, cwd or ".")


def normalize_working_set_path(value: str, workspace_root: Path) -> str:
    text = str(value or "").strip()
    if not text:
        return "."
    try:
        path = Path(text)
        if path.is_absolute():
            try:
                return path.resolve(strict=False).relative_to(workspace_root).as_posix()
            except ValueError:
                return f"../{path.resolve(strict=False).as_posix().lstrip('/')}"
    except (OSError, RuntimeError, ValueError):
        pass
    if re.match(r"^[A-Za-z]:", text):
        return f"../{normalize_path(text)}"
    if text.startswith(("/", "\\")):
        rooted = normalize_path(text)
        return f"../{rooted}" if rooted != "." else ".."
    normalized = normalize_path(text)
    root_text = workspace_root.as_posix().rstrip("/")
    if normalized.lower().startswith(f"{root_text.lower()}/"):
        return normalized[len(root_text) + 1 :].strip("/") or "."
    if ".." in normalized.split("/"):
        try:
            resolved = (workspace_root / normalized).resolve(strict=False)
            return resolved.relative_to(workspace_root).as_posix()
        except ValueError:
            return f"../{resolved.as_posix().lstrip('/')}"
        except (OSError, RuntimeError):
            return f"../{normalized}"
    return normalized


def load_task(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.task_file:
        payload.update(load_explicit_task_file(Path(args.task_file)))
    if args.payload_json:
        inline = json.loads(args.payload_json)
        if not isinstance(inline, dict):
            raise ValueError("--payload-json must be a JSON object")
        payload.update(inline)
    if args.task_id:
        payload["task_id"] = args.task_id
    if args.objective:
        payload["objective"] = args.objective
    if args.working_set:
        payload["working_set"] = args.working_set
    return payload


def load_explicit_task_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"task file is missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"task file is not valid JSON: {path}: {exc}") from None
    if not isinstance(value, dict):
        raise ValueError(f"task file must contain a JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only API authority plan.")
    parser.add_argument("--workspace-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--mcp-server", action="append", default=[])
    parser.add_argument("--task-file")
    parser.add_argument("--payload-json")
    parser.add_argument("--task-id")
    parser.add_argument("--objective")
    parser.add_argument("--working-set", action="append", default=[])
    parser.add_argument("command", nargs="?", choices=["plan", "doctor"], default="plan")
    args = parser.parse_args()

    try:
        task = load_task(args)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    result = build_authority_plan(
        Path(args.workspace_root),
        task,
        max_depth=args.max_depth,
        installed_mcp_servers=args.mcp_server or None,
        codex_home=args.codex_home,
    )
    result["command"] = args.command
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
