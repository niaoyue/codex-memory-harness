from __future__ import annotations

import re
from typing import Any


BUGFIX_WORDS = (
    "bug",
    "fix",
    "crash",
    "error",
    "exception",
    "regression",
    "修复",
    "报错",
    "崩溃",
    "异常",
    "回归",
)
SMALL_CHANGE_WORDS = ("文案", "小改", "小优化", "配置修正", "微调", "typo", "copy", "minor")
FEATURE_WORDS = (
    "feature",
    "story",
    "add",
    "new",
    "implement",
    "新增",
    "增加",
    "实现",
    "玩法",
    "活动",
    "系统入口",
)
SYSTEM_WORDS = (
    "framework",
    "architecture",
    "refactor",
    "rewrite",
    "sdk",
    "hot update",
    "resource loading",
    "资源系统",
    "热更新",
    "协议",
    "框架",
    "架构",
    "重构",
    "接入",
)
TECH_WORDS = ("tech debt", "cleanup", "lint", "test", "tests", "testing", "ci", "工具", "技术债", "治理", "测试")
DOC_WORDS = ("doc", "docs", "gdd", "文档", "策划", "说明")
DESIGN_SOURCE_WORDS = ("gdd", "design doc", "requirements", "策划", "需求文档", "设计文档")
VALID_INTENTS = {
    "bugfix",
    "small_change",
    "feature_story",
    "system_change",
    "release_gate",
    "docs_only",
    "tech_task",
}


def evaluate(
    task: dict[str, Any],
    signals: dict[str, Any],
    *,
    mode: str,
    task_type: str,
    risk_level: str,
    domains: list[str] | None = None,
) -> dict[str, Any]:
    intent = task_intent(task, signals, mode=mode, task_type=task_type, risk_level=risk_level, domains=domains)
    sources = requirement_sources(task, signals)
    acceptance = task_field_list(task, "acceptance") or task_field_list(task, "acceptance_criteria")
    architecture = task_field_list(task, "architecture") or task_field_list(task, "architecture_notes")
    rollback = task_field_list(task, "rollback_plan") or task_field_list(task, "rollback")
    missing = missing_requirements(
        intent,
        sources=sources,
        acceptance=acceptance,
        architecture=architecture,
        rollback=rollback,
    )
    questions = open_questions(intent, missing)
    blocking = bool(missing) and intent in {"feature_story", "system_change", "release_gate"}
    status = "needs_clarification" if blocking else ("warning" if missing else "passed")
    return {
        "version": 1,
        "task_intent": intent,
        "status": status,
        "blocking": blocking,
        "requirement_sources": sources,
        "missing": missing,
        "open_questions": questions,
        "assumptions_policy": (
            "Do not infer missing product or design behavior. Ask for clarification before implementation."
        ),
        "technical_decision_policy": (
            "Follow existing project conventions first. If none exist, choose a production-grade modular "
            "and interface-driven design, then record the decision."
        ),
    }


def task_intent(
    task: dict[str, Any],
    signals: dict[str, Any],
    *,
    mode: str,
    task_type: str,
    risk_level: str,
    domains: list[str] | None = None,
) -> str:
    explicit = first_task_value(task, "task_intent", "intent").strip().lower()
    if explicit:
        return normalize_intent(explicit)
    text = str(signals.get("text") or "").lower()
    domain_set = set(domains or [])
    if docs_only_scope(domain_set, task_type):
        return "docs_only"
    if risk_level == "release_blocking" or task_type == "release":
        return "release_gate"
    if mode == "cross_project_contract" or task_type == "contract":
        return "system_change"
    if has_keyword(text, BUGFIX_WORDS):
        return "bugfix"
    if has_keyword(text, SMALL_CHANGE_WORDS):
        return "small_change"
    if has_keyword(text, TECH_WORDS):
        return "tech_task"
    if has_keyword(text, SYSTEM_WORDS):
        return "system_change"
    if has_keyword(text, FEATURE_WORDS):
        return "feature_story"
    return "tech_task" if domain_set and "workspace_meta" in domain_set else "small_change"


