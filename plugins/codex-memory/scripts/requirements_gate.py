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
TECH_WORDS = (
    "tech debt",
    "cleanup",
    "lint",
    "test",
    "tests",
    "testing",
    "ci",
    "技术债",
    "测试",
)
CONTEXTUAL_TECH_WORDS = (
    "adapter",
    "adapters",
    "tooling",
    "governance",
    "runtime",
    "upstream",
    "工具",
    "治理",
    "适配",
    "复用",
    "上游",
)
NON_IMPLEMENTATION_CONTEXT_WORDS = (
    "doc",
    "docs",
    "documentation",
    "spec",
    "specs",
    "proposal",
    "design",
    "decision",
    "planning",
    "research",
    "audit",
    "verify",
    "check",
    "boundary",
    "license",
    "telemetry",
    "文档",
    "规划",
    "设计",
    "决策",
    "调研",
    "核对",
    "边界",
    "不实现",
    "不复制",
)
DOC_TARGET_PHRASES = (
    "governance docs",
    "decision docs",
    "task-list",
    "task list",
    "docs for",
    "documentation for",
    "治理文档",
    "决策文档",
    "说明文档",
)
DESIGN_SOURCE_PHRASES = (
    "according to design doc",
    "from design doc",
    "per design doc",
    "based on design doc",
    "using design doc",
    "with design doc",
    "according to proposal",
    "from proposal",
    "per proposal",
    "based on proposal",
    "using proposal",
    "with proposal",
    "根据设计文档",
    "按设计文档",
    "基于设计文档",
)
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
    if docs_only_scope(domain_set, task_type) and not implementation_task_context(text, "docs"):
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
    if contextual_tech_task(text, domain_set, task_type):
        return "tech_task"
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


def contextual_tech_task(text: str, domain_set: set[str], task_type: str) -> bool:
    if not has_keyword(text, CONTEXTUAL_TECH_WORDS):
        return False
    if implementation_task_context(text, task_type):
        return False
    if docs_only_scope(domain_set, task_type):
        return True
    if task_type in {"docs", "documentation", "research", "planning", "audit"}:
        return True
    return has_keyword(text, NON_IMPLEMENTATION_CONTEXT_WORDS)


def implementation_task_context(text: str, task_type: str) -> bool:
    candidate_text = without_negated_implementation_targets(text)
    lowered = candidate_text.lower()
    doc_target = documentation_target_context(candidate_text)
    if task_type in {"implementation", "feature", "feature_story", "system", "system_change"}:
        return not doc_target
    if has_keyword(candidate_text, ("implement",)):
        return not doc_target
    if has_keyword(candidate_text, ("add", "new", "新增", "增加")) and has_keyword(candidate_text, CONTEXTUAL_TECH_WORDS):
        return not doc_target
    return "实现" in lowered and not doc_target


