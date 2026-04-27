from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from hook_runner import HookRunner


CODEX_EVENT_MAP = {
    "PostToolUse": "after_tool",
    "SessionStart": "on_session_start",
    "Stop": "on_task_complete",
}


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


def _normalize_payload(codex_event: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    target_event = CODEX_EVENT_MAP.get(codex_event, "after_tool")
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
        return target_event, {
            "task_id": _string(_pick_first(payload, ["task_id", "taskId"])),
            "tool_name": _string(
                _pick_first(payload, ["tool_name", "toolName", "tool", "name"])
            )
            or codex_event,
            "summary": summary,
            "touched_paths": touched_paths,
        }

    if target_event == "on_task_complete":
        return target_event, {
            "task_id": _string(_pick_first(payload, ["task_id", "taskId"])),
            "summary_markdown": _string(
                _pick_first(payload, ["summary_markdown", "summaryMarkdown", "summary"])
            ),
        }

    return target_event, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge Codex plugin hooks to Codex Memory events.")
    parser.add_argument("--codex-event", required=True, help="Hook event name from Codex.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on degraded execution.")
    parser.add_argument("--verbose", action="store_true", help="Print structured result.")
    args = parser.parse_args()

    payload = _load_stdin_payload()
    target_event, normalized_payload = _normalize_payload(args.codex_event, payload)
    result = HookRunner().run_event(target_event, normalized_payload)

    if args.verbose:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict and result.get("degraded"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
