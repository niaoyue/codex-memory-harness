from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None


HARNESS_GLOBAL_SUBDIR = "codex-memory-harness"
HARNESS_RUNTIME_MARKERS = ("memory.db", "events.jsonl", "summaries", "distilled")


def codex_home(home: Path | None = None) -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return (home or Path.home()) / ".codex"


def official_memories_dir(home: Path | None = None) -> Path:
    return codex_home(home) / "memories"


def harness_global_memory_dir(home: Path | None = None) -> Path:
    return codex_home(home) / HARNESS_GLOBAL_SUBDIR / "memories"


def inspect_official_memory(home: Path | None = None) -> dict[str, Any]:
    root = codex_home(home)
    official_dir = official_memories_dir(home)
    harness_dir = harness_global_memory_dir(home)
    config_path = root / "config.toml"
    config = _read_config(config_path)
    values = config.get("values") if isinstance(config.get("values"), dict) else {}
    feature_flag = _nested(values, "features.memories")
    generate = _nested(values, "memories.generate_memories")
    use_memories = _nested(values, "memories.use_memories")
    feature_enabled = feature_flag is True and generate is not False and use_memories is not False
    legacy_markers = [name for name in HARNESS_RUNTIME_MARKERS if (official_dir / name).exists()]

    return {
        "codex_home": str(root),
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "config_parse_ok": config["ok"],
        "config_error": config["error"],
        "features_memories": feature_flag if isinstance(feature_flag, bool) else None,
        "memories_generate_memories": generate if isinstance(generate, bool) else None,
        "memories_use_memories": use_memories if isinstance(use_memories, bool) else None,
        "official_feature_enabled": feature_enabled,
        "official_memories_dir": str(official_dir),
        "official_memories_dir_exists": official_dir.exists(),
        "harness_global_memory_dir": str(harness_dir),
        "harness_global_memory_dir_exists": harness_dir.exists(),
        "legacy_harness_markers_in_official_dir": legacy_markers,
        "official_dir_reserved_for_codex": True,
        "chronicle": inspect_chronicle_status(),
    }


def inspect_chronicle_status() -> dict[str, Any]:
    temp_root = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    screen_dir = temp_root / "chronicle" / "screen_recording"
    return {
        "platform": sys.platform,
        "platform_supported_by_official_preview": sys.platform == "darwin",
        "screen_recording_dir": str(screen_dir),
        "screen_recording_dir_exists": screen_dir.exists(),
        "content_read": False,
        "note": "Chronicle is treated as optional personal context, not project memory.",
    }


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": True, "values": {}, "error": ""}
    if tomllib is None:
        return {"ok": False, "values": {}, "error": "tomllib is unavailable"}
    try:
        return {"ok": True, "values": tomllib.loads(path.read_text(encoding="utf-8")), "error": ""}
    except Exception as exc:  # keep doctor non-fatal and read-only
        return {"ok": False, "values": {}, "error": str(exc)}


def _nested(payload: dict[str, Any], dotted: str) -> Any:
    value: Any = payload
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value
