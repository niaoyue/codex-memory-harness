from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from openspec_upstream_manifest import (
    MANIFEST_NAME,
    PACKAGE_NAME,
    PINNED_VERSION,
    SCHEMA_NAME,
    TARGET_RELATIVE,
    UPSTREAM_FILES,
    verify_target,
)


OFFICIAL_NPM_REGISTRY = "https://registry.npmjs.org/"
OFFICIAL_NPM_HOST = "registry.npmjs.org"
NPM_TIMEOUT_SECONDS = 120
NPM_RETRY_LIMIT = 1
BACKOFF_429_SECONDS = 20
BACKOFF_TRANSIENT_SECONDS = 2


def npm_command() -> str:
    for name in ("npm.cmd", "npm"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError("npm executable was not found in PATH.")


def telemetry_safe_env() -> dict[str, str]:
    env = dict(os.environ)
    env["OPENSPEC_TELEMETRY"] = "0"
    env["DO_NOT_TRACK"] = "1"
    env["npm_config_registry"] = OFFICIAL_NPM_REGISTRY
    env["NPM_CONFIG_REGISTRY"] = OFFICIAL_NPM_REGISTRY
    return env


def run_json(args: list[str], cwd: Path) -> Any:
    result = run_external(args, cwd)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}"
        )
    return json.loads(result.stdout)