def normalize_intent(value: str) -> str:
    aliases = {
        "feature": "feature_story",
        "story": "feature_story",
        "system": "system_change",
        "release": "release_gate",
        "docs": "docs_only",
        "documentation": "docs_only",
        "bug": "bugfix",
        "fix": "bugfix",
        "quick_fix": "bugfix",
        "small": "small_change",
        "optimization": "small_change",
        "tech": "tech_task",
    }
    normalized = value.replace("-", "_").replace(" ", "_")
    intent = aliases.get(normalized, normalized)
    return intent if intent in VALID_INTENTS else "tech_task"


def requirement_sources(task: dict[str, Any], signals: dict[str, Any]) -> list[str]:
    sources = task_field_list(task, "requirement_sources")
    sources.extend(task_field_list(task, "design_docs"))
    sources.extend(task_field_list(task, "source_docs"))
    sources.extend(path_sources(signals))
    task_text = " ".join(task_field_list(task, "objective") + task_field_list(task, "user_request"))
    if sufficiently_detailed_text(task_text):
        sources.append("user_request")
    if task_field_list(task, "requirements"):
        sources.append("task_requirements")
    return unique(sources)


def docs_only_scope(domain_set: set[str], task_type: str) -> bool:
    non_docs_domains = {domain for domain in domain_set if domain and domain != "design_docs"}
    if not non_docs_domains and domain_set:
        return True
    return not domain_set and task_type == "docs"


def first_task_value(task: dict[str, Any], *keys: str) -> str:
    for key in keys:
        values = task_field_list(task, key)
        if values:
            return values[0]
    return ""


def task_field_list(task: dict[str, Any], key: str) -> list[str]:
    values = string_list(task.get(key))
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    values.extend(string_list(metadata.get(key)))
    return unique(values)


def path_sources(signals: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for path in string_list(signals.get("paths")):
        lowered = path.lower()
        if any(token in lowered for token in ("docs/", "design/", "gdd/", "策划/")):
            result.append(path)
    text = str(signals.get("text") or "")
    if has_keyword(text, DESIGN_SOURCE_WORDS):
        result.append("referenced_design_doc")
    return result


def missing_requirements(
    intent: str,
    *,
    sources: list[str],
    acceptance: list[str],
    architecture: list[str],
    rollback: list[str],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if intent in {"feature_story", "system_change", "release_gate"} and not sources:
        missing.append({"field": "requirement_sources", "reason": "缺少可追溯的需求或策划来源"})
    if intent in {"feature_story", "system_change"} and not acceptance:
        missing.append({"field": "acceptance_criteria", "reason": "缺少可验证的验收条件"})
    if intent == "system_change" and not architecture:
        missing.append({"field": "architecture", "reason": "系统级改动缺少架构边界、接口或迁移说明"})
    if intent == "release_gate" and not rollback:
        missing.append({"field": "rollback_plan", "reason": "发布或热更任务缺少回滚说明"})
    return missing


def open_questions(intent: str, missing: list[dict[str, str]]) -> list[str]:
    questions: list[str] = []
    fields = {item.get("field") for item in missing}
    if "requirement_sources" in fields:
        questions.append("本任务的需求来源是什么？请提供策划文档、issue/story 或本轮明确需求说明。")
    if "acceptance_criteria" in fields:
        questions.append("本任务完成后按哪些验收条件判断通过？")
    if "architecture" in fields:
        questions.append("系统级改动的模块边界、接口契约和迁移方式是什么？")
    if "rollback_plan" in fields:
        questions.append("发布、热更或渠道包失败时的回滚方式是什么？")
    if not questions and intent in {"feature_story", "system_change", "release_gate"}:
        questions.append("是否还有未写明但会影响实现的玩法、资源、平台或发布约束？")
    return questions


def sufficiently_detailed_text(value: str) -> bool:
    text = value.strip()
    if len(text) >= 48:
        return True
    english_condition = r"\b(?:when|if|after|before)\b"
    chinese_condition = r"(?:当|如果|点击|进入|完成|失败)"
    return bool(re.search(f"{english_condition}|{chinese_condition}", text, re.IGNORECASE))


def has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", lowered) if token}
    for keyword in keywords:
        normalized = keyword.lower()
        if re.search(r"[^a-z0-9]", normalized):
            if normalized in lowered:
                return True
        elif normalized in tokens:
            return True
    return False


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
