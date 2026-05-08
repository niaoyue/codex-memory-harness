from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PLUGIN_NAME = "codex-memory"
PLUGIN_CATEGORY = "Productivity"
PLUGIN_POLICY = {
    "installation": "INSTALLED_BY_DEFAULT",
    "authentication": "ON_INSTALL",
}


def marketplace_entry(source_path: str) -> dict[str, Any]:
    return {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": source_path},
        "policy": dict(PLUGIN_POLICY),
        "category": PLUGIN_CATEGORY,
    }


def upsert_marketplace_entry(
    path: Path,
    default_name: str,
    default_display_name: str,
    source_path: str,
) -> dict[str, Any]:
    marketplace = _read_json(
        path,
        {
            "name": default_name,
            "interface": {"displayName": default_display_name},
            "plugins": [],
        },
    )
    plugins = marketplace.setdefault("plugins", [])
    interface = marketplace.setdefault("interface", {})
    interface.setdefault("displayName", default_display_name)
    marketplace.setdefault("name", default_name)

    entry = marketplace_entry(source_path)
    for index, existing in enumerate(plugins):
        if existing.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            _write_json(path, marketplace)
            return {"path": str(path), "updated": True, "created": False}

    plugins.append(entry)
    _write_json(path, marketplace)
    return {"path": str(path), "updated": False, "created": True}


def remove_marketplace_entry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "removed": False}
    marketplace = _read_json(path, {"plugins": []})
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        return {"path": str(path), "exists": True, "removed": False}
    original_count = len(plugins)
    marketplace["plugins"] = [
        item for item in plugins if not (isinstance(item, dict) and item.get("name") == PLUGIN_NAME)
    ]
    removed = len(marketplace["plugins"]) != original_count
    if removed:
        _write_json(path, marketplace)
    return {"path": str(path), "exists": True, "removed": removed}


def marketplace_plan(
    path: Path,
    *,
    default_name: str,
    default_display_name: str,
    source_path: str,
) -> dict[str, Any]:
    entry = marketplace_entry(source_path)
    if not path.exists():
        return {
            "path": str(path),
            "category": "marketplace",
            "default_name": default_name,
            "default_display_name": default_display_name,
            "source_path": source_path,
            "status": "missing",
            "action": "create_file",
            "would_write": True,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "category": "marketplace",
            "status": "parse_error",
            "action": "blocked",
            "would_write": False,
            "blocked": True,
            "reason": str(exc),
        }
    if not isinstance(payload, dict):
        return _blocked_plan(path, "invalid_root", "marketplace JSON must be an object")
    interface = payload.get("interface", {})
    if not isinstance(interface, dict):
        return _blocked_plan(path, "invalid_interface", "interface must be an object")
    plugins = payload.get("plugins", [])
    if not isinstance(plugins, list) or not all(isinstance(item, dict) for item in plugins):
        return _blocked_plan(path, "invalid_plugins", "plugins must be a list of objects")
    existing = next((item for item in plugins if isinstance(item, dict) and item.get("name") == PLUGIN_NAME), None)
    if existing == entry:
        action = "rewrite_existing_entry"
    elif existing:
        action = "update_entry"
    else:
        action = "add_entry"
    return {
        "path": str(path),
        "category": "marketplace",
        "default_name": default_name,
        "default_display_name": default_display_name,
        "source_path": source_path,
        "status": "entry_present" if existing else "entry_missing",
        "action": action,
        "would_write": True,
    }


def _blocked_plan(path: Path, status: str, reason: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "category": "marketplace",
        "status": status,
        "action": "blocked",
        "would_write": False,
        "blocked": True,
        "reason": reason,
    }


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
