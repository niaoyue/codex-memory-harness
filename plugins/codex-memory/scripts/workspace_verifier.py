from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import verification_runner
import workspace_router
import diagnostic_gate
from harness_controller import checkpoint_task
from task_spec import task_spec_path


def aggregate_verification(
    project_root: Path,
    route_plan: dict[str, Any],
    *,
    no_run: bool = False,
) -> dict[str, Any]:
    commands, settings = verification_runner.load_commands(project_root)
    profile = verification_runner.load_profile(project_root)
    verification = profile.get("verification") if isinstance(profile.get("verification"), dict) else {}
    max_output_chars = verification_runner._as_int(
        settings.get("max_output_chars"),
        verification_runner.DEFAULT_MAX_OUTPUT_CHARS,
    )

    plan = normalize_verification_plan(route_plan.get("verification_plan"))
    results: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for target in [item for item in plan if isinstance(item, dict)]:
        project_id = str(target.get("project_id") or "")
        cwd = str(target.get("cwd") or "")
        verification_cwd = str(target.get("verification_cwd") or cwd)
        domain = str(target.get("domain") or "")
        blocking = bool(target.get("blocking", True))
        for profile_id in string_list(target.get("verification_profile_ids")):
            command_names = string_list(verification.get(profile_id))
            if not command_names:
                gaps.append(gap(project_id, profile_id, f"verification profile not found: {profile_id}", blocking))
                continue
            for command_name in command_names:
                spec = commands.get(command_name)
                if spec is None:
                    gaps.append(gap(project_id, profile_id, f"verification command not found: {command_name}", blocking))
                    continue
                if no_run:
                    results.append(skipped_result(project_id, domain, verification_cwd, profile_id, command_name, blocking))
                    continue
                command_spec = replace(spec, cwd=spec.cwd or verification_cwd)
                try:
                    result = verification_runner.run_command(command_spec, project_root, max_output_chars)
                except (OSError, RuntimeError, ValueError) as exc:
                    gaps.append(gap(project_id, profile_id, f"verification command could not run: {exc}", blocking))
                    continue
                results.append(
                    result_entry(
                        project_id,
                        domain,
                        str(result.get("cwd") or command_spec.cwd or cwd),
                        profile_id,
                        command_name,
                        blocking,
                        result,
                    )
                )

    gates = release_gates(project_root, route_plan)
    overall_status = status(results, gaps, gates)
    return {
        "version": 1,
        "task_id": str(route_plan.get("task_id") or "workspace-route"),
        "route_plan_id": str(route_plan.get("route_plan_id") or ""),
        "overall_status": overall_status,
        "verification_plan": plan,
        "results": results,
        "release_gates": gates,
        "gaps": gaps,
    }


def gap(project_id: str, profile_id: str, reason: str, blocking: bool) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "profile_id": profile_id,
        "reason": reason,
        "blocking": blocking,
    }


def normalize_verification_plan(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    targets: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        targets.append(
            {
                "project_id": str(item.get("project_id") or ""),
                "domain": str(item.get("domain") or ""),
                "cwd": str(item.get("cwd") or ""),
                "verification_cwd": str(item.get("verification_cwd") or item.get("cwd") or ""),
                "verification_profile_ids": string_list(item.get("verification_profile_ids")),
                "blocking": bool(item.get("blocking", True)),
            }
        )
    return targets


def skipped_result(
    project_id: str,
    domain: str,
    cwd: str,
    profile_id: str,
    command_id: str,
    blocking: bool,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "domain": domain,
        "profile_id": profile_id,
        "command_id": command_id,
        "cwd": cwd,
        "status": "skipped",
        "blocking": blocking,
        "skip_reason": "no_run requested",
    }


def result_entry(
    project_id: str,
    domain: str,
    cwd: str,
    profile_id: str,
    command_id: str,
    blocking: bool,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "domain": domain,
        "profile_id": profile_id,
        "command_id": command_id,
        "cwd": cwd,
        "status": "passed" if result.get("ok") else "failed",
        "blocking": blocking,
        "exit_code": result.get("exit_code"),
        "command": str(result.get("name") or command_id),
        "duration_seconds": result.get("duration_seconds"),
        "stdout_excerpt": str(result.get("stdout_excerpt") or ""),
        "stderr_excerpt": str(result.get("stderr_excerpt") or ""),
        "summary": "passed" if result.get("ok") else "failed",
    }


def status(results: list[dict[str, Any]], gaps: list[dict[str, Any]], gates: dict[str, Any]) -> str:
    if any(item.get("status") == "failed" and item.get("blocking") for item in results):
        return "failed"
    if any(item.get("blocking") for item in gaps):
        return "gap"
    if any(gate.get("blocking") and gate.get("status") != "passed" for gate in gates.values()):
        return "blocked"
    if not results and not gaps:
        return "not_run"
    if any(item.get("status") == "skipped" for item in results):
        return "not_run"
    return "passed"


def release_gates(project_root: Path, route_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "diagnostic_logging_disabled": diagnostic_gate.evaluate_release_gate(project_root, route_plan)
    }


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_route_plan(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("route_plan"), dict):
        return value["route_plan"]
    if not isinstance(value, dict):
        raise ValueError("Route file root must be a JSON object.")
    return value


def checkpoint(project_root: Path, task_id: str, aggregation: dict[str, Any]) -> dict[str, Any]:
    failed = aggregation["overall_status"] not in {"passed", "not_run"}
    payload = {
        "tool_name": "workspace_verifier",
        "phase": "workspace_verification",
        "summary": f"Workspace verification aggregation status: {aggregation['overall_status']}.",
        "touched_paths": [],
        "exit_code": 1 if failed else 0,
        "signals": {
            "verification_aggregation": aggregation,
        },
        "next_step": "修复验证失败或补齐验证缺口" if failed else "完成任务或继续下一项增强",
    }
    args = argparse.Namespace(
        project_root=str(project_root),
        task_id=task_id,
        result_file=None,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    return checkpoint_task(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate workspace verification from a route plan.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--route-file")
    parser.add_argument("--task-file")
    parser.add_argument("--task-id")
    parser.add_argument("--objective")
    parser.add_argument("--working-set", action="append", default=[])
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--auto", action="store_true", help="Alias for automatic route planning when no route file is provided.")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--no-run", action="store_true")
    parser.add_argument("--no-checkpoint", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    route_plan = load_route_plan(args.route_file)
    if not route_plan:
        task = workspace_router.load_task(args.task_file)
        if args.task_id:
            task["task_id"] = args.task_id
        if args.objective:
            task["objective"] = args.objective
        if args.working_set:
            task["working_set"] = workspace_router.string_list(task.get("working_set")) + args.working_set
        route_plan = workspace_router.build_route_plan(
            project_root,
            task,
            changed=args.changed,
            max_depth=max(args.max_depth, 0),
        )

    aggregation = aggregate_verification(project_root, route_plan, no_run=args.no_run)
    checkpoint_result = None
    checkpoint_task_id = string(args.task_id) or string(route_plan.get("task_id"))
    if checkpoint_task_id and not args.no_checkpoint and task_spec_path(project_root, checkpoint_task_id).exists():
        checkpoint_result = checkpoint(project_root, checkpoint_task_id, aggregation)

    ok = aggregation["overall_status"] in {"passed", "not_run"}
    result = {
        "ok": ok,
        "mode": "verify",
        "route_plan": route_plan,
        "verification_aggregation": aggregation,
        "checkpoint": checkpoint_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
