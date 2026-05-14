from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sensitive_scan
from review_fingerprint import (
    REVIEW_MODES,
    diff_check,
    diff_fingerprint,
    package_boundary_check,
    sensitive_check,
    slice_plan,
    verification_summary,
)
from review_findings import detect_review_findings
import xhigh_review_dispatch


REVIEW_DIR = ".codex/harness/review"
TRANSIENT_FAILURE_WORDS = ("429", "rate limit", "5xx", "timeout", "timed out", "capacity")
FULL_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def preflight(project_root: Path, *, mode: str = "uncommitted", task_id: str = "review") -> dict[str, Any]:
    fingerprint = diff_fingerprint(project_root, mode=mode)
    checks = [
        diff_check(project_root, mode),
        sensitive_check(project_root, mode),
        package_boundary_check(project_root, mode),
        verification_summary(project_root),
    ]
    result = {
        "ok": all(item.get("ok") for item in checks),
        "task_id": task_id,
        "mode": mode,
        "diff_fingerprint": fingerprint,
        "checks": checks,
        "slice_plan": slice_plan(project_root, mode=mode),
        "recorded_at": utc_now(),
    }
    write_json(review_dir(project_root) / "preflight.json", result)
    return result


def status(project_root: Path, *, mode: str = "uncommitted") -> dict[str, Any]:
    fingerprint = diff_fingerprint(project_root, mode=mode)
    latest = latest_ledger(project_root)
    invalidated = bool(latest) and latest.get("diff_fingerprint", {}).get("fingerprint") != fingerprint["fingerprint"]
    return {
        "ok": True,
        "mode": mode,
        "diff_fingerprint": fingerprint,
        "latest_review": latest,
        "review_invalidated": invalidated,
    }


def plan(project_root: Path, *, mode: str = "uncommitted") -> dict[str, Any]:
    return {
        "ok": True,
        "mode": mode,
        "diff_fingerprint": diff_fingerprint(project_root, mode=mode),
        "slice_plan": slice_plan(project_root, mode=mode),
    }


def record_review(
    project_root: Path,
    payload: dict[str, Any],
    *,
    task_id: str = "review",
    mode: str = "uncommitted",
    commit_ref: str = "",
) -> dict[str, Any]:
    current_fingerprint = diff_fingerprint(project_root, mode=mode)
    reviewed_fingerprint = reviewed_diff_fingerprint(payload, project_root=project_root)
    raw_reviewed_commit = reviewed_commit_ref(payload, explicit_commit_ref=commit_ref)
    reviewed_commit = resolve_commit_ref(project_root, raw_reviewed_commit)
    status_value = review_status(payload)
    commit_ref_issue = commit_ref_validation_issue(raw_reviewed_commit, reviewed_commit)
    fingerprint_issue = None if reviewed_commit else fingerprint_validation_issue(reviewed_fingerprint, current_fingerprint)
    if status_value == "clean" and (commit_ref_issue or fingerprint_issue):
        status_value = "invalidated"
    runner_state = runner_status(payload)
    entry = {
        "review_id": f"review-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "task_id": task_id,
        "mode": mode,
        "status": status_value,
        "diff_fingerprint": reviewed_fingerprint or current_fingerprint,
        "current_diff_fingerprint": current_fingerprint,
        "runner_status": runner_state,
        "runner_event": runner_event(payload, runner_state),
        "findings": normalize_findings(payload),
        "recorded_at": utc_now(),
    }
    if reviewed_commit:
        entry["review_commit_ref"] = reviewed_commit
    if commit_ref_issue:
        entry["commit_ref_validation"] = commit_ref_issue
    if fingerprint_issue:
        entry["fingerprint_validation"] = fingerprint_issue
    if runner_state == "infra_failed":
        entry["recoverable_failure_policy"] = xhigh_review_dispatch.recoverable_failure_policy()
    append_jsonl(review_dir(project_root) / "review-ledger.jsonl", entry)
    return {"ok": status_value == "clean", "entry": entry}


