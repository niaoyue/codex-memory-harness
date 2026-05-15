from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openspec_upstream_manifest import PINNED_VERSION, verify_project
from openspec_upstream_sync import sync_from_npm


DISABLE_ENV = "CODEX_MEMORY_DISABLE_OPENSPEC_UPSTREAM"


def ensure_default_openspec_upstream(project_root: Path) -> list[dict[str, Any]]:
    if _env_truthy(DISABLE_ENV):
        return [
            {
                "action": "openspec_upstream_default",
                "status": "skipped",
                "ok": False,
                "reason": f"{DISABLE_ENV}=1",
                "next_step": (
                    f"Unset {DISABLE_ENV}, then run "
                    f"codex openspec upstream sync --version {PINNED_VERSION} "
                    "and codex openspec upstream verify."
                ),
            }
        ]

    try:
        sync_result = sync_from_npm(project_root, version=PINNED_VERSION)
    except Exception as exc:
        return [
            {
                "action": "openspec_upstream_sync",
                "status": "degraded",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "next_step": (
                    f"Retry codex openspec upstream sync --version {PINNED_VERSION}; "
                    "then run codex openspec upstream verify."
                ),
            }
        ]

    actions = [_result_action("openspec_upstream_sync", sync_result)]
    if sync_result.get("ok"):
        actions.append(_result_action("openspec_upstream_verify", verify_project(project_root)))
    else:
        actions.append(
            {
                "action": "openspec_upstream_verify",
                "status": "skipped",
                "ok": False,
                "reason": "sync_failed",
                "failures": sync_result.get("failures", []),
            }
        )
    return actions


def _result_action(action: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action,
        "status": result.get("status", "unknown"),
        "ok": bool(result.get("ok")),
        "manifest": result.get("manifest", ""),
        "resolved_version": result.get("resolved_version", ""),
        "files": result.get("files", 0),
        "failures": result.get("failures", []),
    }


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
