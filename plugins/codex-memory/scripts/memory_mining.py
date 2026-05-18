from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import init_storage
from sensitive_scan import sanitized_payload


HISTORY_DIR = "history"
EVENTS_FILE = "events.jsonl"
CANDIDATES_FILE = "candidates.jsonl"
ACCEPTED_FILE = "accepted.jsonl"
MANUAL_REMOVAL_STATUSES = {"rejected", "deprecated"}


def append_history_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    paths = history_paths()
    event = normalize_event(event_type, payload)
    append_jsonl(paths["events"], event)
    return event


def normalize_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe = sanitized_payload(payload, context="memory_mining_event")
    task_id = str(safe.get("task_id") or safe.get("payload", {}).get("task_id") or "").strip()
    text = str(safe.get("summary") or safe.get("objective") or safe.get("tool_name") or event_type)
    command_shape = command_template(safe)
    intent = infer_intent(text, command_shape)
    return {
        "event_id": f"evt-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "event_type": event_type,
        "session_id": str(safe.get("session_id") or ""),
        "task_id": task_id,
        "project_root": str(init_storage.resolve_storage_paths().project_root or ""),
        "project_id": str(safe.get("project_id") or ""),
        "scope": str(safe.get("scope") or "project"),
        "intent": intent,
        "normalized_text": truncate(normalized_text(text), 220),
        "command_shape": command_shape,
        "outcome": outcome(safe),
        "evidence_ref": task_id or event_type,
        "created_at": utc_now(),
    }


def mine_candidates(*, recent: str = "") -> dict[str, Any]:
    paths = history_paths()
    all_events = read_jsonl(paths["events"])
    events = filter_recent_events(all_events, recent)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        key = (
            str(event.get("scope") or "project"),
            str(event.get("intent") or ""),
            str(event.get("command_shape") or event.get("normalized_text") or ""),
        )
        if key[1] or key[2]:
            groups[key].append(event)
    mined_candidates = [candidate_from_group(key, items) for key, items in groups.items() if len(items) >= 2]
    candidates = merge_mined_candidates(
        read_jsonl(paths["candidates"]),
        mined_candidates,
        preserve_unmined=bool(recent),
    )
    write_jsonl(paths["candidates"], candidates)
    accepted = [item for item in candidates if item["status"] == "accepted"]
    write_jsonl(paths["accepted"], accepted)
    return {
        "ok": True,
        "events": len(events),
        "total_events": len(all_events),
        "recent": recent,
        "candidates": len(candidates),
        "mined_candidates": len(mined_candidates),
        "accepted": len(accepted),
    }


def candidate_from_group(key: tuple[str, str, str], events: list[dict[str, Any]]) -> dict[str, Any]:
    scope, intent, command_shape = key
    support_count = len(events)
    sessions = {str(item.get("session_id") or item.get("task_id") or "") for item in events}
    success_count = sum(1 for item in events if item.get("outcome") in {"succeeded", "accepted"})
    failure_count = support_count - success_count
    risk = risk_level(intent, command_shape)
    confidence = "high" if support_count >= 3 and len(sessions) >= 2 else "medium"
    can_auto_promote = confidence == "high" and risk == "low" and success_count == support_count
    status = "accepted" if can_auto_promote else "needs_review" if risk != "low" or failure_count else "observed"
    statement = statement_for(intent, command_shape, support_count)
    return {
        "candidate_id": stable_candidate_id(scope, intent, command_shape),
        "kind": candidate_kind(intent, command_shape),
        "scope": scope,
        "intent": intent,
        "command_shape": command_shape,
        "project_root": str(events[-1].get("project_root") or ""),
        "project_id": str(events[-1].get("project_id") or ""),
        "statement": statement,
        "confidence": confidence,
        "risk": risk,
        "support_count": support_count,
        "unique_session_count": len([item for item in sessions if item]),
        "successful_outcome_count": success_count,
        "contradiction_count": failure_count,
        "last_seen_at": str(events[-1].get("created_at") or ""),
        "status": status,
        "evidence_refs": [str(item.get("event_id") or "") for item in events[-5:]],
        "auto_promoted": status == "accepted",
    }