def findings_list(project_root: Path) -> dict[str, Any]:
    resolved = resolved_finding_keys(project_root)
    findings = []
    for entry in ledger_entries(project_root):
        review_id = str(entry.get("review_id") or "")
        fingerprint = str((entry.get("diff_fingerprint") or {}).get("fingerprint") or "")
        for item in entry.get("findings") if isinstance(entry.get("findings"), list) else []:
            if not isinstance(item, dict) or item.get("resolution") == "resolved":
                continue
            finding_id = str(item.get("id") or "")
            if finding_key(review_id, fingerprint, finding_id) not in resolved:
                findings.append({**item, "review_id": review_id})
    return {"ok": True, "findings": findings, "requires_final_review_rerun": bool(resolved)}


def resolve_finding(project_root: Path, finding_id: str, *, evidence: str = "", review_id: str = "") -> dict[str, Any]:
    entry = finding_review_scope(project_root, finding_id, review_id=review_id)
    path = review_dir(project_root) / "findings.jsonl"
    event = {
        "event": "resolve",
        "finding_id": finding_id,
        "review_id": entry.get("review_id"),
        "review_fingerprint": (entry.get("diff_fingerprint") or {}).get("fingerprint"),
        "evidence": sensitive_scan.sanitized_payload(evidence, context="review_finding_resolution"),
        "diff_fingerprint": diff_fingerprint(project_root, mode="uncommitted"),
        "recorded_at": utc_now(),
        "requires_final_review_rerun": True,
    }
    append_jsonl(path, event)
    return {"ok": True, "resolution": event}


def ledger_show(project_root: Path) -> dict[str, Any]:
    return {"ok": True, "entries": ledger_entries(project_root)}


def normalize_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    if not raw:
        summary = runner_findings_summary(payload)
        count = int(summary.get("review_findings_count") or 0)
        priorities = summary.get("review_finding_priorities") or []
        raw = [
            {
                "severity": priorities[index] if index < len(priorities) else "unknown",
                "summary": "Structured review finding reported by review runner.",
                "source": "review_runner_summary",
            }
            for index in range(count)
        ]
    findings = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            finding = dict(item)
        else:
            finding = {"summary": str(item)}
        finding.setdefault("id", f"finding-{index:03d}")
        finding.setdefault("resolution", "pending")
        findings.append(sensitive_scan.sanitized_payload(finding, context="review_finding"))
    return findings


def runner_findings_summary(payload: dict[str, Any]) -> dict[str, Any]:
    count = payload.get("review_findings_count")
    priorities = payload.get("review_finding_priorities")
    if isinstance(count, int) and count > 0:
        return {
            "review_findings_count": count,
            "review_finding_priorities": priorities if isinstance(priorities, list) else [],
        }
    return detect_review_findings(payload.get("stdout_tail") or [], payload.get("stderr_tail") or [])


def reviewed_diff_fingerprint(payload: dict[str, Any], *, project_root: Path | None = None) -> dict[str, Any] | None:
    for value in (
        payload.get("diff_fingerprint"),
        payload.get("reviewed_diff_fingerprint"),
        payload.get("preflight", {}).get("diff_fingerprint") if isinstance(payload.get("preflight"), dict) else None,
        preflight_diff_fingerprint(project_root) if project_root is not None else None,
    ):
        if isinstance(value, dict) and isinstance(value.get("fingerprint"), str):
            return dict(value)
    return None


