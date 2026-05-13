from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EVAL_DIR = ".codex/evals"
CASE_VERSION = 1
HIGH_VALUE_THRESHOLD = 0.8
CASE_ID_MAX_CHARS = 80
FAILURE_STATUSES = {"fail", "failed", "failure", "error", "blocked", "timeout"}
HIGH_VALUE_SEVERITIES = {"high", "critical", "blocker"}
DANGEROUS_PATTERNS = (
    "rm -rf",
    "git reset --hard",
    "git clean",
    "remove-item -recurse",
    "remove-item -force -recurse",
    "format ",
    "shutdown ",
)
NETWORK_PATTERNS = (
    "curl ",
    "wget ",
    "ssh ",
    "scp ",
    "ftp ",
    "sftp ",
    "invoke-webrequest",
    "invoke-restmethod",
    "http://",
    "https://",
)
DEFAULT_EXPECTED_FIELDS = ("status", "ok", "exit_code")
LOGGER = logging.getLogger("eval_replay")


@dataclass
class ReplayCheck:
    name: str
    ok: bool
    reason: str = ""


@dataclass
class ReplayResult:
    case_id: str
    ok: bool
    checks: list[ReplayCheck] = field(default_factory=list)


def project_root(value: str | None) -> Path:
    return Path(value or os.environ.get("CODEX_MEMORY_CWD") or Path.cwd()).resolve()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evals_dir(root: Path) -> Path:
    return root / EVAL_DIR


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _field_value(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _has_field(payload: dict[str, Any], dotted_path: str) -> bool:
    missing = object()
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current.get(part, missing)
        if current is missing:
            return False
    return True


def _truthy_failure(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in FAILURE_STATUSES
    return False


def classify_artifact(artifact: dict[str, Any]) -> str | None:
    status = _field_value(artifact, "status") or _field_value(artifact, "result.status")
    if _truthy_failure(status) or _truthy_failure(_field_value(artifact, "ok")):
        return "failure"
    if _truthy_failure(_field_value(artifact, "exit_code")):
        return "failure"

    if bool(artifact.get("high_value")):
        return "high_value"
    tags = {item.lower() for item in _string_list(artifact.get("tags"))}
    severity = str(artifact.get("severity") or "").strip().lower()
    score = artifact.get("value_score", artifact.get("score"))
    try:
        is_high_score = float(score) >= HIGH_VALUE_THRESHOLD
    except (TypeError, ValueError):
        is_high_score = False
    if "high_value" in tags or severity in HIGH_VALUE_SEVERITIES or is_high_score:
        return "high_value"
    return None


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return cleaned[:CASE_ID_MAX_CHARS] or "artifact"


def derive_case_id(artifact: dict[str, Any], source_path: Path, explicit: str | None = None) -> str:
    if explicit:
        return _slug(explicit)
    seed = str(artifact.get("artifact_id") or artifact.get("id") or artifact.get("name") or source_path.stem)
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()[:10]
    return f"{_slug(seed)}-{digest}"


def _relative_to_root(root: Path, path_value: str) -> str:
    path = Path(path_value)
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {path_value}") from exc


def _command_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    raw_command = artifact.get("command")
    nested_command = raw_command if isinstance(raw_command, dict) else {}
    argv = _string_list(artifact.get("argv") or nested_command.get("argv"))
    command_value = raw_command if isinstance(raw_command, str) else nested_command.get("command")
    command = str(command_value or "").strip()
    payload: dict[str, Any] = {}
    if argv:
        payload["argv"] = argv
    if command:
        payload["command"] = command
    return payload


def _expected_fields(artifact: dict[str, Any], requested: list[str]) -> list[str]:
    fields = requested or _string_list(artifact.get("expected_fields"))
    if fields:
        return sorted(dict.fromkeys(fields))
    defaults = [field_name for field_name in DEFAULT_EXPECTED_FIELDS if _has_field(artifact, field_name)]
    return defaults or ["status"]


def create_testcase(
    project_root_path: Path,
    artifact_path: Path,
    *,
    case_id: str | None = None,
    expected_fields: list[str] | None = None,
    fixtures: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    artifact = load_json(artifact_path)
    classification = classify_artifact(artifact)
    if classification is None and not force:
        raise ValueError("Artifact is neither failed nor high value; pass --force to create a replay case.")

    root = project_root_path.resolve()
    normalized_fixtures = [
        _relative_to_root(root, item)
        for item in [*_string_list(artifact.get("fixtures")), *(fixtures or [])]
    ]
    source = _relative_to_root(root, str(artifact_path))
    testcase = {
        "version": CASE_VERSION,
        "case_id": derive_case_id(artifact, artifact_path, case_id),
        "kind": classification or "forced",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_artifact": source,
        "command": _command_payload(artifact),
        "expected_fields": _expected_fields(artifact, expected_fields or []),
        "fixtures": sorted(dict.fromkeys(normalized_fixtures)),
        "artifact_snapshot": artifact,
    }
    target = evals_dir(root) / f"{testcase['case_id']}.json"
    LOGGER.debug("writing eval replay testcase case_id=%s path=%s", testcase["case_id"], target)
    write_json(target, testcase)
    return {"ok": True, "path": str(target), "testcase": testcase}


def list_testcases(project_root_path: Path) -> dict[str, Any]:
    root = project_root_path.resolve()
    cases: list[dict[str, Any]] = []
    for path in sorted(evals_dir(root).glob("*.json")):
        payload = load_json(path)
        cases.append(
            {
                "case_id": str(payload.get("case_id") or path.stem),
                "kind": str(payload.get("kind") or ""),
                "path": path.relative_to(root).as_posix(),
                "source_artifact": str(payload.get("source_artifact") or ""),
            }
        )
    LOGGER.debug("listed eval replay testcases count=%d", len(cases))
    return {"ok": True, "cases": cases}


def _command_text(command: dict[str, Any]) -> str:
    parts = [str(command.get("command") or "")]
    parts.extend(_string_list(command.get("argv")))
    return " ".join(parts).strip()


def _contains_pattern(text: str, patterns: tuple[str, ...]) -> str:
    normalized = " ".join(text.lower().split())
    return next((pattern for pattern in patterns if pattern in normalized), "")


def _safe_command_checks(command: dict[str, Any]) -> list[ReplayCheck]:
    text = _command_text(command)
    checks = [ReplayCheck("command_present", bool(text), "command or argv is required")]
    dangerous = _contains_pattern(text, DANGEROUS_PATTERNS)
    network = _contains_pattern(text, NETWORK_PATTERNS)
    checks.append(ReplayCheck("command_safe", not dangerous, f"blocked dangerous pattern: {dangerous}"))
    checks.append(ReplayCheck("no_network_command", not network, f"blocked network pattern: {network}"))
    return checks


def run_testcase(project_root_path: Path, testcase_path: Path) -> ReplayResult:
    root = project_root_path.resolve()
    testcase = load_json(testcase_path)
    checks: list[ReplayCheck] = [
        ReplayCheck("schema_version", testcase.get("version") == CASE_VERSION, "unsupported testcase version"),
    ]
    command = testcase.get("command") if isinstance(testcase.get("command"), dict) else {}
    checks.extend(_safe_command_checks(command))

    snapshot = testcase.get("artifact_snapshot") if isinstance(testcase.get("artifact_snapshot"), dict) else {}
    missing_fields = [field_name for field_name in _string_list(testcase.get("expected_fields")) if not _has_field(snapshot, field_name)]
    checks.append(
        ReplayCheck(
            "expected_fields_present",
            not missing_fields,
            "missing fields: " + ", ".join(missing_fields),
        )
    )

    missing_fixtures = [item for item in _string_list(testcase.get("fixtures")) if not (root / item).exists()]
    checks.append(ReplayCheck("fixtures_exist", not missing_fixtures, "missing fixtures: " + ", ".join(missing_fixtures)))
    ok = all(check.ok for check in checks)
    case_id = str(testcase.get("case_id") or testcase_path.stem)
    LOGGER.debug("ran eval replay testcase case_id=%s ok=%s checks=%d", case_id, ok, len(checks))
    return ReplayResult(case_id=case_id, ok=ok, checks=checks)


def run_testcases(project_root_path: Path, case_id: str | None = None) -> dict[str, Any]:
    root = project_root_path.resolve()
    paths = [evals_dir(root) / f"{case_id}.json"] if case_id else sorted(evals_dir(root).glob("*.json"))
    results = [run_testcase(root, path) for path in paths if path.exists()]
    return {
        "ok": bool(results) and all(result.ok for result in results),
        "results": [
            {
                "case_id": result.case_id,
                "ok": result.ok,
                "checks": [check.__dict__ for check in result.checks],
            }
            for result in results
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and run deterministic Codex eval replay testcases.")
    parser.add_argument("--project-root", help="Project root that owns .codex/evals.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a replay testcase from a failed or high-value artifact.")
    create.add_argument("--artifact", required=True, help="Path to artifact JSON.")
    create.add_argument("--case-id", help="Stable testcase id.")
    create.add_argument("--expected-field", dest="expected_fields", action="append", default=[])
    create.add_argument("--fixture", dest="fixtures", action="append", default=[])
    create.add_argument("--force", action="store_true", help="Create a testcase even when the artifact is not classified.")

    subparsers.add_parser("list", help="List replay testcases.")
    run = subparsers.add_parser("run", help="Run deterministic no-network replay checks.")
    run.add_argument("--case-id", help="Run a single testcase id.")
    return parser


def main() -> int:
    logging.basicConfig(level=os.environ.get("CODEX_EVAL_REPLAY_LOG_LEVEL", "WARNING"))
    parser = build_parser()
    args = parser.parse_args()
    root = project_root(args.project_root)
    if args.command == "create":
        result = create_testcase(
            root,
            Path(args.artifact).resolve(),
            case_id=args.case_id,
            expected_fields=args.expected_fields,
            fixtures=args.fixtures,
            force=args.force,
        )
    elif args.command == "list":
        result = list_testcases(root)
    elif args.command == "run":
        result = run_testcases(root, args.case_id)
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
