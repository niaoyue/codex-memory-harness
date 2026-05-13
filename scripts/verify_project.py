from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import build_release


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_CODE_LINES = 500
BEHAVIOR_TEST_TIMEOUT_SECONDS = 360
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
    return relative_parts[:3] == ("plugins", "codex-memory", "skills")


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
        lines = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        if lines > MAX_CODE_LINES:
            failures.append({"path": str(path), "lines": lines})
    return failures


def compile_python() -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for path in iter_project_files():
        if path.suffix != ".py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec", dont_inherit=True)
        except (OSError, SyntaxError, ValueError) as exc:
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


def run_installer_smoke_test() -> dict[str, object]:
    if os.name != "nt":
        return {
            "ok": True,
            "skipped": True,
            "reason": "install.bat smoke test is Windows-only.",
        }

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        package_path = build_release.build(temp_root / "dist")
        package_root = temp_root / "package"
        with zipfile.ZipFile(package_path) as archive:
            archive.extractall(package_root)

        home = temp_root / "home"
        codex_home = temp_root / "codex-home"
        home.mkdir()
        codex_home.mkdir()

        env = os.environ.copy()
        env.update(
            {
                "CODEX_MEMORY_HOME": str(home),
                "CODEX_HOME": str(codex_home),
                "USERPROFILE": str(home),
                "HOME": str(home),
                "CODEX_MEMORY_AUTO_INSTALL_PYTHON": "0",
            }
        )
        completed = subprocess.run(
            ["cmd", "/c", "install.bat", "--mode", "copy"],
            cwd=package_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

        payload: dict[str, object] = {}
        failures: list[str] = []
        parse_error = ""
        if completed.returncode == 0:
            try:
                parsed = json.loads(completed.stdout)
                if isinstance(parsed, dict):
                    payload = parsed
                else:
                    parse_error = "installer output is not a JSON object"
            except json.JSONDecodeError as exc:
                parse_error = str(exc)

        def expect(condition: bool, message: str) -> None:
            if not condition:
                failures.append(message)

        expect(completed.returncode == 0, "install.bat returned a non-zero exit code")
        expect(not parse_error, f"install.bat stdout was not valid JSON: {parse_error}")
        expect((home / "plugins" / "codex-memory" / ".mcp.json").exists(), "home plugin copy is missing")
        expect((home / ".agents" / "plugins" / "marketplace.json").exists(), "home marketplace is missing")
        profile_path = home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
        profile_text = profile_path.read_text(encoding="utf-8", errors="replace") if profile_path.exists() else ""
        expect("codex-memory codexm launcher" in profile_text, "PowerShell profile launcher block is missing")
        expect((codex_home / "config.toml").exists(), "CODEX_HOME config.toml is missing")
        expect((codex_home / "AGENTS.md").exists(), "CODEX_HOME AGENTS.md is missing")
        expect(
            (home / ".agents" / "skills" / "harness-release-gate" / "SKILL.md").exists(),
            "bundled harness-release-gate skill is missing",
        )
        expect(
            (package_root / ".agents" / "plugins" / "marketplace.json").exists(),
            "package repo marketplace is missing",
        )

        bundled = payload.get("bundled_skills") if isinstance(payload, dict) else None
        if isinstance(bundled, dict):
            manifest_path = package_root / "plugins" / "codex-memory" / "skills" / "bundled-skills.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_skill_count = len(manifest.get("skills", []))
            expect(
                bundled.get("installed") == expected_skill_count,
                f"fresh install did not install all {expected_skill_count} bundled skills",
            )
            expected_skills_root = home / ".agents" / "skills"
            actual_skills_root = Path(str(bundled.get("target_root", "")))
            expect(
                actual_skills_root.resolve() == expected_skills_root.resolve(),
                "skills target_root is outside temp home",
            )

        return {
            "ok": not failures,
            "skipped": False,
            "exit_code": completed.returncode,
            "failures": failures,
            "stdout": completed.stdout[-3000:],
            "stderr": completed.stderr[-3000:],
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


def run_behavior_tests(timeout_seconds: int = BEHAVIOR_TEST_TIMEOUT_SECONDS) -> dict[str, object]:
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        return {"ok": False, "exit_code": 1, "stdout": "", "stderr": "tests directory is missing"}
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_root = Path(temp_dir) / "behavior-memory"
        memory_root.mkdir()
        env = os.environ.copy()
        env.update(
            {
                "CODEX_MEMORY_SCOPE": "project",
                "CODEX_MEMORY_CWD": str(memory_root),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        try:
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", str(tests_dir)],
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return {
                "ok": False,
                "exit_code": 124,
                "stdout": stdout[-3000:],
                "stderr": (stderr + f"\nBehavior tests timed out after {timeout_seconds}s.")[-3000:],
            }
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-3000:],
        "stderr": completed.stderr[-3000:],
    }


def run_grounded_docs_check() -> dict[str, object]:
    script = PROJECT_ROOT / "scripts" / "verify_grounded_docs.py"
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(script),
            "--required",
            "docs/LLM_AGENT_MEMORY_HANDBOOK.md",
            "--required",
            "docs/GROUNDED_FACT_WORKFLOW.md",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
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
    parser.add_argument("--skip-installer-smoke", action="store_true")
    parser.add_argument("--skip-behavior-tests", action="store_true")
    args = parser.parse_args()

    result = {
        "line_count_failures": check_code_line_counts(),
        "compile_failures": compile_python(),
        "json_failures": validate_json(),
        "release_package_failures": check_release_package(),
        "grounded_docs": run_grounded_docs_check(),
        "behavior_tests": None if args.skip_behavior_tests else run_behavior_tests(),
        "installer_check": None if args.skip_installer_check else run_installer_check(),
        "installer_smoke": None if args.skip_installer_smoke else run_installer_smoke_test(),
    }
    ok = (
        not result["line_count_failures"]
        and not result["compile_failures"]
        and not result["json_failures"]
        and not result["release_package_failures"]
        and result["grounded_docs"]["ok"]
        and (args.skip_behavior_tests or result["behavior_tests"]["ok"])
        and (args.skip_installer_check or result["installer_check"]["ok"])
        and (args.skip_installer_smoke or result["installer_smoke"]["ok"])
    )
    result["ok"] = ok
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