def reviewed_commit_ref(payload: dict[str, Any], *, explicit_commit_ref: str = "") -> str:
    explicit = explicit_commit_ref.strip()
    if explicit:
        return explicit
    for key in ("review_commit_ref", "commit_ref", "commit_sha", "commit"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    command = payload.get("command")
    if isinstance(command, list):
        return commit_ref_from_command([str(item) for item in command])
    if isinstance(command, str):
        return commit_ref_from_command(command.split())
    return ""


def commit_ref_from_command(command: list[str]) -> str:
    for index, item in enumerate(command):
        if item == "--commit" and index + 1 < len(command):
            return command[index + 1].strip()
        if item.startswith("--commit="):
            return item.split("=", 1)[1].strip()
    return ""


def resolve_commit_ref(project_root: Path, ref: str) -> str:
    value = ref.strip()
    if not value:
        return ""
    if value.startswith("-"):
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", f"{value}^{{commit}}"],
            cwd=project_root,
            text=True,
            capture_output=True,
            encoding="utf-8",
            shell=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    resolved = result.stdout.strip()
    return resolved.lower() if result.returncode == 0 and FULL_COMMIT_SHA_RE.fullmatch(resolved) else ""


def commit_ref_validation_issue(raw_ref: str, resolved_ref: str) -> dict[str, Any] | None:
    if raw_ref and not resolved_ref:
        return {"ok": False, "reason": "unresolved_review_commit_ref", "review_commit_ref": raw_ref}
    return None


def preflight_diff_fingerprint(project_root: Path) -> dict[str, Any] | None:
    path = review_dir(project_root) / "preflight.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = payload.get("diff_fingerprint") if isinstance(payload, dict) else None
    return dict(value) if isinstance(value, dict) and isinstance(value.get("fingerprint"), str) else None


def fingerprint_validation_issue(reviewed: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any] | None:
    if not reviewed:
        return {
            "ok": False,
            "reason": "missing_reviewed_diff_fingerprint",
            "current_fingerprint": current["fingerprint"],
        }
    if reviewed.get("mode") != current.get("mode"):
        return {
            "ok": False,
            "reason": "review_mode_mismatch",
            "reviewed_mode": reviewed.get("mode"),
            "current_mode": current.get("mode"),
            "reviewed_fingerprint": reviewed.get("fingerprint"),
            "current_fingerprint": current.get("fingerprint"),
        }
    if reviewed.get("fingerprint") != current.get("fingerprint"):
        return {
            "ok": False,
            "reason": "reviewed_diff_changed",
            "reviewed_fingerprint": reviewed.get("fingerprint"),
            "current_fingerprint": current.get("fingerprint"),
        }
    return None


def review_status(payload: dict[str, Any]) -> str:
    if normalize_findings(payload):
        return "findings"
    if payload.get("ok") is True:
        return "clean"
    if runner_status(payload) == "infra_failed":
        return "infra_failed"
    return "failed"


def runner_status(payload: dict[str, Any]) -> str:
    if payload.get("idle_timeout") or payload.get("max_timeout"):
        return "infra_failed"
    if payload.get("ok") is True:
        return "completed"
    text = transient_failure_text(payload)
    if any(word in text for word in TRANSIENT_FAILURE_WORDS):
        return "infra_failed"
    return "completed_with_findings" if normalize_findings(payload) else "failed"


def transient_failure_text(payload: dict[str, Any]) -> str:
    values = [
        payload.get("error"),
        payload.get("message"),
        payload.get("stderr_tail"),
        payload.get("stdout_tail"),
        payload.get("runner_event"),
        payload.get("event"),
    ]
    return json.dumps(values, ensure_ascii=False).lower()


def runner_event(payload: dict[str, Any], status_value: str) -> str:
    value = str(payload.get("runner_event") or payload.get("event") or "").strip().lower()
    if value in {"active", "resumed", "restarted", "infra_failed", "completed"}:
        return value
    return status_value


def review_dir(project_root: Path) -> Path:
    path = project_root / REVIEW_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def ledger_entries(project_root: Path) -> list[dict[str, Any]]:
    path = review_dir(project_root) / "review-ledger.jsonl"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def finding_review_scope(project_root: Path, finding_id: str, *, review_id: str = "") -> dict[str, Any]:
    matches = []
    for entry in ledger_entries(project_root):
        if review_id and entry.get("review_id") != review_id:
            continue
        for item in entry.get("findings") if isinstance(entry.get("findings"), list) else []:
            if isinstance(item, dict) and item.get("id") == finding_id:
                matches.append(entry)
    if not matches:
        raise ValueError(f"Review finding not found: {finding_id}")
    return matches[-1]


def finding_key(review_id: str, fingerprint: str, finding_id: str) -> str:
    return f"{review_id}\0{fingerprint}\0{finding_id}"


def resolved_finding_keys(project_root: Path) -> set[str]:
    path = review_dir(project_root) / "findings.jsonl"
    if not path.exists():
        return set()
    resolved: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == "resolve" and event.get("finding_id") and event.get("review_id"):
            resolved.add(
                finding_key(
                    str(event["review_id"]),
                    str(event.get("review_fingerprint") or ""),
                    str(event["finding_id"]),
                )
            )
    return resolved


def latest_ledger(project_root: Path) -> dict[str, Any] | None:
    entries = ledger_entries(project_root)
    return entries[-1] if entries else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sensitive_scan.sanitized_payload(payload, context="review_workflow"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sensitive_scan.sanitized_payload(payload, context="review_workflow"), ensure_ascii=False) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Codex review preflight, fingerprint, ledger, and findings.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--task-id", default="review")
    parser.add_argument("--mode", choices=sorted(REVIEW_MODES), dest="global_mode", default="uncommitted")
    sub = parser.add_subparsers(dest="command", required=True)
    add_mode_flags(sub.add_parser("status"))
    add_mode_flags(sub.add_parser("preflight"))
    add_mode_flags(sub.add_parser("plan"))
    record = sub.add_parser("record")
    add_mode_flags(record)
    record.add_argument("--result-file")
    record.add_argument("--payload-json")
    record.add_argument("--commit", default="", help="Commit SHA/ref reviewed by the result payload.")
    findings = sub.add_parser("findings")
    findings_sub = findings.add_subparsers(dest="findings_command", required=True)
    findings_sub.add_parser("list")
    resolve = findings_sub.add_parser("resolve")
    resolve.add_argument("finding_id")
    resolve.add_argument("--evidence", default="")
    resolve.add_argument("--review-id", default="")
    ledger = sub.add_parser("ledger")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_sub.add_parser("show")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    mode = selected_mode(args)
    if args.command == "status":
        result = status(root, mode=mode)
    elif args.command == "preflight":
        result = preflight(root, mode=mode, task_id=args.task_id)
    elif args.command == "plan":
        result = plan(root, mode=mode)
    elif args.command == "record":
        payload = load_payload(args.result_file, args.payload_json)
        result = record_review(root, payload, task_id=args.task_id, mode=mode, commit_ref=args.commit)
    elif args.command == "findings" and args.findings_command == "list":
        result = findings_list(root)
    elif args.command == "findings" and args.findings_command == "resolve":
        result = resolve_finding(root, args.finding_id, evidence=args.evidence, review_id=args.review_id)
    elif args.command == "ledger" and args.ledger_command == "show":
        result = ledger_show(root)
    else:
        raise ValueError("Unsupported review command.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


def add_mode_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=sorted(REVIEW_MODES), dest="command_mode")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--uncommitted", action="store_const", const="uncommitted", dest="mode_alias")
    mode_group.add_argument("--staged", action="store_const", const="staged", dest="mode_alias")
    mode_group.add_argument("--working", action="store_const", const="working", dest="mode_alias")


def selected_mode(args: argparse.Namespace) -> str:
    return str(
        getattr(args, "mode_alias", None)
        or getattr(args, "command_mode", None)
        or getattr(args, "global_mode", None)
        or "uncommitted"
    )


def load_payload(path: str | None, inline_json: str | None) -> dict[str, Any]:
    if inline_json:
        value = json.loads(inline_json)
    elif path:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("Review payload must be a JSON object.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
