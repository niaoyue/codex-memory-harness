from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PACKAGE_NAME = "@fission-ai/openspec"
PINNED_VERSION = "1.3.1"
SCHEMA_NAME = "spec-driven"
TARGET_RELATIVE = Path("openspec") / "upstream" / "openspec"
MANIFEST_NAME = "manifest.json"
UPSTREAM_FILES = (
    "LICENSE",
    "README.md",
    "package.json",
    "schemas/spec-driven/schema.yaml",
    "schemas/spec-driven/templates/proposal.md",
    "schemas/spec-driven/templates/spec.md",
    "schemas/spec-driven/templates/design.md",
    "schemas/spec-driven/templates/tasks.md",
)


def verify_project(project_root: Path, *, target_relative: Path = TARGET_RELATIVE) -> dict[str, Any]:
    return verify_target(project_root / target_relative)


def verify_target(target_dir: Path) -> dict[str, Any]:
    manifest_path = target_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {"ok": False, "status": "missing", "manifest": str(manifest_path), "failures": ["manifest missing"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "status": "invalid", "manifest": str(manifest_path), "failures": ["manifest invalid JSON"]}
    failures: list[str] = []
    if not isinstance(manifest, dict):
        return {"ok": False, "status": "invalid", "manifest": str(manifest_path), "failures": ["manifest must be a JSON object"]}
    failures.extend(validate_manifest_metadata(manifest, target_dir))
    records = manifest.get("files", [])
    if not isinstance(records, list):
        records = []
        failures.append("manifest files must be a list")
    required_files = set(required_manifest_files())
    records_by_path: dict[str, dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, dict):
            failures.append("invalid file record")
            continue
        item_path = str(item.get("path") or "")
        if not item_path:
            failures.append("file record missing path")
            continue
        if item_path not in required_files:
            failures.append(f"unexpected file record {item_path}")
            continue
        if item_path in records_by_path:
            failures.append(f"duplicate file record {item_path}")
            continue
        records_by_path[item_path] = item
    for required in required_manifest_files():
        if required not in records_by_path:
            failures.append(f"manifest record missing {required}")
    for extra_file in unmanifested_files(target_dir, set(records_by_path)):
        failures.append(f"unmanifested file {extra_file}")
    for item_path, item in records_by_path.items():
        path = target_dir / item_path
        expected = str(item.get("sha256") or "")
        if not expected:
            failures.append(f"sha256 missing {item_path}")
            continue
        if not path.exists():
            failures.append(f"missing {item_path}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            failures.append(f"sha256 mismatch {item_path}")
    for required in required_manifest_files():
        if not (target_dir / required).exists():
            failures.append(f"required file missing {required}")
    status = "passed" if not failures else "invalid"
    return {
        "ok": not failures,
        "status": status,
        "manifest": str(manifest_path),
        "package": manifest.get("package"),
        "resolved_version": manifest.get("resolved_version"),
        "schema": manifest.get("schema"),
        "files": len(manifest.get("files", [])),
        "failures": failures,
    }


def unmanifested_files(target_dir: Path, manifest_paths: set[str]) -> list[str]:
    extras = []
    for path in target_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(target_dir).as_posix()
        if relative == MANIFEST_NAME:
            continue
        if relative not in manifest_paths:
            extras.append(relative)
    return sorted(extras)


def required_manifest_files() -> tuple[str, ...]:
    return (*UPSTREAM_FILES, "NOTICE.md")


def validate_manifest_metadata(manifest: dict[str, Any], target_dir: Path) -> list[str]:
    failures: list[str] = []
    expected = {
        "version": 1,
        "package": PACKAGE_NAME,
        "schema": SCHEMA_NAME,
        "source_policy": "official_npm_package_snapshot",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            failures.append(f"manifest {key} mismatch")
    validate_telemetry_policy(manifest, failures)
    validate_package_json_metadata(manifest, target_dir, failures)
    for key in ("resolved_version", "license", "integrity", "shasum"):
        if not str(manifest.get(key) or ""):
            failures.append(f"manifest {key} missing")
    return failures


def validate_telemetry_policy(manifest: dict[str, Any], failures: list[str]) -> None:
    telemetry = manifest.get("telemetry_policy")
    if not isinstance(telemetry, dict):
        failures.append("manifest telemetry_policy missing")
        return
    expected_telemetry = {
        "OPENSPEC_TELEMETRY": "0",
        "DO_NOT_TRACK": "1",
    }
    for key, value in expected_telemetry.items():
        if telemetry.get(key) != value:
            failures.append(f"manifest telemetry_policy {key} mismatch")


def validate_package_json_metadata(manifest: dict[str, Any], target_dir: Path, failures: list[str]) -> None:
    package_json = read_package_json(target_dir / "package.json")
    if not package_json:
        failures.append("package.json invalid")
        return
    if package_json.get("name") != PACKAGE_NAME:
        failures.append("package.json name mismatch")
    if package_json.get("version") != manifest.get("resolved_version"):
        failures.append("package.json version mismatch")
    if package_json.get("license") and manifest.get("license") != package_json.get("license"):
        failures.append("manifest license mismatch")


def read_package_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