def merge_mined_candidates(
    existing_candidates: list[dict[str, Any]],
    mined_candidates: list[dict[str, Any]],
    *,
    preserve_unmined: bool,
) -> list[dict[str, Any]]:
    existing_by_id = {str(item.get("candidate_id") or ""): dict(item) for item in existing_candidates}
    merged_by_id = dict(existing_by_id) if preserve_unmined else {}
    ordered_ids = [
        str(item.get("candidate_id") or "")
        for item in existing_candidates
        if preserve_unmined and item.get("candidate_id")
    ]

    for candidate in mined_candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            continue
        existing = existing_by_id.get(candidate_id)
        next_candidate = dict(candidate)
        if existing and existing.get("status") in MANUAL_REMOVAL_STATUSES:
            next_candidate["status"] = existing["status"]
            next_candidate["auto_promoted"] = False
        elif (
            existing
            and existing.get("status") == "accepted"
            and int(next_candidate.get("contradiction_count") or 0) == 0
        ):
            next_candidate["status"] = "accepted"
            next_candidate["auto_promoted"] = bool(existing.get("auto_promoted"))
        merged_by_id[candidate_id] = next_candidate
        if candidate_id not in ordered_ids:
            ordered_ids.append(candidate_id)

    return [merged_by_id[candidate_id] for candidate_id in ordered_ids if candidate_id in merged_by_id]


def list_candidates(status: str = "") -> dict[str, Any]:
    items = read_jsonl(history_paths()["candidates"])
    if status:
        items = [item for item in items if item.get("status") == status]
    return {"ok": True, "candidates": items}


def show_candidate(candidate_id: str) -> dict[str, Any]:
    for item in read_jsonl(history_paths()["candidates"]):
        if item.get("candidate_id") == candidate_id:
            return {"ok": True, "candidate": item}
    return {"ok": False, "candidate_id": candidate_id, "error": "candidate not found"}


def update_candidate(candidate_id: str, status: str) -> dict[str, Any]:
    paths = history_paths()
    items = read_jsonl(paths["candidates"])
    changed = False
    for item in items:
        if item.get("candidate_id") == candidate_id:
            item["status"] = status
            item["auto_promoted"] = status == "accepted"
            changed = True
    write_jsonl(paths["candidates"], items)
    write_jsonl(paths["accepted"], [item for item in items if item.get("status") == "accepted"])
    return {"ok": changed, "candidate_id": candidate_id, "status": status}


def accepted_context(
    limit: int = 5,
    *,
    project_id: str = "",
    scope: str = "",
    intent: str = "",
    working_set: list[str] | None = None,
) -> list[dict[str, Any]]:
    items = read_jsonl(history_paths()["accepted"])
    filtered = [
        item
        for item in items
        if candidate_matches(
            item,
            project_id=project_id,
            scope=scope,
            intent=intent,
            working_set=working_set or [],
        )
    ]
    return sorted(filtered, key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)[
        : max(1, limit)
    ]


def candidate_matches(
    item: dict[str, Any],
    *,
    project_id: str = "",
    scope: str = "",
    intent: str = "",
    working_set: list[str] | None = None,
) -> bool:
    if project_id and item.get("project_id") and item.get("project_id") != project_id:
        return False
    if scope and item.get("scope") and item.get("scope") != scope:
        return False
    if intent and item.get("intent") and item.get("intent") != intent:
        return False

    terms = [Path(str(value)).name.lower() for value in (working_set or []) if str(value).strip()]
    if not terms:
        return True
    searchable = " ".join(
        str(item.get(key) or "").lower()
        for key in ("statement", "command_shape", "kind", "intent", "project_id", "scope")
    )
    return any(term and term in searchable for term in terms)


def status() -> dict[str, Any]:
    paths = history_paths()
    candidates = read_jsonl(paths["candidates"])
    return {
        "ok": True,
        "history_dir": str(paths["dir"]),
        "event_count": len(read_jsonl(paths["events"])),
        "candidate_count": len(candidates),
        "accepted_count": sum(1 for item in candidates if item.get("status") == "accepted"),
        "needs_review_count": sum(1 for item in candidates if item.get("status") == "needs_review"),
        "observed_count": sum(1 for item in candidates if item.get("status") == "observed"),
    }


def history_paths() -> dict[str, Path]:
    init_storage.ensure_storage_layout()
    root = init_storage.resolve_storage_paths().storage_dir / HISTORY_DIR
    root.mkdir(parents=True, exist_ok=True)
    return {
        "dir": root,
        "events": root / EVENTS_FILE,
        "candidates": root / CANDIDATES_FILE,
        "accepted": root / ACCEPTED_FILE,
    }


