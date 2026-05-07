from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
from datetime import datetime, timezone
from uuid import uuid4
import json
import os
import sqlite3
import sys
from typing import Any

import review_gate_env
from hook_runner import HookRunner


CODEX_EVENT_MAP = {
    "PostToolUse": "after_tool",
    "SessionStart": "on_session_start",
    "Stop": "before_response",
    "TaskComplete": "on_task_complete",
    "OnTaskComplete": "on_task_complete",
    "UserPromptSubmit": "before_task",
    "codex-memory-complete": "on_task_complete",
}

CWD_KEYS = ("cwd", "working_directory", "workingDirectory")
TASK_ID_KEYS = ("task_id", "taskId", "codex_memory_task_id", "codexMemoryTaskId")
SCOPE_ID_KEYS = (
    "session_id",
    "sessionId",
    "conversation_id",
    "conversationId",
    "thread_id",
    "threadId",
    "chat_id",
    "chatId",
    "run_id",
    "runId",
)
TURN_ID_KEYS = (
    "turn_id",
    "turnId",
    "prompt_id",
    "promptId",
    "submission_id",
    "submissionId",
    "request_id",
    "requestId",
    "user_prompt_id",
    "userPromptId",
)
HOOK_TASK_META_PREFIX = "hook_task_map:"
HOOK_TASK_SQLITE_TIMEOUT_SECONDS = 30.0
HOOK_TASK_CACHE: dict[str, str] = {}


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    return [str(value).strip()]


def _load_stdin_payload() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Hook stdin payload must decode to an object.")
    return value


def _pick_first(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, "", []):
            return payload[key]
    return None