def without_negated_implementation_targets(text: str) -> str:
    text = re.sub(
        r"\b(?:do\s+not|don['’]?t|not)\s+implement\b(?:(?!\b(?:but|and)\b|[;,.，。]).)*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"(?:不|不要|别|无需|不用|不需要)实现(?:(?!但|而|并\s*实现|且\s*实现|然后\s*实现|[;,.，。]).)*", " ", text)


def documentation_target_context(text: str) -> bool:
    lowered = text.lower()
    if mixed_implementation_doc_target_context(text):
        return False
    if re.search(r"\b(?:adapter|runtime|tooling|governance|upstream)(?:[- ]+(?:adapter|runtime|tooling|governance|upstream))*[- ]+(?:doc|docs|documentation|readme|guide)[- ]+(?:parser|adapter|adapters|runtime|generator|loader|validator|gate|router)\b", lowered):
        return False
    if doc_reference_context(text):
        return False
    if explicit_contextual_doc_target(text):
        return True
    if any(phrase in lowered for phrase in DOC_TARGET_PHRASES):
        return True
    if any(phrase in lowered for phrase in DESIGN_SOURCE_PHRASES):
        return False
    design_source_context = has_keyword(text, DESIGN_SOURCE_WORDS) and has_keyword(text, CONTEXTUAL_TECH_WORDS)
    if design_source_context and has_keyword(text, ("implement", "实现")):
        return False
    if spec_document_target_context(text):
        return True
    return standalone_doc_artifact_target_context(text)


def spec_document_target_context(text: str) -> bool:
    lowered = text.lower()
    if not re.search(r"\bspecs?\b", lowered):
        return False
    if re.search(r"\bspecs?\s+(?:parser|adapter|runtime|loader|validator|gate|router)\b", lowered):
        return False
    return bool(
        re.search(r"\b(?:change[- ]+)?governance[- ]+specs?\b", lowered)
        or re.search(r"\bopenspec[- ]+specs?\b", lowered)
        or re.search(r"\b(?:spec[- ]+delta|delta[- ]+spec)\b", lowered)
        or re.search(r"治理\s*spec", text)
    )


def standalone_doc_artifact_target_context(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(?:doc|docs|documentation|gdd)\s+(?:parser|adapter|runtime|generator|loader|validator|gate|router)\b", lowered):
        return False
    english_doc_action = re.search(
        r"\b(?:add|update|write|create|revise|edit)\b.*\b(?:doc|docs|documentation|gdd|proposal|decision|task[- ]list|readme|guide|runbook|handbook|release notes)\b",
        lowered,
    )
    chinese_doc_action = re.search(r"(?:新增|增加|更新|编写|完善|修订|整理).*(?:文档|策划|说明|提案|决策|任务清单)", text)
    return bool(english_doc_action or chinese_doc_action)


def doc_reference_context(text: str) -> bool:
    lowered = text.lower()
    english_ref = re.search(
        r"\b(?:according to|from|per|based on|using|with)\s+(?:the\s+)?(?:docs?|documentation|readme|guide|runbook|handbook|gdd|proposal|decision|(?:change[- ]+)?governance docs|task[- ]list)\b",
        lowered,
    )
    chinese_ref = re.search(r"(?:根据|按|基于|参考|使用).{0,16}(?:文档|说明|提案|决策|任务清单|readme|guide|runbook)", text, re.IGNORECASE)
    match = english_ref or chinese_ref
    if not match:
        return False
    prefix = text[: match.start()]
    lowered_prefix = prefix.lower()
    if explicit_contextual_doc_target(prefix) or any(phrase in lowered_prefix for phrase in DOC_TARGET_PHRASES):
        return False
    return not standalone_doc_artifact_target_context(prefix)


def mixed_implementation_doc_target_context(text: str) -> bool:
    candidate_text = without_negated_implementation_targets(text)
    if not has_keyword(candidate_text, ("implement", "实现")):
        return False
    if not has_keyword(candidate_text, CONTEXTUAL_TECH_WORDS):
        return False
    lowered = candidate_text.lower()
    english_contexts = "adapter|runtime|tooling|governance|upstream"
    english_docs = "doc|docs|documentation|readme|guide|runbook|handbook|release notes|spec|specs"
    if re.search(
        rf"\bimplement\b(?:(?!\b(?:and|plus|then)\b|[;,.]).)*(?:{english_contexts})\b"
        rf"(?:(?!\b(?:and|plus|then)\b|[;,.]).)*(?:\b(?:and|plus|then)\b|[;,.]).*\b(?:{english_docs})\b",
        lowered,
    ):
        return True
    if re.search(
        r"实现(?:(?!并|且|然后|[;,.，。]).)*(?:adapter|runtime|工具|治理|适配|复用|上游)"
        r"(?:并|且|然后|[;,.，。]).*(?:文档|说明)",
        candidate_text,
    ):
        return True
    if re.search(r"\bimplement\s+(?:doc|docs|documentation|readme|guide|runbook|handbook|release notes)\b", lowered):
        return False
    return False


def explicit_contextual_doc_target(text: str) -> bool:
    lowered = text.lower()
    english_contexts = "adapter|runtime|tooling|governance|upstream"
    english_docs = "doc|docs|documentation|readme|guide"
    if re.search(rf"\b(?:{english_contexts})(?:[- ]+(?:{english_contexts}))*[- ]+(?:{english_docs})\b", lowered):
        return True
    return bool(re.search(r"(?:runtime|adapter|工具|治理|适配|复用|上游)\s*(?:文档|说明)", text))


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
