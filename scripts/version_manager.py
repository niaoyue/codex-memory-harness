from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_RELATIVE = Path("pyproject.toml")
PLUGIN_MANIFEST_RELATIVE = Path("plugins/codex-memory/.codex-plugin/plugin.json")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class VersionError(RuntimeError):
    pass


def current_version(project_root: Path = PROJECT_ROOT) -> str:
    status = version_status(project_root)
    if not status["ok"]:
        raise VersionError("; ".join(status["errors"]))
    return str(status["version"])


def version_status(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    sources = read_versions(project_root)
    versions = {str(value) for value in sources.values()}
    errors: list[str] = []
    if len(versions) != 1:
        errors.append(
            "version mismatch: "
            + ", ".join(f"{name}={version}" for name, version in sorted(sources.items()))
        )
    version = next(iter(versions)) if len(versions) == 1 else ""
    if version and not SEMVER_RE.fullmatch(version):
        errors.append("version must be semantic major.minor.patch")
    return {
        "ok": not errors,
        "version": version,
        "sources": sources,
        "errors": errors,
    }


def read_versions(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    return {
        "pyproject": read_pyproject_version(project_root / PYPROJECT_RELATIVE),
        "plugin_manifest": read_plugin_version(project_root / PLUGIN_MANIFEST_RELATIVE),
    }


def read_pyproject_version(path: Path) -> str:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise VersionError(f"missing [project].version in {path}")
    return version


def read_plugin_version(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise VersionError(f"missing plugin version in {path}")
    return version


def set_version(project_root: Path, version: str, *, dry_run: bool = False) -> dict[str, object]:
    validate_version(version)
    before = read_versions(project_root)
    if not dry_run:
        update_pyproject_version(project_root / PYPROJECT_RELATIVE, version)
        update_plugin_version(project_root / PLUGIN_MANIFEST_RELATIVE, version)
    after = {name: version for name in before}
    return {
        "ok": True,
        "dry_run": dry_run,
        "version": version,
        "before": before,
        "after": after,
        "changed": any(value != version for value in before.values()),
    }


def bump_version(project_root: Path, part: str, *, dry_run: bool = False) -> dict[str, object]:
    version = current_version(project_root)
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise VersionError(f"cannot bump non-semver version: {version}")
    major, minor, patch = (int(item) for item in match.groups())
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    elif part == "patch":
        patch += 1
    else:
        raise VersionError(f"unknown bump part: {part}")
    return set_version(project_root, f"{major}.{minor}.{patch}", dry_run=dry_run)


def update_pyproject_version(path: Path, version: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(replace_project_version(text, version), encoding="utf-8")


def replace_project_version(text: str, version: str) -> str:
    lines = text.splitlines(keepends=True)
    in_project = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("[") and stripped.endswith("]"):
            break
        if in_project and re.match(r"^version\s*=", stripped):
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f'version = "{version}"{newline}'
            return "".join(lines)
    raise VersionError("missing [project].version line in pyproject.toml")


def update_plugin_version(path: Path, version: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VersionError(f"plugin manifest must be an object: {path}")
    payload["version"] = version
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_version(version: str) -> None:
    if not SEMVER_RE.fullmatch(version):
        raise VersionError("version must be semantic major.minor.patch, for example 0.1.2")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Codex Memory Harness package versions.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("show", help="Print the current version sources.")
    subparsers.add_parser("check", help="Verify version sources match.")

    set_parser = subparsers.add_parser("set", help="Set all package version sources.")
    set_parser.add_argument("version")
    set_parser.add_argument("--dry-run", action="store_true")

    bump_parser = subparsers.add_parser("bump", help="Bump the semantic version.")
    bump_parser.add_argument("part", choices=["major", "minor", "patch"])
    bump_parser.add_argument("--dry-run", action="store_true")
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, object]:
    project_root = Path(args.project_root)
    command = args.command or "show"
    if command == "show":
        return version_status(project_root)
    if command == "check":
        return version_status(project_root)
    if command == "set":
        return set_version(project_root, args.version, dry_run=args.dry_run)
    if command == "bump":
        return bump_version(project_root, args.part, dry_run=args.dry_run)
    raise VersionError(f"unknown command: {command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = dispatch(args)
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError, VersionError) as exc:
        result: dict[str, Any] = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") or args.command in (None, "show") else 1


if __name__ == "__main__":
    raise SystemExit(main())
