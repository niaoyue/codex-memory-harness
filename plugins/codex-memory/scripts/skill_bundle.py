from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from install_support import codex_home_root


def _skills_root(plugin_root: Path) -> Path:
    return plugin_root / "skills"


def bundled_manifest_path(plugin_root: Path) -> Path:
    return _skills_root(plugin_root) / "bundled-skills.json"


def bundled_source_root(plugin_root: Path) -> Path:
    return _skills_root(plugin_root) / "openai-curated"


def codex_skills_root() -> Path:
    return codex_home_root() / "skills"


def load_manifest(plugin_root: Path) -> dict[str, Any]:
    path = bundled_manifest_path(plugin_root)
    if not path.exists():
        return {
            "version": 1,
            "source_repo": "",
            "source_ref": "",
            "skills": [],
            "missing_manifest": True,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("skills", [])
    return payload


def _skill_names(manifest: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in manifest.get("skills", []):
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def _copy_skill(src: Path, dst: Path) -> None:
    if not (src / "SKILL.md").exists():
        raise RuntimeError(f"Bundled skill source is missing SKILL.md: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def ensure_bundled_skills(plugin_root: Path) -> dict[str, Any]:
    manifest = load_manifest(plugin_root)
    source_root = bundled_source_root(plugin_root)
    target_root = codex_skills_root()
    results: list[dict[str, Any]] = []
    installed = 0
    skipped = 0

    for name in _skill_names(manifest):
        src = source_root / name
        dst = target_root / name
        if dst.exists():
            skipped += 1
            results.append(
                {
                    "name": name,
                    "path": str(dst),
                    "status": "already_exists",
                    "installed": False,
                }
            )
            continue
        _copy_skill(src, dst)
        installed += 1
        results.append(
            {
                "name": name,
                "path": str(dst),
                "status": "installed",
                "installed": True,
            }
        )

    return {
        "target_root": str(target_root),
        "source_ref": manifest.get("source_ref", ""),
        "installed": installed,
        "skipped_existing": skipped,
        "skills": results,
    }


def bundled_skills_status(plugin_root: Path) -> dict[str, Any]:
    manifest = load_manifest(plugin_root)
    source_root = bundled_source_root(plugin_root)
    target_root = codex_skills_root()
    skills: list[dict[str, Any]] = []

    for name in _skill_names(manifest):
        src = source_root / name
        dst = target_root / name
        skills.append(
            {
                "name": name,
                "source_exists": (src / "SKILL.md").exists(),
                "target_exists": dst.exists(),
                "target_has_skill_md": (dst / "SKILL.md").exists(),
                "path": str(dst),
            }
        )

    return {
        "target_root": str(target_root),
        "source_root": str(source_root),
        "source_repo": manifest.get("source_repo", ""),
        "source_ref": manifest.get("source_ref", ""),
        "installed_by_default": bool(manifest.get("installed_by_default", False)),
        "overwrite_existing": bool(manifest.get("overwrite_existing", False)),
        "missing_manifest": bool(manifest.get("missing_manifest", False)),
        "skills": skills,
        "installed_count": sum(1 for item in skills if item["target_has_skill_md"]),
        "missing_count": sum(1 for item in skills if not item["target_has_skill_md"]),
        "source_missing_count": sum(1 for item in skills if not item["source_exists"]),
    }
