from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import skill_bundle


MAX_EVENTS = 20
MAX_REASON_CHARS = 96
DECISION_RANK = {"matched": 1, "skipped": 2, "used": 3}

DEFAULT_TRIGGERS = {
    "grill-me": ("requirement", "需求", "策划", "clarify", "澄清", "逻辑", "question"),
    "design-an-interface": ("interface", "api", "schema", "contract", "接口", "协议", "契约"),
    "tdd": ("tdd", "test", "tests", "测试", "bug", "fix", "修复"),
    "git-safe-commit": ("commit", "提交", "stage", "staging"),
    "review-fix-merge-branch": ("review", "merge", "分支", "合并"),
    "harness-release-gate": ("release", "gate", "verify", "发布", "验证", "review"),
    "skill-installer": ("skill", "skills", "技能", "install", "安装"),
    "openai-docs": ("openai", "chatgpt", "responses api", "codex api"),
    "security-best-practices": ("security", "secure", "安全", "漏洞"),
    "security-threat-model": ("threat", "abuse", "威胁", "建模"),
    "cli-creator": ("cli", "command", "命令行", "wrapper"),
    "migrate-to-codex": ("migrate", "codex", "迁移"),
    "triage-issue": ("bug", "issue", "triage", "异常", "根因"),
    "write-a-prd": ("prd", "产品需求", "需求文档"),
    "prd-to-plan": ("prd", "plan", "计划", "阶段"),
    "prd-to-issues": ("prd", "issue", "任务", "工单"),
    "request-refactor-plan": ("refactor", "重构", "改造"),
    "improve-codebase-architecture": ("architecture", "架构", "模块", "可测试"),
}