def command_template(payload: dict[str, Any]) -> str:
    command = payload.get("command") or payload.get("tool_name") or ""
    if isinstance(command, list):
        command = " ".join(str(item) for item in command[:4])
    text = str(command).strip()
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key)=\S+", r"\1=<redacted>", text)
    return truncate(text, 160)


def infer_intent(text: str, command_shape: str) -> str:
    lowered = f"{text} {command_shape}".lower()
    if any(word in lowered for word in ("review", "xhigh")):
        return "review_gate"
    if any(word in lowered for word in ("verify", "test", "验证", "测试")):
        return "verification_workflow"
    if any(word in lowered for word in ("commit", "push", "提交")):
        return "git_workflow"
    if any(word in lowered for word in ("error", "failed", "纠正", "修正")):
        return "correction_pattern"
    return "workflow_preference"


def candidate_kind(intent: str, command_shape: str) -> str:
    if command_shape:
        return "command_preference"
    if intent == "correction_pattern":
        return "correction_pattern"
    if intent == "verification_workflow":
        return "verification_workflow"
    return "workflow_preference"


def risk_level(intent: str, command_shape: str) -> str:
    text = f"{intent} {command_shape}".lower()
    if any(word in text for word in ("delete", "remove", "push", "release", "force", "清理", "发布")):
        return "high"
    if any(word in text for word in ("commit", "merge", "review")):
        return "medium"
    return "low"


def statement_for(intent: str, command_shape: str, support_count: int) -> str:
    if command_shape:
        return f"历史上 `{command_shape}` 已作为 `{intent}` 的常用命令形态出现 {support_count} 次；后续同类任务优先参考该形态。"
    return f"历史上 `{intent}` 工作流重复出现 {support_count} 次；后续同类任务优先参考该偏好。"


def stable_candidate_id(scope: str, intent: str, command_shape: str) -> str:
    seed = re.sub(r"[^a-zA-Z0-9]+", "-", f"{scope}-{intent}-{command_shape.lower()}").strip("-")
    return (seed[:96] or "candidate").lower()


def outcome(payload: dict[str, Any]) -> str:
    if payload.get("exit_code") not in (None, 0):
        return "failed"
    if payload.get("ok") is False:
        return "failed"
    return "succeeded"


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def filter_recent_events(events: list[dict[str, Any]], recent: str = "") -> list[dict[str, Any]]:
    cutoff = recent_cutoff(recent)
    if cutoff is None:
        return events
    return [event for event in events if event_datetime(event) >= cutoff]


def recent_cutoff(value: str) -> datetime | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)([dh])", text)
    if not match:
        raise ValueError("recent must use '<number>d' or '<number>h', for example '90d'")
    amount = int(match.group(1))
    delta = timedelta(days=amount) if match.group(2) == "d" else timedelta(hours=amount)
    return datetime.now(timezone.utc) - delta


def event_datetime(event: dict[str, Any]) -> datetime:
    raw = str(event.get("created_at") or "")
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine sanitized memory events into reusable private memory candidates.")
    sub = parser.add_subparsers(dest="command", required=True)
    mine = sub.add_parser("mine")
    mine_sub = mine.add_subparsers(dest="mine_command", required=True)
    mine_sub.add_parser("status")
    mine_run = mine_sub.add_parser("run")
    mine_run.add_argument("--recent", default="")
    candidates = sub.add_parser("candidates")
    candidates_sub = candidates.add_subparsers(dest="candidates_command", required=True)
    list_cmd = candidates_sub.add_parser("list")
    list_cmd.add_argument("--status", default="")
    show = candidates_sub.add_parser("show")
    show.add_argument("candidate_id")
    for name in ("accept", "reject", "deprecate"):
        cmd = candidates_sub.add_parser(name)
        cmd.add_argument("candidate_id")
    args = parser.parse_args()
    if args.command == "mine" and args.mine_command == "status":
        result = status()
    elif args.command == "mine" and args.mine_command == "run":
        result = mine_candidates(recent=args.recent)
    elif args.command == "candidates" and args.candidates_command == "list":
        result = list_candidates(status=args.status)
    elif args.command == "candidates" and args.candidates_command == "show":
        result = show_candidate(args.candidate_id)
    else:
        status_map = {"accept": "accepted", "reject": "rejected", "deprecate": "deprecated"}
        result = update_candidate(args.candidate_id, status_map[args.candidates_command])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
