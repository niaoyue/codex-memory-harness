from __future__ import annotations

import re
from typing import Any

import openspec_task_signals


ACTION_WORDS = (
    "build",
    "create",
    "develop",
    "generate",
    "implement",
    "scaffold",
    "simulate",
    "clone",
    "redesign",
    "from scratch",
    "生成",
    "创建",
    "开发",
    "实现",
    "搭建",
    "模拟",
    "复刻",
    "仿",
)
APP_WORDS = (
    "app",
    "application",
    "website",
    "web app",
    "dashboard",
    "frontend",
    "backend",
    "full-stack",
    "fullstack",
    "portal",
    "应用",
    "网站",
    "前端",
    "后端",
    "全栈",
    "管理后台",
    "小程序",
    "词典",
    "字典",
    "单词",
    "背词",
)
COMPLEX_WORDS = (
    "end-to-end",
    "multi-page",
    "workflow",
    "architecture",
    "refactor",
    "rewrite",
    "migration",
    "完整",
    "端到端",
    "多页面",
    "工作流",
    "架构",
    "重构",
    "迁移",
    "大型",
    "复杂",
    "批量",
)
COMPLEX_INTENTS = {"system_change", "release_gate"}
REQUIRED_EXECUTION_MODELS = {"host_subagent_required"}
DISABLE_PHRASES = (
    "不要用 subagent",
    "不用 subagent",
    "不要派发子代理",
    "不用子代理",
    "do not use subagent",
    "without subagent",
    "main agent only",
)
REQUEST_PHRASES = (
    "subagent",
    "sub-agent",
    "sub agent",
    "delegate",
    "delegation",
    "parallel agent",
    "分角色",
    "并行代理",
    "子代理",
    "多代理",
)
REVIEW_GATE_PHRASES = (
    "codex xhigh review",
    "xhigh review",
    "review gate",
    "codex review",
    "代码审核",
    "最终审核",
    "reivew",
)
OPENSPEC_METADATA_KEYS = (
    "openspec_change_id",
    "openspec_change",
    "openspec_capability",
    "openspec_dispatch_required",
)
OPENSPEC_EXECUTION_WORDS = (
    *ACTION_WORDS,
    "update",
    "modify",
    "edit",
    "change",
    "apply",
    "archive",
    "execute",
    "run",
    "complete",
    "fix",
    "align",
    "更新",
    "修改",
    "编辑",
    "变更",
    "应用",
    "归档",
    "执行",
    "完成",
    "修复",
    "对齐",
    "落地",
)


def route_policy_recommended(route_plan: dict[str, Any]) -> bool:
    policy = route_plan.get("subagent_runtime_policy")
    if not isinstance(policy, dict):
        return False
    return str(policy.get("execution_model") or "") in {"host_subagent_or_manual", *REQUIRED_EXECUTION_MODELS}


def route_policy_reason(route_plan: dict[str, Any]) -> str:
    policy = route_plan.get("subagent_runtime_policy")
    if isinstance(policy, dict) and str(policy.get("reason") or "").strip():
        return str(policy["reason"]).strip()
    return "Route plan subagent_runtime_policy requests host SubAgent dispatch."


def explicitly_disabled(task_payload: dict[str, Any]) -> bool:
    metadata = metadata_dict(task_payload)
    explicit_value = task_payload.get("use_subagents", metadata.get("use_subagents"))
    if explicit_value is False:
        return True
    mode = str(task_payload.get("subagent_mode") or metadata.get("subagent_mode") or "").strip().lower()
    if mode in {"off", "none", "main", "serial", "main_agent"}:
        return True
    return has_any(text_for_keys(task_payload, ("objective", "user_request", "summary", "prompt")), DISABLE_PHRASES)


def explicitly_requested(task_payload: dict[str, Any]) -> bool:
    metadata = metadata_dict(task_payload)
    explicit_value = task_payload.get("use_subagents", metadata.get("use_subagents"))
    if isinstance(explicit_value, bool):
        return explicit_value
    mode = str(task_payload.get("subagent_mode") or metadata.get("subagent_mode") or "").strip().lower()
    if mode in {"spawn", "parallel", "delegate", "delegated", "host"}:
        return True
    text = text_for_keys(task_payload, ("objective", "user_request", "summary", "prompt"))
    return not has_any(text, DISABLE_PHRASES) and has_any(text, REQUEST_PHRASES)