def match_task_skills(
    *,
    task_id: str,
    task: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    loaded_manifest = manifest or _load_manifest()
    audit = _base_audit(task_id, loaded_manifest, previous)
    text = _task_text(task)
    matched_names = set(_explicit_skill_names(task))

    for item in loaded_manifest.get("skills", []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"]
        reasons = _match_reasons(name, item, text)
        if name in matched_names:
            reasons.append("explicit_skill_request")
        if not reasons:
            continue
        _upsert_skill(audit, name, "matched", reasons, _source_group(item), available=_source_available(item))
        for reason in reasons:
            _append_event(audit, "before_task", name, "matched", reason)

    _apply_payload_decisions(audit, task, event="before_task")
    return _finalize(audit)


def record_skill_decision(
    *,
    audit: dict[str, Any],
    skill_name: str,
    decision: str,
    reason: str = "",
    source: str = "agent",
    event: str = "after_tool",
) -> dict[str, Any]:
    result = _copy_audit(audit)
    normalized = decision if decision in DECISION_RANK else "matched"
    name = _safe_text(skill_name, 64)
    reason_code = _reason_code(reason or normalized)
    _upsert_skill(result, name, normalized, [reason_code], source, available=True)
    if normalized == "skipped":
        _set_skip_reason(result, name, reason_code)
    _append_event(result, event, name, normalized, reason_code)
    return _finalize(result)


def merge_payload_decisions(audit: dict[str, Any], payload: dict[str, Any], *, event: str) -> dict[str, Any]:
    result = _copy_audit(audit)
    result.setdefault("version", 1)
    if payload.get("task_id"):
        result.setdefault("task_id", _safe_text(str(payload.get("task_id")), 96))
    result.setdefault("skills", [])
    result.setdefault("events", [])
    _apply_payload_decisions(result, payload, event=event)
    signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
    incoming = signals.get("skill_routing_audit")
    if isinstance(incoming, dict):
        for skill in incoming.get("skills") if isinstance(incoming.get("skills"), list) else []:
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("name") or "").strip()
            status = str(skill.get("status") or "matched").strip()
            reason = str(skill.get("skip_reason") or ",".join(_string_list(skill.get("match_reasons"))) or status)
            if name:
                result = record_skill_decision(
                    audit=result,
                    skill_name=name,
                    decision=status,
                    reason=reason,
                    source=str(skill.get("source") or "payload"),
                    event=event,
                )
    return _finalize(result)


def render_skill_audit(*, audit: dict[str, Any], target: str = "all") -> dict[str, Any]:
    normalized = _copy_audit(audit)
    if target in {"checkpoint", "brief", "all"}:
        normalized["finalize_unrecorded_as_skipped"] = True
    normalized = _finalize(normalized)
    normalized.pop("finalize_unrecorded_as_skipped", None)
    brief = _brief_lines(normalized)
    checkpoint = {
        "summary": brief[0] if brief else "技能路由：未记录。",
        "signals": {"skill_routing_audit": normalized},
    }
    result = {
        "metadata": {"skill_routing_audit": normalized},
        "checkpoint": checkpoint,
        "brief": brief,
    }
    if target in {"metadata", "checkpoint", "brief"}:
        return {target: result[target]}
    return result


def _load_manifest() -> dict[str, Any]:
    try:
        return skill_bundle.load_manifest(Path(__file__).resolve().parents[1])
    except Exception as exc:
        return {
            "version": 1,
            "skills": [],
            "missing_manifest": True,
            "degraded_reason": f"{type(exc).__name__}: {exc}",
        }


def _base_audit(task_id: str, manifest: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    audit = _copy_audit(previous or {})
    audit["version"] = 1
    audit["task_id"] = _safe_text(task_id, 96)
    audit["manifest"] = {
        "source": "plugins/codex-memory/skills/bundled-skills.json",
        "version": manifest.get("version", 1),
        "digest": _manifest_digest(manifest),
    }
    audit.setdefault("skills", [])
    audit.setdefault("events", [])
    if manifest.get("missing_manifest"):
        audit["degraded_reason"] = str(manifest.get("degraded_reason") or "manifest_unavailable")
    return audit


def _copy_audit(audit: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(audit, ensure_ascii=False))
    except (TypeError, ValueError):
        return {}


def _manifest_digest(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _task_text(task: dict[str, Any]) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    parts = [
        task.get("objective"),
        task.get("user_request"),
        task.get("summary"),
        task.get("task_intent"),
        task.get("task_type"),
        task.get("risk_level"),
        metadata.get("task_intent"),
        metadata.get("task_type"),
        metadata.get("risk_level"),
    ]
    parts.extend(_string_list(task.get("working_set")))
    return " ".join(str(part) for part in parts if part).lower()


def _explicit_skill_names(task: dict[str, Any]) -> list[str]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    values = []
    for source in (task, metadata):
        values.extend(_string_list(source.get("skills")))
        values.extend(_string_list(source.get("used_skills")))
        values.extend(_string_list(source.get("matched_skills")))
    return values


def _match_reasons(name: str, item: dict[str, Any], text: str) -> list[str]:
    triggers = _string_list(item.get("trigger_keywords")) or list(DEFAULT_TRIGGERS.get(name, ()))
    reasons = []
    for trigger in triggers:
        token = trigger.lower().strip()
        if token and token in text:
            reasons.append(_reason_code(token))
    return _unique(reasons)


def _apply_payload_decisions(audit: dict[str, Any], payload: dict[str, Any], *, event: str) -> None:
    for name in _string_list(payload.get("used_skills")):
        updated = record_skill_decision(audit=audit, skill_name=name, decision="used", reason="payload_used", event=event)
        audit.clear()
        audit.update(updated)
    for name in _string_list(payload.get("skipped_skills")):
        updated = record_skill_decision(audit=audit, skill_name=name, decision="skipped", reason="payload_skipped", event=event)
        audit.clear()
        audit.update(updated)
    for item in payload.get("skill_decisions") if isinstance(payload.get("skill_decisions"), list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        updated = record_skill_decision(
            audit=audit,
            skill_name=name,
            decision=str(item.get("decision") or "matched"),
            reason=str(item.get("reason") or ""),
            source=str(item.get("source") or "payload"),
            event=event,
        )
        audit.clear()
        audit.update(updated)


def _upsert_skill(
    audit: dict[str, Any],
    name: str,
    status: str,
    reasons: list[str],
    source: str,
    *,
    available: bool,
) -> None:
    skills = audit.setdefault("skills", [])
    existing = next((item for item in skills if isinstance(item, dict) and item.get("name") == name), None)
    if existing is None:
        existing = {
            "name": name,
            "status": status,
            "match_reasons": [],
            "skip_reason": "",
            "source": source,
            "available": available,
        }
        skills.append(existing)
    if DECISION_RANK.get(status, 0) >= DECISION_RANK.get(str(existing.get("status") or "matched"), 0):
        existing["status"] = status
    existing["source"] = source or existing.get("source") or "manifest"
    existing["available"] = bool(available)
    existing["match_reasons"] = _unique(_string_list(existing.get("match_reasons")) + [_reason_code(item) for item in reasons])


def _set_skip_reason(audit: dict[str, Any], name: str, reason: str) -> None:
    for item in audit.get("skills") if isinstance(audit.get("skills"), list) else []:
        if isinstance(item, dict) and item.get("name") == name:
            item["skip_reason"] = _reason_code(reason)


def _append_event(audit: dict[str, Any], event: str, skill: str, decision: str, reason: str) -> None:
    events = audit.setdefault("events", [])
    entry = {
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "event": _safe_text(event, 32),
        "skill": _safe_text(skill, 64),
        "decision": decision if decision in DECISION_RANK else "matched",
        "reason_code": _reason_code(reason),
    }
    if entry not in events:
        events.append(entry)
    del events[:-MAX_EVENTS]


def _finalize(audit: dict[str, Any]) -> dict[str, Any]:
    skills = [item for item in audit.get("skills", []) if isinstance(item, dict)]
    for item in skills:
        if item.get("status") == "matched" and target_skipped(audit):
            item["status"] = "skipped"
            item["skip_reason"] = item.get("skip_reason") or "not_recorded_as_used"
    audit["skills"] = sorted(skills, key=lambda item: str(item.get("name") or ""))
    audit["summary"] = {
        "matched_count": len(skills),
        "used_count": sum(1 for item in skills if item.get("status") == "used"),
        "skipped_count": sum(1 for item in skills if item.get("status") == "skipped"),
        "degraded": bool(audit.get("degraded_reason")),
    }
    return audit


def target_skipped(audit: dict[str, Any]) -> bool:
    return bool(audit.get("finalize_unrecorded_as_skipped"))


def _brief_lines(audit: dict[str, Any]) -> list[str]:
    skills = audit.get("skills") if isinstance(audit.get("skills"), list) else []
    matched = [str(item.get("name")) for item in skills if isinstance(item, dict)]
    used = [str(item.get("name")) for item in skills if isinstance(item, dict) and item.get("status") == "used"]
    skipped = [
        f"{item.get('name')}({item.get('skip_reason') or 'not_used'})"
        for item in skills
        if isinstance(item, dict) and item.get("status") == "skipped"
    ]
    lines = [
        "技能路由："
        f"matched={len(matched)}, used={len(used)}, skipped={len(skipped)}, "
        f"degraded={bool(audit.get('degraded_reason'))}."
    ]
    if matched:
        lines.append("- matched: " + ", ".join(matched))
    if used:
        lines.append("- used: " + ", ".join(used))
    if skipped:
        lines.append("- skipped: " + ", ".join(skipped))
    if audit.get("degraded_reason"):
        lines.append("- degraded_reason: " + _safe_text(str(audit["degraded_reason"]), MAX_REASON_CHARS))
    return lines


def _source_group(item: dict[str, Any]) -> str:
    return str(item.get("source_group") or "openai-curated")


def _source_available(item: dict[str, Any]) -> bool:
    return not bool(item.get("source_missing"))


def _reason_code(value: str) -> str:
    text = _safe_text(value, MAX_REASON_CHARS).lower()
    text = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "_", text).strip("_-")
    return text or "unspecified"


def _safe_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key)=\S+", r"\1=<redacted>", text)
    return text[:limit]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
