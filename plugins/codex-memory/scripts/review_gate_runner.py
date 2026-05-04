from __future__ import annotations

import argparse
import codecs
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, TextIO


TAIL_LINES = 80
PARTIAL_TAIL_CHARS = 8192
PUMP_CHUNK_BYTES = 4096
REVIEW_FINDING_PATTERN = re.compile(r"(?im)^\s*(?:[-*]|\d+[.)])\s*\[(P\d+)\](?=\s|:|-|$)")
REVIEW_FINDING_INLINE_PATTERN = re.compile(r"(?i)\[(P\d+)\](?=\s|:|-|$)")
REVIEW_COMMENTS_MARKER_PATTERN = re.compile(r"(?im)^\s*Full review comments:\s*$")


class TailBuffer:
    def __init__(self, max_lines: int, partial_limit: int = PARTIAL_TAIL_CHARS) -> None:
        self.max_lines = max_lines
        self.partial_limit = partial_limit
        self.lines: deque[str] = deque(maxlen=max_lines)
        self.partial = ""

    def append(self, text: str) -> None:
        if not text:
            return
        self.partial += text
        while "\n" in self.partial:
            line, self.partial = self.partial.split("\n", 1)
            self.lines.append(self._tail(line.rstrip("\r")))
        self.partial = self._tail(self.partial)

    def snapshot(self) -> list[str]:
        lines = list(self.lines)
        if self.partial:
            lines.append(self.partial.rstrip("\r"))
        return lines[-self.max_lines :]

    def _tail(self, text: str) -> str:
        if len(text) <= self.partial_limit:
            return text
        return text[-self.partial_limit :]


class ReviewFindingsTracker:
    def __init__(self) -> None:
        self._partials: dict[str, str] = {}
        self._text: dict[str, list[str]] = {}
        self._priorities: list[str] = []
        self._sources: list[str] = []
        self._count = 0
        self._marker_found = False
        self._structured_recorded = False

    def append(self, source: str, text: str) -> None:
        if not text:
            return
        self._append_text(source, text)
        partial = self._partials.get(source, "") + text
        while "\n" in partial:
            line, partial = partial.split("\n", 1)
            self._record_line(source, line.rstrip("\r"))
        self._partials[source] = partial[-PARTIAL_TAIL_CHARS:]

    def append_lines(self, source: str, lines: list[str]) -> None:
        self._append_text(source, "\n".join(lines))
        for line in lines:
            self._record_line(source, line.rstrip("\r"))

    def summary(self) -> dict[str, Any]:
        for source, partial in list(self._partials.items()):
            if not partial:
                continue
            self._record_line(source, partial.rstrip("\r"))
            self._partials[source] = ""
        self._record_structured_json()
        findings_found = self._count > 0
        return {
            "review_findings_found": findings_found,
            "blocking_findings_found": findings_found,
            "review_findings_count": self._count,
            "review_finding_priorities": list(self._priorities),
            "review_findings_sources": list(self._sources),
            "review_findings_marker_found": self._marker_found,
        }

    def _record_line(self, source: str, line: str) -> None:
        self._marker_found = self._marker_found or REVIEW_COMMENTS_MARKER_PATTERN.match(line) is not None
        matches = REVIEW_FINDING_PATTERN.findall(line)
        if not matches:
            return
        self._record_matches(source, len(matches), matches)

    def _append_text(self, source: str, text: str) -> None:
        if text:
            self._text.setdefault(source, []).append(text)

    def _record_structured_json(self) -> None:
        if self._structured_recorded:
            return
        self._structured_recorded = True
        for source, chunks in self._text.items():
            for count, priorities in _json_finding_groups("".join(chunks)):
                self._record_matches(source, count, priorities)

    def _record_matches(self, source: str, count: int, priorities: list[str]) -> None:
        if count <= 0:
            return
        self._count += count
        if source not in self._sources:
            self._sources.append(source)
        for priority in priorities:
            normalized = priority.upper()
            if normalized not in self._priorities:
                self._priorities.append(normalized)


def _json_finding_groups(text: str) -> list[tuple[int, list[str]]]:
    groups: list[tuple[int, list[str]]] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        start = _next_json_start(text, index)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        count, priorities = _findings_from_json(payload)
        if count:
            groups.append((count, priorities))
        index = end if end > start else start + 1
    return groups


def _next_json_start(text: str, index: int) -> int:
    candidates = [position for position in (text.find("{", index), text.find("[", index)) if position >= 0]
    return min(candidates) if candidates else -1


def _findings_from_json(value: Any) -> tuple[int, list[str]]:
    count = 0
    priorities: list[str] = []
    if isinstance(value, dict):
        findings = value.get("findings")
        if isinstance(findings, list):
            count += len(findings)
            for finding in findings:
                priorities.extend(_priorities_from_json(finding))
        for item in value.values():
            child_count, child_priorities = _findings_from_json(item)
            count += child_count
            priorities.extend(child_priorities)
    elif isinstance(value, list):
        for item in value:
            child_count, child_priorities = _findings_from_json(item)
            count += child_count
            priorities.extend(child_priorities)
    return count, priorities


