from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS_DIR = PROJECT_ROOT / "tests"


class TimedTextTestResult(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._starts: dict[unittest.case.TestCase, float] = {}
        self.durations: list[dict[str, Any]] = []

    def startTest(self, test: unittest.case.TestCase) -> None:
        self._starts[test] = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test: unittest.case.TestCase) -> None:
        started = self._starts.pop(test, None)
        duration = 0.0 if started is None else time.perf_counter() - started
        self.durations.append(
            {
                "id": test.id(),
                "module": test.__class__.__module__,
                "class": test.__class__.__qualname__,
                "duration": round(duration, 6),
            }
        )
        super().stopTest(test)


class TimedTextTestRunner(unittest.TextTestRunner):
    resultclass = TimedTextTestResult


def _add_import_paths() -> None:
    for path in (
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "plugins" / "codex-memory" / "scripts",
        PROJECT_ROOT / "tests",
    ):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def _default_env(memory_root: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("CODEX_MEMORY_SCOPE", "project")
    if memory_root is not None and not env.get("CODEX_MEMORY_CWD"):
        memory_root.mkdir()
        env["CODEX_MEMORY_CWD"] = str(memory_root)
    return env


def _summarize_modules(durations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    modules: dict[str, dict[str, Any]] = {}
    for item in durations:
        module = str(item["module"])
        bucket = modules.setdefault(module, {"module": module, "tests": 0, "duration": 0.0})
        bucket["tests"] += 1
        bucket["duration"] += float(item["duration"])
    for bucket in modules.values():
        bucket["duration"] = round(float(bucket["duration"]), 6)
    return sorted(modules.values(), key=lambda item: item["duration"], reverse=True)


def _run_tests(start_dir: Path, pattern: str, verbosity: int) -> tuple[TimedTextTestResult, str, float]:
    loader = unittest.defaultTestLoader
    suite = loader.discover(str(start_dir), pattern=pattern)
    stream = io.StringIO()
    runner = TimedTextTestRunner(stream=stream, verbosity=verbosity)
    started = time.perf_counter()
    result = runner.run(suite)
    elapsed = time.perf_counter() - started
    return result, stream.getvalue(), elapsed


def _result_payload(
    result: TimedTextTestResult,
    output: str,
    elapsed: float,
    *,
    top: int,
    slow_threshold: float,
) -> dict[str, Any]:
    slowest = sorted(result.durations, key=lambda item: item["duration"], reverse=True)
    return {
        "ok": result.wasSuccessful(),
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "duration": round(elapsed, 6),
        "slow_threshold": slow_threshold,
        "slowest_tests": slowest[:top],
        "slow_tests": [item for item in slowest if float(item["duration"]) >= slow_threshold],
        "slowest_modules": _summarize_modules(result.durations)[:top],
        "output_tail": output[-3000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unittest discovery and report slow tests.")
    parser.add_argument("--start-dir", default=str(DEFAULT_TESTS_DIR))
    parser.add_argument("--pattern", default="test*.py")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--slow-threshold", type=float, default=0.5)
    parser.add_argument("--verbosity", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    _add_import_paths()
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_root = None if os.environ.get("CODEX_MEMORY_CWD") else Path(temp_dir) / "behavior-memory"
        os.environ.update(_default_env(memory_root))
        result, output, elapsed = _run_tests(Path(args.start_dir), args.pattern, args.verbosity)
        payload = _result_payload(
            result,
            output,
            elapsed,
            top=args.top,
            slow_threshold=args.slow_threshold,
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(output, end="")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
