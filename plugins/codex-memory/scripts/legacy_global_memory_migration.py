from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from official_memory_status import HARNESS_RUNTIME_MARKERS, codex_home


MANIFEST_DIR = "migration-manifests"
BACKUP_DIR = "legacy-official-backups"


def build_plan(codex_home_root: Path | None = None) -> dict[str, Any]:
    root = (codex_home_root or codex_home()).expanduser().resolve()
    official_dir = root / "memories"
    target_dir = root / "codex-memory-harness" / "memories"
    migration_id = _migration_id()
    entries = [
        _entry(marker, official_dir / marker, target_dir / marker)
        for marker in HARNESS_RUNTIME_MARKERS
    ]
    blocked = [entry for entry in entries if entry.get("blocked")]
    return {
        "ok": not blocked,
        "migration_id": migration_id,
        "dry_run": True,
        "codex_home": str(root),
        "official_memories_dir": str(official_dir),
        "harness_global_memory_dir": str(target_dir),
        "manifest_path": str(target_dir / MANIFEST_DIR / f"{migration_id}.json"),
        "backup_dir": str(target_dir / BACKUP_DIR / migration_id),
        "markers": list(HARNESS_RUNTIME_MARKERS),
        "entries": entries,
        "blocked": blocked,
        "rollback": _rollback_text(target_dir / MANIFEST_DIR / f"{migration_id}.json"),
    }


def migrate(codex_home_root: Path | None = None, *, confirm: bool = False) -> dict[str, Any]:
    plan = build_plan(codex_home_root)
    if not confirm:
        return plan
    result = dict(plan)
    result["dry_run"] = False
    if plan["blocked"]:
        result["ok"] = False
        result["status"] = "blocked"
        return result

    manifest_path = Path(str(plan["manifest_path"]))
    backup_dir = Path(str(plan["backup_dir"]))
    target_dir = Path(str(plan["harness_global_memory_dir"]))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, {**result, "status": "started"})

    applied: list[dict[str, Any]] = []
    for entry in plan["entries"]:
        applied.append(_apply_entry(entry, backup_dir))
    result["entries"] = applied
    result["ok"] = all(item.get("applied") or item.get("action") in {"skip_missing", "already_migrated"} for item in applied)
    result["status"] = "completed" if result["ok"] else "partial_failure"
    result["rollback"] = _rollback_text(manifest_path)
    _write_json(manifest_path, result)
    return result


def _entry(marker: str, source: Path, target: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "marker": marker,
        "source": str(source),
        "target": str(target),
        "source_exists": source.exists(),
        "target_exists": target.exists(),
        "source_kind": _kind(source),
        "target_kind": _kind(target),
        "source_checksum": "",
        "target_checksum": "",
        "size_bytes": 0,
        "action": "skip_missing",
        "blocked": False,
        "blocked_reason": "",
    }
    if not source.exists():
        return payload
    if source.is_symlink():
        return _blocked(payload, "source is a symlink")
    if target.is_symlink():
        return _blocked(payload, "target is a symlink")
    source_nested_symlink = _first_nested_symlink(source)
    target_nested_symlink = _first_nested_symlink(target)
    if source_nested_symlink:
        return _blocked(payload, f"source contains symlink: {source_nested_symlink}")
    if target_nested_symlink:
        return _blocked(payload, f"target contains symlink: {target_nested_symlink}")
    if target.exists() and _kind(source) != _kind(target):
        return _blocked(payload, "target exists with a different kind")
    source_digest = _checksum(source)
    payload["source_checksum"] = source_digest["checksum"]
    payload["size_bytes"] = source_digest["size_bytes"]
    if target.exists():
        target_digest = _checksum(target)
        payload["target_checksum"] = target_digest["checksum"]
        if target_digest["checksum"] != source_digest["checksum"]:
            payload["action"] = "archive_conflicting_source"
            payload["conflict_reason"] = "target exists with different checksum"
            return payload
        payload["action"] = "already_migrated"
        return payload
    payload["action"] = "copy_then_archive_source"
    return payload


def _apply_entry(entry: dict[str, Any], backup_dir: Path) -> dict[str, Any]:
    result = dict(entry)
    source = Path(str(entry["source"]))
    target = Path(str(entry["target"]))
    action = str(entry["action"])
    if action == "skip_missing":
        result["applied"] = True
        return result
    if action == "copy_then_archive_source":
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy(source, target)
        copied = _checksum(target)
        if copied["checksum"] != entry["source_checksum"]:
            result.update({"applied": False, "error": "copied checksum mismatch"})
            return result
    archive_path = backup_dir / str(entry["marker"])
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        shutil.move(str(source), str(archive_path))
        result["source_archived_to"] = str(archive_path)
    result["applied"] = True
    return result


def _copy(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, copy_function=shutil.copy2)
        return
    shutil.copy2(source, target)


def _checksum(path: Path) -> dict[str, Any]:
    if path.is_dir():
        digest = hashlib.sha256()
        total = 0
        for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
            relative = file_path.relative_to(path).as_posix()
            file_digest = _file_hash(file_path)
            size = file_path.stat().st_size
            total += size
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_digest.encode("ascii"))
            digest.update(b"\0")
            digest.update(str(size).encode("ascii"))
            digest.update(b"\0")
        return {"checksum": f"sha256-dir:{digest.hexdigest()}", "size_bytes": total}
    return {"checksum": f"sha256:{_file_hash(path)}", "size_bytes": path.stat().st_size}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _kind(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


def _first_nested_symlink(path: Path) -> str:
    if not path.exists() or not path.is_dir():
        return ""
    for item in path.rglob("*"):
        if item.is_symlink():
            return str(item)
    return ""


def _blocked(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    payload["blocked"] = True
    payload["blocked_reason"] = reason
    payload["action"] = "blocked"
    return payload


def _migration_id() -> str:
    return "legacy-global-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rollback_text(manifest_path: Path) -> str:
    return (
        "Rollback is manual and manifest-driven: read this manifest, move each "
        "`source_archived_to` path back to its `source` path, then remove target "
        "markers whose action was `copy_then_archive_source` if they were created "
        f"by this migration. Manifest: {manifest_path}"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy harness global memory markers out of official Codex Memories.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview migration without writing files. This is the default.")
    mode.add_argument("--confirm", action="store_true", help="Copy markers to harness global memory and archive the official-dir sources.")
    parser.add_argument("--codex-home", help="Override CODEX_HOME for testing or explicit migration.")
    args = parser.parse_args()

    result = migrate(Path(args.codex_home).expanduser() if args.codex_home else None, confirm=args.confirm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