def _priorities_from_json(value: Any) -> list[str]:
    results: list[str] = []
    if isinstance(value, dict):
        for key in ("title", "message", "body", "description", "priority", "severity"):
            results.extend(_priority_values(value.get(key)))
    elif isinstance(value, list):
        for item in value:
            results.extend(_priorities_from_json(item))
    return results


def _priority_values(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, int):
        return [f"P{value}"] if value >= 0 else []
    text = str(value)
    bracketed = REVIEW_FINDING_INLINE_PATTERN.findall(text)
    if bracketed:
        return bracketed
    match = re.fullmatch(r"(?i)P(\d+)", text.strip())
    if match:
        return [f"P{match.group(1)}"]
    return []


def build_review_command(codex: str, effort: str, review_args: list[str]) -> list[str]:
    if not codex:
        raise ValueError("codex executable is required")
    command = [resolve_executable_for_windows(codex), "review", "-c", f'model_reasoning_effort="{effort}"', *review_args]
    return normalize_command_for_windows(command)


def resolve_executable_for_windows(executable: str) -> str:
    if os.name != "nt" or not executable:
        return executable
    if "/" in executable or "\\" in executable:
        return executable
    resolved = shutil.which(executable)
    return resolved or executable


def normalize_command_for_windows(command: list[str]) -> list[str]:
    if os.name != "nt" or not command:
        return command
    executable = command[0]
    if Path(executable).suffix.lower() != ".ps1":
        return command
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", executable, *command[1:]]


def idle_timed_out(last_output: float, now: float, idle_seconds: float) -> bool:
    return idle_seconds > 0 and now - last_output > idle_seconds


