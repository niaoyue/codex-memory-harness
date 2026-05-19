from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

import sensitive_scan


RUNTIME_PREFIXES = (".codex/memories", ".codex/harness/tasks", ".codex/harness/review", "dist")
RUNTIME_NAMES = {"memory.db", "events.jsonl"}
GENERATED_SUFFIXES = (".pyc",)
REVIEW_MODES = {"uncommitted", "staged", "working"}
REVIEW_METADATA_PATHS = {
    ".codex/harness/review/preflight.json",
    ".codex/harness/review/review-ledger.jsonl",
    ".codex/harness/review/findings.jsonl",
}


def review_inputs(project_root: Path, *, mode: str = "uncommitted") -> dict[str, Any]:
    if mode not in REVIEW_MODES:
        raise ValueError(f"Unsupported review mode: {mode}")
    head = git_text(project_root, ["rev-parse", "HEAD"], check=False).strip()
    status_rows = porcelain_status(project_root)
    status_text = status_snapshot_from_rows(status_rows, mode=mode)
    working = git_bytes(project_root, ["diff", "--binary", "--full-index"]) if mode in {"uncommitted", "working"} else b""
    cached = git_bytes(project_root, ["diff", "--cached", "--binary", "--full-index"]) if mode in {"uncommitted", "staged"} else b""
    untracked_paths = untracked_files(project_root) if mode in {"uncommitted", "working"} else []
    untracked = untracked_snapshot(project_root, untracked_paths) if mode in {"uncommitted", "working"} else b""
    changed = changed_files(project_root, mode, status_rows=status_rows)
    return {
        "mode": mode,
        "head": head,
        "status_rows": status_rows,
        "status_text": status_text,
        "working": working,
        "cached": cached,
        "untracked_paths": untracked_paths,
        "untracked": untracked,
        "changed_files": changed,
    }