def review_gate_recommended(task_payload: dict[str, Any]) -> bool:
    if xhigh_review_dispatch_disabled(task_payload):
        return False
    text = text_for_keys(task_payload, ("objective", "user_request", "summary", "prompt", "next_step"))
    return not has_any(text, DISABLE_PHRASES) and has_any(text, REVIEW_GATE_PHRASES)


def xhigh_review_dispatch_disabled(task_payload: dict[str, Any]) -> bool:
    return (
        task_payload.get("xhigh_review_dispatch_disabled") is True
        or task_payload.get("review_gate_running") is True
    )


def complex_task_recommended(task_payload: dict[str, Any], route_plan: dict[str, Any]) -> bool:
    if str(route_plan.get("risk_level") or "") in {"high", "release_blocking"}:
        return True
    text = task_text(task_payload, route_plan)
    if not text:
        return False
    action = has_any(text, ACTION_WORDS)
    app = has_any(text, APP_WORDS)
    complex_signal = has_any(text, COMPLEX_WORDS)
    if action and app:
        return True
    if complex_signal and (action or app):
        return True
    if action and scope_size(task_payload, route_plan) >= 4:
        return True
    requirements = route_plan.get("requirements_gate") if isinstance(route_plan.get("requirements_gate"), dict) else {}
    intent = str(requirements.get("task_intent") or "")
    return intent in COMPLEX_INTENTS and (complex_signal or scope_size(task_payload, route_plan) >= 3)


def openspec_subagent_required(task_payload: dict[str, Any], route_plan: dict[str, Any]) -> bool:
    metadata = metadata_dict(task_payload)
    if any(metadata_value_is_required(source.get(key)) for source in (task_payload, metadata) for key in OPENSPEC_METADATA_KEYS):
        return True
    if openspec_required_paths(task_payload, route_plan):
        return True
    text = task_text(task_payload, route_plan)
    return "openspec" in text and has_any(text, OPENSPEC_EXECUTION_WORDS)


def openspec_required_reason(task_payload: dict[str, Any], route_plan: dict[str, Any]) -> str:
    paths = openspec_required_paths(task_payload, route_plan)
    if paths:
        return f"OpenSpec path requires host SubAgent dispatch: {paths[0]}"
    return "OpenSpec execution/change task requires host SubAgent dispatch before main Agent implementation."


def openspec_required_paths(task_payload: dict[str, Any], route_plan: dict[str, Any]) -> list[str]:
    return openspec_task_signals.contract_paths_from_task(task_payload, route_plan)


def metadata_value_is_required(value: Any) -> bool:
    if value is True:
        return True
    if value in (None, False, "", [], {}):
        return False
    return bool(str(value).strip())


def task_text(task_payload: dict[str, Any], route_plan: dict[str, Any]) -> str:
    metadata = metadata_dict(task_payload)
    parts: list[str] = []
    for source in (task_payload, metadata):
        for key in (
            "objective",
            "user_request",
            "summary",
            "prompt",
            "requirements",
            "acceptance",
            "acceptance_criteria",
            "architecture",
            "architecture_notes",
        ):
            parts.extend(string_list(source.get(key)))
    reasons = route_plan.get("reasons") if isinstance(route_plan.get("reasons"), list) else []
    parts.extend(str(item) for item in reasons if item)
    return " ".join(parts).lower()


def text_for_keys(task_payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    metadata = metadata_dict(task_payload)
    return " ".join(
        str(value)
        for source in (task_payload, metadata)
        for key in keys
        for value in string_list(source.get(key))
    ).lower()


def metadata_dict(task_payload: dict[str, Any]) -> dict[str, Any]:
    metadata = task_payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def scope_size(task_payload: dict[str, Any], route_plan: dict[str, Any]) -> int:
    paths = set(string_list(task_payload.get("working_set")) + string_list(task_payload.get("touched_paths")))
    for route in route_plan.get("routes") if isinstance(route_plan.get("routes"), list) else []:
        if isinstance(route, dict):
            paths.update(string_list(route.get("assigned_scope")))
    return len(paths)


def has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word_matches(text, word) for word in words)


def word_matches(text: str, word: str) -> bool:
    if word.isascii() and (word.replace("-", "").replace(" ", "").isalnum()):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text))
    return word in text


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