def run_monitored(
    command: list[str],
    *,
    cwd: Path,
    idle_seconds: float,
    max_seconds: float = 0,
    stream_output: bool = True,
    log_file: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    last_output = started
    events: queue.Queue[tuple[str, str]] = queue.Queue()
    stdout_tail = TailBuffer(TAIL_LINES)
    stderr_tail = TailBuffer(TAIL_LINES)
    findings_tracker = ReviewFindingsTracker()
    log_handle = _open_log(log_file)
    try:
        try:
            process = subprocess.Popen(command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        except OSError as exc:
            message = f"{type(exc).__name__}: {exc}"
            stderr_tail.append(message + "\n")
            findings_tracker.append("stderr_tail", message + "\n")
            if log_handle is not None:
                log_handle.write(message + "\n")
                log_handle.flush()
            return _result(
                command=command,
                log_file=log_file,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
                findings_tracker=findings_tracker,
                started=started,
                exit_code=127,
                idle_timeout=False,
                max_timeout=False,
                idle_seconds=idle_seconds,
                max_seconds=max_seconds,
                launch_failed=True,
            )
        threads = [threading.Thread(target=_pump, args=(name, stream, events), daemon=True) for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
        for thread in threads:
            thread.start()

        idle_timeout = False
        max_timeout = False
        while process.poll() is None:
            drained, last_output = _drain(events, stdout_tail, stderr_tail, findings_tracker, last_output, stream_output=stream_output, log_handle=log_handle)
            if not drained:
                time.sleep(0.2)
            now = time.monotonic()
            if idle_timed_out(last_output, now, idle_seconds):
                idle_timeout = True
                _terminate(process)
                break
            if max_seconds > 0 and now - started > max_seconds:
                max_timeout = True
                _terminate(process)
                break

        for thread in threads:
            thread.join(timeout=1)
        _drain(events, stdout_tail, stderr_tail, findings_tracker, last_output, stream_output=stream_output, log_handle=log_handle)
    finally:
        if log_handle is not None:
            log_handle.close()
    exit_code = 124 if idle_timeout or max_timeout else process.returncode if process.returncode is not None else 124
    return _result(
        command=command, log_file=log_file, stdout_tail=stdout_tail, stderr_tail=stderr_tail,
        findings_tracker=findings_tracker, started=started, exit_code=exit_code,
        idle_timeout=idle_timeout, max_timeout=max_timeout, idle_seconds=idle_seconds, max_seconds=max_seconds,
    )


def _result(
    *,
    command: list[str],
    log_file: Path | None,
    stdout_tail: TailBuffer,
    stderr_tail: TailBuffer,
    findings_tracker: ReviewFindingsTracker,
    started: float,
    exit_code: int,
    idle_timeout: bool,
    max_timeout: bool,
    idle_seconds: float,
    max_seconds: float,
    launch_failed: bool = False,
) -> dict[str, Any]:
    duration = round(time.monotonic() - started, 3)
    stdout_snapshot = stdout_tail.snapshot()
    stderr_snapshot = stderr_tail.snapshot()
    findings = findings_tracker.summary()
    command_ok = exit_code == 0 and not idle_timeout and not max_timeout
    ok = command_ok and not findings["review_findings_found"]
    gate_exit_code = 0 if ok else exit_code or 1
    return {
        "ok": ok,
        "exit_code": exit_code,
        "gate_exit_code": gate_exit_code,
        "launch_failed": launch_failed,
        "idle_timeout": idle_timeout,
        "max_timeout": max_timeout,
        "safety_cap_triggered": max_timeout,
        **findings,
        "total_timeout_disabled": max_seconds <= 0,
        "duration_seconds": duration,
        "idle_seconds": idle_seconds,
        "max_seconds": max_seconds,
        "safety_cap_seconds": max_seconds,
        "timeout_policy": "progress_output_observation",
        "idle_policy": "stdout_stderr_no_progress_only",
        "total_timeout_policy": "none" if max_seconds <= 0 else "infrastructure_safety_cap",
        "command": command,
        "log_file": str(log_file) if log_file else "",
        "stdout_tail": stdout_snapshot,
        "stderr_tail": stderr_snapshot,
    }


def detect_review_findings(stdout_lines: list[str], stderr_lines: list[str]) -> dict[str, Any]:
    tracker = ReviewFindingsTracker()
    for source, lines in (("stdout_tail", stdout_lines), ("stderr_tail", stderr_lines)):
        tracker.append_lines(source, lines)
    return tracker.summary()


def _pump(name: str, stream: Any, events: queue.Queue[tuple[str, str]]) -> None:
    if stream is None:
        return
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        while True:
            chunk = _read_chunk(stream)
            if not chunk:
                break
            events.put((name, decoder.decode(chunk)))
        final = decoder.decode(b"", final=True)
        if final:
            events.put((name, final))
    finally:
        stream.close()


def _read_chunk(stream: Any) -> bytes:
    read1 = getattr(stream, "read1", None)
    if callable(read1):
        return read1(PUMP_CHUNK_BYTES)
    return stream.read(PUMP_CHUNK_BYTES)


def _drain(
    events: queue.Queue[tuple[str, str]],
    stdout_tail: TailBuffer,
    stderr_tail: TailBuffer,
    findings_tracker: ReviewFindingsTracker,
    last_output: float,
    *,
    stream_output: bool,
    log_handle: TextIO | None = None,
) -> tuple[bool, float]:
    drained = False
    while True:
        try:
            name, text = events.get_nowait()
        except queue.Empty:
            return drained, last_output
        drained = True
        last_output = time.monotonic()
        tail = stderr_tail if name == "stderr" else stdout_tail
        source = "stderr_tail" if name == "stderr" else "stdout_tail"
        output = sys.stderr if name == "stderr" else sys.stdout
        tail.append(text)
        findings_tracker.append(source, text)
        if log_handle is not None:
            log_handle.write(text)
            log_handle.flush()
        if stream_output:
            output.write(text)
            output.flush()


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        _terminate_windows_tree(process)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _terminate_windows_tree(process: subprocess.Popen[str]) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=10)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    process.terminate()


def _open_log(log_file: Path | None) -> TextIO | None:
    if log_file is None:
        return None
    log_file.parent.mkdir(parents=True, exist_ok=True)
    return log_file.open("w", encoding="utf-8", newline="")


def write_summary(summary_file: Path | None, result: dict[str, Any]) -> None:
    if summary_file is None:
        return
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Codex review with idle-output timeout semantics.")
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--effort", default="xhigh", choices=["low", "medium", "high", "xhigh"])
    parser.add_argument("--idle-seconds", type=float, default=0)
    parser.add_argument("--max-seconds", type=float, default=0, help="Infrastructure safety cap. Keep 0 for SubAgent review runners; this is not a review timeout.")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--summary-file", default="")
    parser.add_argument("--log-file", default="")
    parser.add_argument("--no-stream-output", action="store_true")
    parser.add_argument("review_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    review_args = args.review_args[1:] if args.review_args[:1] == ["--"] else args.review_args
    command = build_review_command(args.codex, args.effort, review_args)
    sys.stderr.write(f"REVIEW_GATE_RUNNER idle_seconds={max(args.idle_seconds, 0)} max_seconds={max(args.max_seconds, 0)} policy=progress_output_observation\n")
    sys.stderr.flush()
    result = run_monitored(command, cwd=Path(args.cwd).resolve(), idle_seconds=max(args.idle_seconds, 0), max_seconds=max(args.max_seconds, 0), stream_output=not args.no_stream_output, log_file=Path(args.log_file).resolve() if args.log_file else None)
    write_summary(Path(args.summary_file).resolve() if args.summary_file else None, result)
    sys.stderr.write(f"\nREVIEW_GATE_SUMMARY {json.dumps(result, ensure_ascii=False)}\n")
    return int(result["gate_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
