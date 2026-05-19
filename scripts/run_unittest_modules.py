from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS_DIR = PROJECT_ROOT / "tests"
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEFAULT_JOBS = min(4, max(1, os.cpu_count() or 1))
OUTPUT_TAIL_CHARS = 3000


def discover_modules(start_dir: Path, pattern: str) -> list[str]:
    modules: list[str] = []
    for path in sorted(start_dir.rglob(pattern)):
        if not path.is_file() or path.name == "__init__.py" or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(start_dir).with_suffix("")
        modules.append(".".join(relative.parts))
    return modules


def child_env(memory_root: Path, start_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CODEX_MEMORY_SCOPE": "project",
            "CODEX_MEMORY_CWD": str(memory_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    path_entries = [
        str(SCRIPTS_DIR),
        str(PLUGIN_SCRIPTS_DIR),
        str(start_dir.resolve(strict=False)),
        str(PROJECT_ROOT),
    ]
    existing = env.get("PYTHONPATH", "")
    if existing:
        path_entries.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(path_entries)
    return env


def parse_unittest_counts(output: str) -> dict[str, int]:
    tests = 0
    skipped = 0
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    if match:
        tests = int(match.group(1))
    skipped_match = re.search(r"skipped=(\d+)", output)
    if skipped_match:
        skipped = int(skipped_match.group(1))
    return {"tests": tests, "skipped": skipped}


def run_module(module: str, temp_root: Path, timeout_seconds: int, start_dir: Path) -> dict[str, Any]:
    memory_root = temp_root / safe_name(module)
    memory_root.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-X", "utf8", "-m", "unittest", module]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=child_env(memory_root, start_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration = time.perf_counter() - started
        combined = f"{completed.stdout}\n{completed.stderr}"
        counts = parse_unittest_counts(combined)
        return {
            "module": module,
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "duration": round(duration, 6),
            "tests": counts["tests"],
            "skipped": counts["skipped"],
            "stdout": completed.stdout[-OUTPUT_TAIL_CHARS:],
            "stderr": completed.stderr[-OUTPUT_TAIL_CHARS:],
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        duration = time.perf_counter() - started
        return {
            "module": module,
            "ok": False,
            "exit_code": 124,
            "duration": round(duration, 6),
            "tests": 0,
            "skipped": 0,
            "stdout": stdout[-OUTPUT_TAIL_CHARS:],
            "stderr": (stderr + f"\nModule timed out after {timeout_seconds}s.")[-OUTPUT_TAIL_CHARS:],
        }


def run_modules(
    modules: list[str],
    jobs: int,
    timeout_seconds: int,
    *,
    start_dir: Path = DEFAULT_TESTS_DIR,
    include_module_results: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
            futures = [
                executor.submit(run_module, module, temp_root, timeout_seconds, start_dir)
                for module in modules
            ]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
    results.sort(key=lambda item: str(item["module"]))
    failed = [item for item in results if not item["ok"]]
    slowest = sorted(results, key=lambda item: float(item["duration"]), reverse=True)
    result = {
        "ok": not failed,
        "modules": len(results),
        "tests": sum(int(item.get("tests") or 0) for item in results),
        "skipped": sum(int(item.get("skipped") or 0) for item in results),
        "jobs": max(1, jobs),
        "duration": round(time.perf_counter() - started, 6),
        "slowest_modules": [
            {
                "module": item["module"],
                "duration": item["duration"],
                "tests": item.get("tests", 0),
                "skipped": item.get("skipped", 0),
            }
            for item in slowest[:20]
        ],
        "failed_modules": failed,
    }
    if include_module_results:
        result["module_results"] = results
    return result


def safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return normalized or "test_module"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unittest modules in isolated subprocesses.")
    parser.add_argument("--start-dir", default=str(DEFAULT_TESTS_DIR))
    parser.add_argument("--pattern", default="test*.py")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--module-timeout", type=int, default=180)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    start_dir = Path(args.start_dir)
    modules = discover_modules(start_dir, args.pattern)
    result = run_modules(
        modules,
        jobs=args.jobs,
        timeout_seconds=args.module_timeout,
        start_dir=start_dir,
        include_module_results=not args.summary_only,
    )
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