def run_external(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    attempts = 0
    while True:
        try:
            result = subprocess.run(
                args,
                cwd=cwd,
                text=True,
                capture_output=True,
                encoding="utf-8",
                shell=False,
                env=telemetry_safe_env(),
                timeout=NPM_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            if attempts < NPM_RETRY_LIMIT:
                attempts += 1
                time.sleep(BACKOFF_TRANSIENT_SECONDS)
                continue
            raise RuntimeError(f"Command timed out after {NPM_TIMEOUT_SECONDS}s: {' '.join(args)}") from exc
        delay = retry_delay_seconds(result)
        if result.returncode != 0 and delay is not None and attempts < NPM_RETRY_LIMIT:
            attempts += 1
            time.sleep(delay)
            continue
        return result


def retry_delay_seconds(result: subprocess.CompletedProcess[str]) -> int | None:
    text = f"{result.stdout}\n{result.stderr}".lower()
    if "429" in text or "rate limit" in text:
        return BACKOFF_429_SECONDS
    if any(marker in text for marker in ("5xx", "500", "502", "503", "504", "timeout", "timed out")):
        return BACKOFF_TRANSIENT_SECONDS
    return None


def npm_view(package_name: str, version: str, cwd: Path) -> dict[str, Any]:
    specifier = f"{package_name}@{version}"
    payload = run_json(
        official_npm_args([
            npm_command(),
            "view",
            specifier,
            "version",
            "engines",
            "dist-tags",
            "dist",
            "repository",
            "homepage",
            "license",
            "--json",
        ]),
        cwd,
    )
    return payload if isinstance(payload, dict) else {"version": str(payload)}


def official_npm_args(args: list[str]) -> list[str]:
    return [
        *args,
        f"--registry={OFFICIAL_NPM_REGISTRY}",
        f"--@fission-ai:registry={OFFICIAL_NPM_REGISTRY}",
    ]


def safe_extract_tar(tar_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(tar_path, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if root not in (target, *target.parents):
                raise RuntimeError(f"Blocked unsafe tar member: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise RuntimeError(f"Blocked unsafe tar member type: {member.name}")
        try:
            archive.extractall(destination, filter="data")
        except TypeError:
            archive.extractall(destination)


def sync_from_npm(
    project_root: Path,
    *,
    package_name: str = PACKAGE_NAME,
    version: str = PINNED_VERSION,
    schema_name: str = SCHEMA_NAME,
    target_relative: Path = TARGET_RELATIVE,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="openspec-upstream-") as temp_dir:
        temp = Path(temp_dir)
        view = npm_view(package_name, version, temp)
        pack_payload = run_json(official_npm_args([npm_command(), "pack", f"{package_name}@{version}", "--json"]), temp)
        if not isinstance(pack_payload, list) or not pack_payload:
            raise RuntimeError("npm pack did not return package metadata.")
        package_meta = pack_payload[0]
        validate_official_npm_metadata(view, package_meta)
        tar_path = temp / str(package_meta["filename"])
        extract_dir = temp / "extract"
        safe_extract_tar(tar_path, extract_dir)
        package_dir = extract_dir / "package"
        return sync_from_package_dir(
            package_dir,
            project_root / target_relative,
            package_name=package_name,
            view_metadata=view,
            pack_metadata=package_meta,
            schema_name=schema_name,
        )


def validate_official_npm_metadata(view_metadata: dict[str, Any], pack_metadata: dict[str, Any]) -> None:
    dist = view_metadata.get("dist") if isinstance(view_metadata.get("dist"), dict) else {}
    tarball = str(dist.get("tarball") or "")
    parsed_tarball = urlparse(tarball)
    if parsed_tarball.scheme != "https" or parsed_tarball.netloc.lower() != OFFICIAL_NPM_HOST:
        raise RuntimeError("OpenSpec upstream tarball must resolve from the official npm registry.")
    for key in ("integrity", "shasum"):
        expected = str(dist.get(key) or "")
        actual = str(pack_metadata.get(key) or "")
        if not expected or not actual or actual != expected:
            raise RuntimeError(f"OpenSpec upstream npm {key} mismatch.")


def sync_from_package_dir(
    package_dir: Path,
    target_dir: Path,
    *,
    package_name: str,
    view_metadata: dict[str, Any],
    pack_metadata: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".openspec-upstream-stage-", dir=str(target_dir.parent)) as temp_dir:
        staged_dir = Path(temp_dir) / "snapshot"
        build_snapshot_from_package_dir(
            package_dir,
            staged_dir,
            package_name=package_name,
            view_metadata=view_metadata,
            pack_metadata=pack_metadata,
            schema_name=schema_name,
        )
        staged_result = verify_target(staged_dir)
        if not staged_result.get("ok"):
            staged_result["target"] = str(target_dir)
            return staged_result
        replace_target_dir(staged_dir, target_dir)
    return verify_target(target_dir)


def build_snapshot_from_package_dir(
    package_dir: Path,
    target_dir: Path,
    *,
    package_name: str,
    view_metadata: dict[str, Any],
    pack_metadata: dict[str, Any],
    schema_name: str,
) -> None:
    reset_target_dir(target_dir)
    files: list[dict[str, str]] = []
    for source_name in UPSTREAM_FILES:
        source = package_dir / source_name
        if not source.exists():
            raise FileNotFoundError(f"Required OpenSpec upstream file missing: {source_name}")
        destination = target_dir / source_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_text_snapshot(source, destination)
        files.append(file_record(destination, target_dir, source_name))

    notice = target_dir / "NOTICE.md"
    notice.write_text(notice_text(package_name, view_metadata), encoding="utf-8", newline="\n")
    files.append(file_record(notice, target_dir, "NOTICE.md"))

    package_json = json.loads((target_dir / "package.json").read_text(encoding="utf-8"))
    manifest = {
        "version": 1,
        "package": package_name,
        "resolved_version": str(view_metadata.get("version") or package_json.get("version")),
        "schema": schema_name,
        "node_engine": str((view_metadata.get("engines") or {}).get("node") or ""),
        "repository": view_metadata.get("repository") or package_json.get("repository") or {},
        "homepage": str(view_metadata.get("homepage") or package_json.get("homepage") or ""),
        "license": str(view_metadata.get("license") or package_json.get("license") or ""),
        "integrity": str(pack_metadata.get("integrity") or ""),
        "shasum": str(pack_metadata.get("shasum") or ""),
        "dist_tags": view_metadata.get("dist-tags") or {},
        "telemetry_policy": {
            "OPENSPEC_TELEMETRY": "0",
            "DO_NOT_TRACK": "1",
        },
        "source_policy": "official_npm_package_snapshot",
        "update_command": (
            f"codex openspec upstream sync --version "
            f"{view_metadata.get('version') or package_json.get('version')}"
        ),
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    manifest_path = target_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def replace_target_dir(staged_dir: Path, target_dir: Path) -> None:
    backup_parent = Path(tempfile.mkdtemp(prefix=".openspec-upstream-backup-", dir=str(target_dir.parent)))
    backup_dir = backup_parent / "snapshot"
    try:
        if target_dir.exists() or target_dir.is_symlink():
            shutil.move(str(target_dir), str(backup_dir))
        shutil.move(str(staged_dir), str(target_dir))
    except Exception:
        if not (target_dir.exists() or target_dir.is_symlink()) and backup_dir.exists():
            shutil.move(str(backup_dir), str(target_dir))
        raise
    finally:
        if backup_parent.exists():
            shutil.rmtree(backup_parent, ignore_errors=True)


def reset_target_dir(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in target_dir.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def notice_text(package_name: str, view_metadata: dict[str, Any]) -> str:
    version = view_metadata.get("version") or "unknown"
    repository = view_metadata.get("repository") or {}
    repo_url = repository.get("url") if isinstance(repository, dict) else repository
    return (
        "# OpenSpec Upstream Snapshot\n\n"
        f"This directory contains selected files copied from `{package_name}@{version}`.\n"
        "They are kept as pinned upstream reference material for Harness adapters.\n"
        "Do not edit these files for Harness behavior; update them through the sync command.\n\n"
        f"- Source: {repo_url or 'npm package metadata'}\n"
        "- Local behavior belongs in Harness adapters, not in this upstream snapshot.\n"
    )


def copy_text_snapshot(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8")
    destination.write_text(normalize_text_snapshot(text), encoding="utf-8", newline="\n")


def normalize_text_snapshot(text: str) -> str:
    return text.rstrip() + "\n"


def file_record(path: Path, root: Path, source_name: str) -> dict[str, str]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "source": source_name,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
