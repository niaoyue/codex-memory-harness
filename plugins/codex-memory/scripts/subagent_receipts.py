from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import workspace_subagents


TERMINAL_FAILURES = {"failed", "blocked", "cancelled"}
SUCCESS_STATUSES = {"completed", "succeeded", "success", "ready", "ready_for_integration"}
CANDIDATE_METADATA_FIELDS = ("branch", "effective_cwd", "base_head", "head", "candidate_commit")


def summarize(
    bindings: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    specialists = [item for item in bindings if item.get("binding_mode") == "specialist"]
    normalized = [normalize_receipt(item) for item in receipts]
    by_binding = {item["binding_id"]: item for item in normalized if item.get("binding_id")}
    missing = [
        {"binding_id": binding.get("binding_id"), "project_id": binding.get("project_id")}
        for binding in specialists
        if binding.get("binding_id") not in by_binding
    ]
    failures = [item for item in normalized if item["status"] in TERMINAL_FAILURES]
    incomplete = [
        item for item in normalized
        if item["status"] not in SUCCESS_STATUSES and item["status"] not in TERMINAL_FAILURES
    ]
    scope_guard = [
        workspace_subagents.check_scope(binding, touched_paths(by_binding.get(str(binding.get("binding_id")))), project_root=project_root)
        for binding in specialists
        if binding.get("binding_id") in by_binding
    ]
    conflicts = workspace_subagents.conflict_report(normalized, project_root=project_root)
    metadata_gaps = [
        gap
        for binding in specialists
        if binding.get("binding_id") in by_binding
        for gap in candidate_metadata_gap(binding, by_binding[str(binding.get("binding_id"))])
    ]
    blockers = []
    blockers.extend({"type": "missing_receipt", **item} for item in missing)
    blockers.extend({"type": "terminal_failure", "binding_id": item.get("binding_id"), "status": item["status"]} for item in failures)
    blockers.extend({"type": "incomplete_receipt", "binding_id": item.get("binding_id"), "status": item["status"]} for item in incomplete)
    blockers.extend(metadata_gaps)
    blockers.extend({"type": "scope_violation", **violation} for item in scope_guard for violation in item.get("violations", []))
    blockers.extend({"type": "path_conflict", **item} for item in conflicts)
    return {
        "version": 1,
        "ok": not blockers,
        "status": "ready_for_integration" if not blockers else "blocked",
        "receipt_count": len(normalized),
        "expected_receipt_count": len(specialists),
        "missing_receipts": missing,
        "terminal_failures": failures,
        "incomplete_receipts": incomplete,
        "scope_guard": scope_guard,
        "conflicts": conflicts,
        "receipt_metadata_gaps": metadata_gaps,
        "blocking_gaps": blockers,
        "integration_plan": {
            "publish_order": workspace_subagents.publish_order(bindings),
            "candidate_branches": candidate_branches(specialists, by_binding),
            "final_gate": "create candidate commit, then run codex xhigh review --commit <commit-sha>",
            "auto_merge": False,
            "merge_preflight_required": True,
            "integration_worktree_required": True,
        },
    }


def normalize_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    status = str(receipt.get("status") or "").strip().lower().replace("-", "_") or "unknown"
    binding_id = str(receipt.get("binding_id") or "").strip()
    return {
        **receipt,
        "status": "completed" if status in SUCCESS_STATUSES else status,
        "binding_id": binding_id,
        "subagent_id": str(receipt.get("subagent_id") or "").strip(),
        "touched_paths": touched_paths(receipt),
    }


def candidate_metadata_gap(binding: dict[str, Any], receipt: dict[str, Any]) -> list[dict[str, Any]]:
    if receipt.get("status") not in {"completed"}:
        return []
    missing = [field for field in CANDIDATE_METADATA_FIELDS if not candidate_metadata_value(receipt, field)]
    if not missing:
        return []
    return [
        {
            "type": "receipt_metadata",
            "binding_id": binding.get("binding_id"),
            "subagent_id": receipt.get("subagent_id"),
            "project_id": binding.get("project_id"),
            "status": receipt.get("status"),
            "missing_fields": missing,
            "reason": "ready or successful specialist receipt is missing candidate commit metadata",
        }
    ]


def candidate_branches(bindings: list[dict[str, Any]], receipts_by_binding: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    branches = []
    for binding in bindings:
        receipt = receipts_by_binding.get(str(binding.get("binding_id")))
        if not receipt or receipt.get("status") != "completed":
            continue
        metadata = {field: candidate_metadata_value(receipt, field) for field in CANDIDATE_METADATA_FIELDS}
        if not all(metadata.values()):
            continue
        branches.append(
            {
                "binding_id": str(binding.get("binding_id") or ""),
                "project_id": str(binding.get("project_id") or ""),
                **metadata,
            }
        )
    return branches


def candidate_metadata_value(receipt: dict[str, Any], field: str) -> str:
    value = receipt.get(field)
    if not value:
        metadata = receipt.get("metadata")
        if isinstance(metadata, dict):
            value = metadata.get(field)
    if not value:
        candidate = receipt.get("candidate")
        if isinstance(candidate, dict):
            value = candidate.get(field)
    return str(value or "").strip()


def touched_paths(receipt: dict[str, Any] | None) -> list[str]:
    if not receipt:
        return []
    value = receipt.get("touched_paths")
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize host SubAgent execution receipts.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--bindings-file", required=True)
    parser.add_argument("--receipt-file", action="append", default=[])
    args = parser.parse_args()
    payload = workspace_subagents.read_json(args.bindings_file)
    bindings = payload.get("bindings") if isinstance(payload.get("bindings"), list) else []
    receipts = workspace_subagents.read_json_list(args.receipt_file)
    result = summarize(bindings, receipts, project_root=Path(args.project_root).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
