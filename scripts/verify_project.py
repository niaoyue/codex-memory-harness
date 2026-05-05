from __future__ import annotations

import argparse
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import build_release


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_CODE_LINES = 500
CODE_SUFFIXES = {".py", ".ps1", ".bat", ".sh"}
JSON_SUFFIXES = {".json"}
SKIPPED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "dist",
    ".codex",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def is_generated(path: Path) -> bool:
    relative_parts = path.relative_to(PROJECT_ROOT).parts
    parts = set(relative_parts)
    if parts.intersection(SKIPPED_DIR_NAMES):
        return True
    return relative_parts[:4] == ("plugins", "codex-memory", "skills", "openai-curated")


def iter_project_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(PROJECT_ROOT):
        root_path = Path(root)
        dirs[:] = sorted(
            item for item in dirs if not is_generated(root_path / item)
        )
        for name in sorted(names):
            path = root_path / name
            if not is_generated(path):
                files.append(path)
    return files


def check_code_line_counts() -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for path in iter_project_files():
        if path.suffix not in CODE_SUFFIXES:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > MAX_CODE_LINES:
            failures.append({"path": str(path), "lines": lines})
    return failures


def compile_python() -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for path in iter_project_files():
        if path.suffix != ".py":
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append({"path": str(path), "error": str(exc)})
    return failures


def validate_json() -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for path in iter_project_files():
        if path.suffix not in JSON_SUFFIXES:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append({"path": str(path), "error": str(exc)})
    return failures


def run_installer_check() -> dict[str, object]:
    installer = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts" / "install_codex_memory.py"
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", str(installer), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def check_release_package() -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as output_dir:
        package_path = build_release.build(Path(output_dir))
        with zipfile.ZipFile(package_path) as archive:
            names = archive.namelist()

    blocked_prefixes = (".codex/", "dist/")
    for name in names:
        if name.startswith(blocked_prefixes):
            failures.append({"path": name, "error": "runtime path included in release package"})
        if "__pycache__/" in name or name.endswith(".pyc"):
            failures.append({"path": name, "error": "generated Python cache included"})
        if name.endswith("memory.db") or name.endswith("events.jsonl"):
            failures.append({"path": name, "error": "memory storage file included"})
    return failures


def run_behavior_tests() -> dict[str, object]:
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        return {"ok": False, "exit_code": 1, "stdout": "", "stderr": "tests directory is missing"}
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", str(tests_dir)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-3000:],
        "stderr": completed.stderr[-3000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Codex Memory Harness project health.")
    parser.add_argument("--skip-installer-check", action="store_true")
    parser.add_argument("--skip-behavior-tests", action="store_true")
    args = parser.parse_args()

    result = {
        "line_count_failures": check_code_line_counts(),
        "compile_failures": compile_python(),
        "json_failures": validate_json(),
        "release_package_failures": check_release_package(),
        "behavior_tests": None if args.skip_behavior_tests else run_behavior_tests(),
        "installer_check": None if args.skip_installer_check else run_installer_check(),
    }
    ok = (
        not result["line_count_failures"]
        and not result["compile_failures"]
        and not result["json_failures"]
        and not result["release_package_failures"]
        and (args.skip_behavior_tests or result["behavior_tests"]["ok"])
        and (args.skip_installer_check or result["installer_check"]["ok"])
    )
    result["ok"] = ok
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
