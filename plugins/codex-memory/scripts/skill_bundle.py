from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from install_support import codex_home_root, home_root


def _skills_root(plugin_root: Path) -> Path:
    return plugin_root / "skills"


def bundled_manifest_path(plugin_root: Path) -> Path:
    return _skills_root(plugin_root) / "bundled-skills.json"


def bundled_source_root(plugin_root: Path) -> Path:
    return _skills_root(plugin_root) / "openai-curated"


def local_source_root(plugin_root: Path) -> Path:
    return _skills_root(plugin_root) / "local"


def user_skills_root() -> Path:
    return home_root() / ".agents" / "skills"


def legacy_codex_skills_root() -> Path:
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


def _manifest_skill_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in manifest.get("skills", []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"].strip()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized = dict(item)
        normalized["name"] = name
        items.append(normalized)
    return items


def _manifest_duplicate_count(manifest: dict[str, Any]) -> int:
    return len(_skill_names(manifest)) - len(_manifest_skill_items(manifest))


def _skill_source(plugin_root: Path, item: dict[str, Any]) -> Path:
    source_path = item.get("path")
    if isinstance(source_path, str) and source_path.strip():
        return _skills_root(plugin_root) / source_path
    source_group = item.get("source_group", "openai-curated")
    if source_group == "local":
        return local_source_root(plugin_root) / item["name"]
    return bundled_source_root(plugin_root) / item["name"]


def _copy_skill(src: Path, dst: Path) -> None:
    if not (src / "SKILL.md").exists():
        raise RuntimeError(f"Bundled skill source is missing SKILL.md: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _skill_md(path: Path) -> Path:
    return path / "SKILL.md"


def _file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _skill_tree_sha256(path: Path) -> str:
    if not path.exists() or not path.is_dir():
        return ""
    digest = hashlib.sha256()
    files = [
        item
        for item in path.rglob("*")
        if item.is_file()
        and "__pycache__" not in item.parts
        and item.suffix.lower() != ".pyc"
    ]
    for item in sorted(files, key=lambda value: value.relative_to(path).as_posix()):
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def ensure_bundled_skills(plugin_root: Path) -> dict[str, Any]:
    manifest = load_manifest(plugin_root)
    target_root = user_skills_root()
    results: list[dict[str, Any]] = []
    installed = 0
    skipped = 0

    for item in _manifest_skill_items(manifest):
        name = item["name"]
        src = _skill_source(plugin_root, item)
        dst = target_root / name
        if dst.exists():
            skipped += 1
            results.append(
                {
                    "name": name,
                    "path": str(dst),
                    "status": "deduped_existing",
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
        "legacy_target_root": str(legacy_codex_skills_root()),
        "source_ref": manifest.get("source_ref", ""),
        "installed": installed,
        "skipped_existing": skipped,
        "deduped_existing": skipped,
        "manifest_duplicate_count": _manifest_duplicate_count(manifest),
        "skills": results,
    }


def bundled_skills_status(plugin_root: Path) -> dict[str, Any]:
    manifest = load_manifest(plugin_root)
    target_root = user_skills_root()
    legacy_target_root = legacy_codex_skills_root()
    skills: list[dict[str, Any]] = []

    for item in _manifest_skill_items(manifest):
        name = item["name"]
        src = _skill_source(plugin_root, item)
        dst = target_root / name
        legacy_dst = legacy_target_root / name
        source_skill = _skill_md(src)
        target_skill = _skill_md(dst)
        source_digest = _skill_tree_sha256(src)
        target_digest = _skill_tree_sha256(dst)
        target_has_skill_md = target_skill.exists()
        source_exists = source_skill.exists()
        target_matches_source = bool(
            source_digest
            and target_digest
            and source_digest == target_digest
        )
        content_differs_from_source = bool(
            source_exists
            and target_has_skill_md
            and not target_matches_source
        )
        skills.append(
            {
                "name": name,
                "source_exists": source_exists,
                "target_exists": dst.exists(),
                "target_has_skill_md": target_has_skill_md,
                "source_digest": source_digest,
                "target_digest": target_digest,
                "target_matches_source": target_matches_source,
                "content_differs_from_source": content_differs_from_source,
                "deduped_existing": target_has_skill_md,
                "stale_existing": False,
                "legacy_target_exists": legacy_dst.exists(),
                "path": str(dst),
            }
        )

    return {
        "target_root": str(target_root),
        "legacy_target_root": str(legacy_target_root),
        "source_root": str(_skills_root(plugin_root)),
        "source_repo": manifest.get("source_repo", ""),
        "source_ref": manifest.get("source_ref", ""),
        "installed_by_default": bool(manifest.get("installed_by_default", False)),
        "overwrite_existing": bool(manifest.get("overwrite_existing", False)),
        "missing_manifest": bool(manifest.get("missing_manifest", False)),
        "manifest_skill_count": len(_skill_names(manifest)),
        "manifest_unique_skill_count": len(skills),
        "manifest_duplicate_count": _manifest_duplicate_count(manifest),
        "skills": skills,
        "installed_count": sum(1 for item in skills if item["target_has_skill_md"]),
        "missing_count": sum(1 for item in skills if not item["target_has_skill_md"]),
        "source_missing_count": sum(1 for item in skills if not item["source_exists"]),
        "deduped_existing_count": sum(1 for item in skills if item["deduped_existing"]),
        "content_differs_count": sum(1 for item in skills if item["content_differs_from_source"]),
        "stale_count": 0,
    }