def _copy_cwd_fields(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    selected_cwd = _string(_pick_first(source, list(CWD_KEYS)))
    if selected_cwd:
        target["cwd"] = selected_cwd
    for key in CWD_KEYS:
        value = _string(source.get(key))
        if value:
            target[key] = value
    return target


def _new_prompt_task_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"prompt-{stamp}-{uuid4().hex[:8]}"


def _normalize_payload(
    codex_event: str,
    payload: dict[str, Any],
    *,
    persist_hook_task: bool = False,
) -> tuple[str, dict[str, Any]]:
    target_event = CODEX_EVENT_MAP.get(codex_event, "after_tool")
    task_id = _resolve_hook_task_id(codex_event, payload, target_event, persist=persist_hook_task)
    if target_event == "before_task":
        prompt = _string(
            _pick_first(
                payload,
                [
                    "prompt",
                    "user_prompt",
                    "userPrompt",
                    "message",
                    "input",
                    "text",
                    "summary",
                ],
            )
        )
        return target_event, _mark_review_gate_payload(_copy_cwd_fields(payload, {
            "task_id": task_id,
            "objective": prompt,
            "user_request": prompt,
            "cwd": _string(_pick_first(payload, ["cwd", "working_directory", "workingDirectory"])),
        }))

    if target_event == "after_tool":
        summary = _string(
            _pick_first(
                payload,
                [
                    "summary",
                    "tool_output_summary",
                    "toolOutputSummary",
                    "tool_output",
                    "output",
                    "stdout",
                    "message",
                    "result",
                ],
            )
        ) or "Tool executed via Codex hook."
        touched_paths = _string_list(
            _pick_first(
                payload,
                [
                    "touched_paths",
                    "touchedPaths",
                    "file_paths",
                    "filePaths",
                    "files",
                    "paths",
                    "target_file",
                    "targetFile",
                ],
            )
        )
        return target_event, _mark_review_gate_payload(_copy_cwd_fields(payload, {
            "task_id": task_id,
            "tool_name": _string(
                _pick_first(payload, ["tool_name", "toolName", "tool", "name"])
            )
            or codex_event,
            "summary": summary,
            "touched_paths": touched_paths,
        }))

    if target_event in {"before_response", "on_task_complete"}:
        summary_markdown = _string(_pick_first(payload, ["summary_markdown", "summaryMarkdown"]))
        summary = _string(_pick_first(payload, ["summary", "message"]))
        normalized = {
            "task_id": task_id,
            "summary": summary,
            "summary_markdown": summary_markdown or summary,
        }
        if codex_event == "Stop":
            normalized["writeback"] = True
        return target_event, _mark_review_gate_payload(_copy_cwd_fields(payload, normalized))

    return target_event, _mark_review_gate_payload(dict(payload))


def _mark_review_gate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not review_gate_env.xhigh_review_dispatch_disabled():
        return payload
    payload["review_gate_running"] = review_gate_env.review_gate_running()
    payload["xhigh_review_dispatch_disabled"] = True
    return payload


def _resolve_hook_task_id(
    codex_event: str,
    payload: dict[str, Any],
    target_event: str,
    *,
    persist: bool,
) -> str:
    explicit = _string(_pick_first(payload, list(TASK_ID_KEYS)))
    scope_key = _hook_scope_key(payload)
    turn_key = _hook_turn_key(payload)
    if explicit:
        if persist:
            _remember_hook_task_keys(scope_key, turn_key, explicit)
        return explicit

    if turn_key:
        association_key = f"{scope_key}|{turn_key}" if scope_key else turn_key
        remembered = _recall_hook_task(association_key) if persist else ""
        task_id = remembered or _stable_task_id("prompt", association_key)
        if persist:
            _remember_hook_task(association_key, task_id)
            if target_event == "before_task" and scope_key:
                _remember_hook_task(scope_key, task_id)
        return task_id

    if target_event == "before_task":
        task_id = _new_prompt_task_id()
        if persist and scope_key:
            _remember_hook_task(scope_key, task_id)
        return task_id

    if scope_key:
        remembered = _recall_hook_task(scope_key) if persist else ""
        task_id = remembered or _stable_task_id("hook", scope_key)
        if persist and scope_key:
            _remember_hook_task(scope_key, task_id)
        return task_id

    return _isolated_event_task_id(codex_event)


def _hook_scope_key(payload: dict[str, Any]) -> str:
    identifier = _identifier_pair(payload, SCOPE_ID_KEYS, ("session", "conversation", "thread", "chat", "run"))
    if not identifier:
        return ""
    cwd = _string(_pick_first(payload, list(CWD_KEYS)))
    scope = f"{identifier[0]}:{identifier[1]}"
    return f"{scope}|cwd:{cwd}" if cwd else scope


def _hook_turn_key(payload: dict[str, Any]) -> str:
    identifier = _identifier_pair(payload, TURN_ID_KEYS, ("turn", "prompt", "submission", "request"))
    return f"{identifier[0]}:{identifier[1]}" if identifier else ""


def _identifier_pair(
    payload: dict[str, Any],
    keys: tuple[str, ...],
    nested_keys: tuple[str, ...],
) -> tuple[str, str] | None:
    for key in keys:
        value = _string(payload.get(key))
        if value:
            return key, value
    for key in nested_keys:
        nested = payload.get(key)
        if not isinstance(nested, dict):
            continue
        value = _string(_pick_first(nested, ["id", "uuid", "key"]))
        if value:
            return f"{key}.id", value
    return None


def _stable_task_id(prefix: str, raw_key: str) -> str:
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _isolated_event_task_id(codex_event: str) -> str:
    event_name = "".join(ch.lower() if ch.isalnum() else "-" for ch in codex_event).strip("-") or "hook"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"hook-{event_name}-{stamp}-{uuid4().hex[:8]}"


def _remember_hook_task(scope_key: str, task_id: str) -> None:
    if not scope_key or not task_id:
        return
    meta_key = _hook_task_meta_key(scope_key)
    safe_task_id = _safe_hook_task_id(task_id)
    payload = {
        "task_id": safe_task_id,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    try:
        import init_storage

        layout = init_storage.ensure_storage_layout()
        HOOK_TASK_CACHE[_hook_task_cache_key(layout["db_path"], meta_key)] = safe_task_id
        with closing(_connect_hook_db(layout["db_path"])) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO plugin_meta (key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (meta_key, json.dumps(payload, ensure_ascii=False), payload["updated_at"]),
                )
    except Exception:
        return


def _safe_hook_task_id(task_id: str) -> str:
    try:
        from memory_store import _safe_task_id

        return _safe_task_id(task_id) or "task"
    except Exception:
        return _stable_task_id("task", task_id)


def _remember_hook_task_keys(scope_key: str, turn_key: str, task_id: str) -> None:
    if scope_key:
        _remember_hook_task(scope_key, task_id)
    if turn_key:
        association_key = f"{scope_key}|{turn_key}" if scope_key else turn_key
        _remember_hook_task(association_key, task_id)


def _recall_hook_task(scope_key: str) -> str:
    if not scope_key:
        return ""
    meta_key = _hook_task_meta_key(scope_key)
    try:
        import init_storage

        layout = init_storage.ensure_storage_layout()
        cached = HOOK_TASK_CACHE.get(_hook_task_cache_key(layout["db_path"], meta_key), "")
        with closing(_connect_hook_db(layout["db_path"])) as conn:
            row = conn.execute(
                "SELECT value_json FROM plugin_meta WHERE key = ?",
                (meta_key,),
            ).fetchone()
        if not row:
            return cached
        payload = json.loads(str(row[0]))
    except Exception:
        return locals().get("cached", "")
    task_id = _string(payload.get("task_id")) if isinstance(payload, dict) else ""
    if task_id:
        HOOK_TASK_CACHE[_hook_task_cache_key(layout["db_path"], meta_key)] = task_id
    return task_id or cached


def _connect_hook_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=HOOK_TASK_SQLITE_TIMEOUT_SECONDS)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _hook_task_meta_key(scope_key: str) -> str:
    digest = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
    return f"{HOOK_TASK_META_PREFIX}{digest}"


def _hook_task_cache_key(db_path: str, meta_key: str) -> str:
    return f"{db_path}|{meta_key}"


def _apply_payload_cwd(payload: dict[str, Any]) -> str | None:
    cwd = _string(_pick_first(payload, list(CWD_KEYS)))
    if not cwd:
        return None
    previous = os.environ.get("CODEX_MEMORY_CWD")
    os.environ["CODEX_MEMORY_CWD"] = cwd
    return previous


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge Codex plugin hooks to Codex Memory events.")
    parser.add_argument("--codex-event", required=True, help="Hook event name from Codex.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on degraded execution.")
    parser.add_argument("--verbose", action="store_true", help="Print structured result.")
    args = parser.parse_args()

    payload = _load_stdin_payload()
    old_cwd = _apply_payload_cwd(payload)
    try:
        target_event, normalized_payload = _normalize_payload(
            args.codex_event,
            payload,
            persist_hook_task=True,
        )
        result = HookRunner().run_event(target_event, normalized_payload)
    finally:
        _restore_env("CODEX_MEMORY_CWD", old_cwd)

    if args.verbose:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict and result.get("degraded"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