def diff_fingerprint(project_root: Path, *, mode: str = "uncommitted", inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    data = inputs or review_inputs(project_root, mode=mode)
    mode = str(data["mode"])
    head = str(data["head"])
    status_text = str(data["status_text"])
    working = _bytes_value(data["working"])
    cached = _bytes_value(data["cached"])
    untracked = _bytes_value(data["untracked"])
    digest = hashlib.sha256()
    for label, value in (("head", head.encode()), ("status", status_text.encode()), ("working", working), ("cached", cached), ("untracked", untracked)):
        digest.update(label.encode() + b"\0" + value + b"\0")
    return {
        "algorithm": "sha256",
        "fingerprint": f"sha256:{digest.hexdigest()}",
        "mode": mode,
        "head": head,
        "status_sha256": hashlib.sha256(status_text.encode()).hexdigest(),
        "working_diff_sha256": hashlib.sha256(working).hexdigest(),
        "cached_diff_sha256": hashlib.sha256(cached).hexdigest(),
        "untracked_sha256": hashlib.sha256(untracked).hexdigest(),
        "changed_files": list(data["changed_files"]),
    }


def diff_check(project_root: Path, mode: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if mode in {"uncommitted", "working"}:
        checks.append(_diff_check_once(project_root, "working", ["diff", "--check"]))
    if mode in {"uncommitted", "staged"}:
        checks.append(_diff_check_once(project_root, "cached", ["diff", "--cached", "--check"]))
    ok = all(item["ok"] for item in checks)
    return {
        "name": "git_diff_check",
        "ok": ok,
        "mode": mode,
        "checks": checks,
        "stdout_tail": tail("\n".join(item["stdout_tail"] for item in checks)),
        "stderr_tail": tail("\n".join(item["stderr_tail"] for item in checks)),
    }


def _diff_check_once(project_root: Path, name: str, args: list[str]) -> dict[str, Any]:
    completed = run_git(project_root, args)
    return {
        "name": name,
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout_tail": tail(completed.stdout),
        "stderr_tail": tail(completed.stderr),
    }


def sensitive_check(project_root: Path, mode: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    diff_text = sensitive_review_text(project_root, mode, inputs=inputs)
    result = sensitive_scan.sanitize_for_persistence(diff_text)
    return {
        "name": "sensitive_scan",
        "ok": not result.blocked and not result.findings,
        "report": result.report(),
    }


def package_boundary_check(project_root: Path, mode: str, files: list[str] | None = None) -> dict[str, Any]:
    files = files if files is not None else changed_files(project_root, mode)
    blocked = []
    for path in files:
        normalized = path.replace("\\", "/").strip("/")
        name = normalized.rsplit("/", 1)[-1]
        if is_runtime_prefix_path(normalized) or name in RUNTIME_NAMES or normalized.endswith(GENERATED_SUFFIXES):
            blocked.append(path)
    return {"name": "package_boundary", "ok": not blocked, "blocked_paths": blocked}


def verification_summary(project_root: Path) -> dict[str, Any]:
    profile = project_root / ".codex" / "harness" / "project_profile.json"
    commands = project_root / ".codex" / "harness" / "commands.json"
    return {
        "name": "verification_config",
        "ok": profile.exists() and commands.exists(),
        "project_profile_exists": profile.exists(),
        "commands_exists": commands.exists(),
        "recommendation": "run configured verification before final xhigh review",
    }


def slice_plan(project_root: Path, *, mode: str, files: list[str] | None = None) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = {}
    for path in files if files is not None else changed_files(project_root, mode):
        groups.setdefault(slice_kind(path), []).append(path)
    order = ["runtime", "tests", "docs", "templates", "install_packaging", "generated_or_deleted", "other"]
    return [
        {"slice_id": f"slice-{kind}", "kind": kind, "paths": sorted(groups[kind]), "risk": slice_risk(kind)}
        for kind in order
        if groups.get(kind)
    ]


def changed_files(project_root: Path, mode: str, *, status_rows: list[tuple[str, str]] | None = None) -> list[str]:
    args = ["diff", "--name-only"]
    if mode == "staged":
        args.insert(1, "--cached")
    files = git_text(project_root, args, check=False).splitlines()
    status_files = []
    rows = porcelain_status(project_root) if status_rows is None else status_rows
    if mode == "uncommitted":
        status_files = [path for _, path in rows]
    elif mode == "working":
        status_files = [path for code, path in rows if is_working_status(code)]
    return sorted({item for item in normalize_review_paths(files + status_files) if not is_review_metadata_path(item)})


def review_diff_text(project_root: Path, mode: str, inputs: dict[str, Any] | None = None) -> str:
    if inputs is not None:
        parts = []
        if mode in {"uncommitted", "working"}:
            parts.append(_bytes_value(inputs["working"]).decode("utf-8", errors="replace"))
        if mode in {"uncommitted", "staged"}:
            parts.append(_bytes_value(inputs["cached"]).decode("utf-8", errors="replace"))
        if mode in {"uncommitted", "working"}:
            parts.append(_bytes_value(inputs["untracked"]).decode("utf-8", errors="replace"))
        return "\n".join(parts)
    parts = []
    if mode in {"uncommitted", "working"}:
        parts.append(git_text(project_root, ["diff", "--binary", "--full-index"], check=False))
    if mode in {"uncommitted", "staged"}:
        parts.append(git_text(project_root, ["diff", "--cached", "--binary", "--full-index"], check=False))
    if mode in {"uncommitted", "working"}:
        parts.append(untracked_snapshot(project_root).decode("utf-8", errors="replace"))
    return "\n".join(parts)


def sensitive_review_text(project_root: Path, mode: str, inputs: dict[str, Any] | None = None) -> str:
    parts = [review_diff_text(project_root, mode, inputs=inputs)]
    if mode in {"uncommitted", "working"}:
        paths = list(inputs["untracked_paths"]) if inputs is not None else None
        parts.append(untracked_full_text(project_root, paths))
    return "\n".join(parts)


def untracked_snapshot(project_root: Path, paths: list[str] | None = None) -> bytes:
    paths = untracked_files(project_root) if paths is None else paths
    chunks: list[bytes] = []
    for relative in paths:
        path = project_root / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            data = f"<unreadable:{exc}>".encode("utf-8", errors="replace")
        header = (
            f"\n--- untracked file: {relative}\n"
            f"sha256: {hashlib.sha256(data).hexdigest()}\n"
            f"size: {len(data)}\n"
        ).encode("utf-8")
        chunks.append(header + data[:262144] + b"\n")
        if len(data) > 262144:
            chunks.append(b"\n[untracked file content truncated after 262144 bytes]\n")
    return b"".join(chunks)


def untracked_full_text(project_root: Path, paths: list[str] | None = None) -> str:
    chunks: list[str] = []
    for relative in untracked_files(project_root) if paths is None else paths:
        path = project_root / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            chunks.append(f"\n--- untracked file full scan: {relative}\n<unreadable:{exc}>\n")
            continue
        chunks.append(
            f"\n--- untracked file full scan: {relative}\n"
            + data.decode("utf-8", errors="replace")
            + "\n"
        )
    return "".join(chunks)


def untracked_files(project_root: Path) -> list[str]:
    output = git_text(project_root, ["ls-files", "--others", "--exclude-standard"], check=False)
    return sorted(item for item in normalize_review_paths(output.splitlines()) if not is_review_metadata_path(item))


def status_snapshot(project_root: Path, *, mode: str) -> str:
    return status_snapshot_from_rows(porcelain_status(project_root), mode=mode)


def status_snapshot_from_rows(rows: list[tuple[str, str]], *, mode: str) -> str:
    if mode == "staged":
        return ""
    selected = []
    for code, path in rows:
        if mode == "working" and not is_working_status(code):
            continue
        if is_review_metadata_path(path):
            continue
        selected.append(f"{code} {path}")
    return "\n".join(selected) + ("\n" if selected else "")


def porcelain_status(project_root: Path) -> list[tuple[str, str]]:
    rows = []
    for line in git_text(project_root, ["status", "--porcelain=v1", "--untracked-files=all"], check=False).splitlines():
        if len(line) < 4:
            continue
        rows.append((line[:2], normalize_review_path(line[3:].strip())))
    return rows


def is_working_status(code: str) -> bool:
    return code == "??" or (len(code) > 1 and code[1] != " ")


def normalize_review_paths(paths: list[str]) -> list[str]:
    return [normalize_review_path(item) for item in paths if item.strip()]


def normalize_review_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if " -> " in normalized:
        normalized = normalized.rsplit(" -> ", 1)[-1]
    return normalized


def is_review_metadata_path(path: str) -> bool:
    return normalize_review_path(path).strip("/") in REVIEW_METADATA_PATHS


def is_runtime_prefix_path(path: str) -> bool:
    normalized = normalize_review_path(path).strip("/")
    return any(normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in RUNTIME_PREFIXES)


def slice_kind(path: str) -> str:
    lowered = path.lower()
    if lowered.startswith("tests/") or "/test_" in lowered:
        return "tests"
    if lowered.startswith("docs/") or lowered.endswith(".md"):
        return "docs"
    if lowered.startswith("templates/") or "/templates/" in lowered:
        return "templates"
    if lowered.startswith(("install", "scripts/build", "scripts/verify", "plugins/codex-memory/scripts/install")):
        return "install_packaging"
    if lowered.endswith((".pyc", ".lscache")) or lowered.startswith("dist/"):
        return "generated_or_deleted"
    if lowered.startswith("plugins/") or lowered.startswith("scripts/") or lowered.startswith("schemas/"):
        return "runtime"
    return "other"


def slice_risk(kind: str) -> str:
    return {"runtime": "high", "install_packaging": "high", "templates": "medium", "tests": "medium", "docs": "low"}.get(kind, "medium")


def git_bytes(project_root: Path, args: list[str]) -> bytes:
    return subprocess.run(["git", *args], cwd=project_root, capture_output=True, check=False).stdout


def git_text(project_root: Path, args: list[str], *, check: bool = True) -> str:
    completed = run_git(project_root, args)
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def run_git(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def tail(text: str, limit: int = 2000) -> str:
    return text[-limit:]


def _bytes_value(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)
