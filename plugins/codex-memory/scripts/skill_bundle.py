from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
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


def system_skills_root() -> Path:
    return legacy_codex_skills_root() / ".system"


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


def _backup_existing_skill(dst: Path, backup_root: Path) -> Path:
    _assert_safe_skill_move(dst, backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_root / f"{dst.name}.backup-{timestamp}"
    suffix = 1
    while backup.exists():
        backup = backup_root / f"{dst.name}.backup-{timestamp}-{suffix}"
        suffix += 1
    shutil.move(str(dst), str(backup))
    return backup


def _assert_safe_skill_move(dst: Path, backup_root: Path) -> None:
    source_parent = dst.parent.resolve(strict=False)
    backup_parent = backup_root.parent.resolve(strict=False)
    source = dst.resolve(strict=False)
    backup = backup_root.resolve(strict=False)
    if source_parent not in source.parents and source != source_parent:
        raise RuntimeError(f"Refusing to move skill outside its skills root: {dst}")
    if backup_parent not in backup.parents and backup != backup_parent:
        raise RuntimeError(f"Refusing to back up skill outside its skills root: {backup_root}")


def _skill_md(path: Path) -> Path:
    return path / "SKILL.md"


def _has_skill_md(path: Path) -> bool:
    return _skill_md(path).exists()


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
    backup_root = target_root / ".codex-memory-backups"
    legacy_target_root = legacy_codex_skills_root()
    legacy_backup_root = legacy_target_root / ".codex-memory-backups"
    system_target_root = system_skills_root()
    overwrite_existing = bool(manifest.get("overwrite_existing", False))
    results: list[dict[str, Any]] = []
    installed = 0
    updated = 0
    skipped = 0
    retired_legacy_duplicates = 0
    retired_system_duplicates = 0

    for item in _manifest_skill_items(manifest):
        name = item["name"]
        src = _skill_source(plugin_root, item)
        dst = target_root / name
        legacy_dst = legacy_target_root / name
        system_dst = system_target_root / name
        if not (src / "SKILL.md").exists():
            raise RuntimeError(f"Bundled skill source is missing SKILL.md: {src}")
        system_builtin_available = _has_skill_md(system_dst)
        legacy_backup = ""
        if system_builtin_available:
            system_backup = ""
            if dst.exists():
                system_backup = str(_backup_existing_skill(dst, backup_root))
                retired_system_duplicates += 1
            if _has_skill_md(legacy_dst):
                legacy_backup = str(_backup_existing_skill(legacy_dst, legacy_backup_root))
                retired_legacy_duplicates += 1
            skipped += 1
            results.append(
                {
                    "name": name,
                    "path": str(dst),
                    "status": "system_builtin",
                    "installed": False,
                    "updated": False,
                    "system_target_path": str(system_dst),
                    "system_duplicate_retired": bool(system_backup),
                    "system_duplicate_backup_path": system_backup,
                    "legacy_duplicate_retired": bool(legacy_backup),
                    "legacy_duplicate_backup_path": legacy_backup,
                }
            )
            continue
        if dst.exists():
            source_digest = _skill_tree_sha256(src)
            target_digest = _skill_tree_sha256(dst)
            if source_digest and source_digest == target_digest:
                if _has_skill_md(legacy_dst):
                    legacy_backup = str(_backup_existing_skill(legacy_dst, legacy_backup_root))
                    retired_legacy_duplicates += 1
                skipped += 1
                results.append(
                    {
                        "name": name,
                        "path": str(dst),
                        "status": "already_current",
                        "installed": False,
                        "updated": False,
                        "legacy_duplicate_retired": bool(legacy_backup),
                        "legacy_duplicate_backup_path": legacy_backup,
                    }
                )
                continue
            if not overwrite_existing:
                if _has_skill_md(legacy_dst):
                    legacy_backup = str(_backup_existing_skill(legacy_dst, legacy_backup_root))
                    retired_legacy_duplicates += 1
                skipped += 1
                results.append(
                    {
                        "name": name,
                        "path": str(dst),
                        "status": "deduped_existing",
                        "installed": False,
                        "updated": False,
                        "legacy_duplicate_retired": bool(legacy_backup),
                        "legacy_duplicate_backup_path": legacy_backup,
                    }
                )
                continue
            backup = _backup_existing_skill(dst, backup_root)
            _copy_skill(src, dst)
            if _has_skill_md(legacy_dst):
                legacy_backup = str(_backup_existing_skill(legacy_dst, legacy_backup_root))
                retired_legacy_duplicates += 1
            updated += 1
            results.append(
                {
                    "name": name,
                    "path": str(dst),
                    "status": "updated",
                    "backup_path": str(backup),
                    "installed": False,
                    "updated": True,
                    "legacy_duplicate_retired": bool(legacy_backup),
                    "legacy_duplicate_backup_path": legacy_backup,
                }
            )
            continue
        _copy_skill(src, dst)
        if _has_skill_md(legacy_dst):
            legacy_backup = str(_backup_existing_skill(legacy_dst, legacy_backup_root))
            retired_legacy_duplicates += 1
        installed += 1
        results.append(
            {
                "name": name,
                "path": str(dst),
                "status": "installed",
                "installed": True,
                "updated": False,
                "legacy_duplicate_retired": bool(legacy_backup),
                "legacy_duplicate_backup_path": legacy_backup,
            }
        )

    return {
        "target_root": str(target_root),
        "legacy_target_root": str(legacy_target_root),
        "system_target_root": str(system_target_root),
        "backup_root": str(backup_root),
        "legacy_backup_root": str(legacy_backup_root),
        "source_ref": manifest.get("source_ref", ""),
        "installed": installed,
        "updated": updated,
        "skipped_existing": skipped,
        "deduped_existing": skipped,
        "retired_legacy_duplicates": retired_legacy_duplicates,
        "retired_system_duplicates": retired_system_duplicates,
        "manifest_duplicate_count": _manifest_duplicate_count(manifest),
        "skills": results,
    }


def bundled_skills_status(plugin_root: Path) -> dict[str, Any]:
    manifest = load_manifest(plugin_root)
    target_root = user_skills_root()
    legacy_target_root = legacy_codex_skills_root()
    system_target_root = system_skills_root()
    skills: list[dict[str, Any]] = []

    for item in _manifest_skill_items(manifest):
        name = item["name"]
        src = _skill_source(plugin_root, item)
        dst = target_root / name
        legacy_dst = legacy_target_root / name
        system_dst = system_target_root / name
        source_skill = _skill_md(src)
        target_skill = _skill_md(dst)
        source_digest = _skill_tree_sha256(src)
        target_digest = _skill_tree_sha256(dst)
        target_has_skill_md = target_skill.exists()
        legacy_has_skill_md = _has_skill_md(legacy_dst)
        system_has_skill_md = _has_skill_md(system_dst)
        source_exists = source_skill.exists()
        target_matches_source = bool(
            source_digest
            and target_digest
            and source_digest == target_digest
        )
        available = bool(target_has_skill_md or system_has_skill_md)
        legacy_duplicate = bool(legacy_has_skill_md and available)
        legacy_retirement_required = bool(source_exists and legacy_has_skill_md)
        system_duplicate = bool(system_has_skill_md and target_has_skill_md)
        content_differs_from_source = bool(
            source_exists
            and target_has_skill_md
            and not target_matches_source
        )
        stale_existing = bool(dst.exists() and source_exists and not target_matches_source)
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
                "stale_existing": stale_existing,
                "legacy_target_exists": legacy_dst.exists(),
                "legacy_target_has_skill_md": legacy_has_skill_md,
                "legacy_duplicate": legacy_duplicate,
                "legacy_retirement_required": legacy_retirement_required,
                "system_target_exists": system_dst.exists(),
                "system_target_has_skill_md": system_has_skill_md,
                "system_duplicate": system_duplicate,
                "available": available,
                "path": str(dst),
                "legacy_path": str(legacy_dst),
                "system_path": str(system_dst),
            }
        )

    return {
        "target_root": str(target_root),
        "legacy_target_root": str(legacy_target_root),
        "system_target_root": str(system_target_root),
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
        "available_count": sum(1 for item in skills if item["available"]),
        "missing_count": sum(1 for item in skills if not item["available"]),
        "source_missing_count": sum(1 for item in skills if not item["source_exists"]),
        "deduped_existing_count": sum(1 for item in skills if item["deduped_existing"]),
        "content_differs_count": sum(1 for item in skills if item["content_differs_from_source"]),
        "stale_count": sum(1 for item in skills if item["stale_existing"]),
        "legacy_duplicate_count": sum(1 for item in skills if item["legacy_duplicate"]),
        "system_duplicate_count": sum(1 for item in skills if item["system_duplicate"]),
        "duplicate_count": sum(
            1 for item in skills if item["legacy_duplicate"] or item["system_duplicate"]
        ),
    }
