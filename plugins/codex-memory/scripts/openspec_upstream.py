from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import openspec_upstream_sync as _sync
from openspec_upstream_manifest import (
    MANIFEST_NAME,
    PACKAGE_NAME,
    PINNED_VERSION,
    SCHEMA_NAME,
    TARGET_RELATIVE,
    UPSTREAM_FILES,
    read_package_json,
    required_manifest_files,
    unmanifested_files,
    validate_manifest_metadata,
    verify_project,
    verify_target,
)
from openspec_upstream_sync import (
    BACKOFF_429_SECONDS,
    BACKOFF_TRANSIENT_SECONDS,
    NPM_RETRY_LIMIT,
    NPM_TIMEOUT_SECONDS,
    OFFICIAL_NPM_HOST,
    OFFICIAL_NPM_REGISTRY,
    build_snapshot_from_package_dir,
    copy_text_snapshot,
    file_record,
    normalize_text_snapshot,
    notice_text,
    npm_command,
    npm_view,
    official_npm_args,
    replace_target_dir,
    reset_target_dir,
    retry_delay_seconds,
    run_external,
    run_json,
    safe_extract_tar,
    sync_from_npm,
    sync_from_package_dir,
    telemetry_safe_env,
    validate_official_npm_metadata,
)


# Compatibility aliases for tests and callers that patched the old single-file module.
subprocess = _sync.subprocess
time = _sync.time


def status(project_root: Path) -> dict[str, Any]:
    target = project_root / TARGET_RELATIVE
    result = verify_target(target)
    result["target"] = str(target)
    result["default_package"] = PACKAGE_NAME
    result["pinned_version"] = PINNED_VERSION
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync and verify pinned OpenSpec upstream assets.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync")
    sync.add_argument("--package", default=PACKAGE_NAME)
    sync.add_argument("--version", default=PINNED_VERSION)
    sync.add_argument("--schema", default=SCHEMA_NAME)
    sub.add_parser("verify")
    sub.add_parser("status")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    try:
        if args.command == "sync":
            result = sync_from_npm(
                project_root,
                package_name=args.package,
                version=args.version,
                schema_name=args.schema,
            )
        elif args.command == "verify":
            result = verify_project(project_root)
        else:
            result = status(project_root)
    except Exception as exc:
        result = {"ok": False, "status": "error", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
