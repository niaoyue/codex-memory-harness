from __future__ import annotations

import re
from typing import Any


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


def route_policy_recommended(route_plan: dict[str, Any]) -> bool:
    policy = route_plan.get("subagent_runtime_policy")
    if not isinstance(policy, dict):
        return False
    return str(policy.get("execution_model") or "") == "host_subagent_or_manual"


def route_policy_reason(route_plan: dict[str, Any]) -> str:
    policy = route_plan.get("subagent_runtime_policy")
    if isinstance(policy, dict) and str(policy.get("reason") or "").strip():
        return str(policy["reason"]).strip()
    return "Route plan subagent_runtime_policy requests host_subagent_or_manual."


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
