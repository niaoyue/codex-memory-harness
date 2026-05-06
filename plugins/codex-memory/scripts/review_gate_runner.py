from __future__ import annotations

import argparse
import codecs
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, TextIO

from review_findings import ReviewFindingsTracker, detect_review_findings


TAIL_LINES = 80
PARTIAL_TAIL_CHARS = 8192
PUMP_CHUNK_BYTES = 4096
PUMP_TEXT_FLUSH_CHARS = 4096
IDLE_GRACE_SECONDS = 0.1


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
    if _path_suffix(executable) != ".ps1":
        return command
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", executable, *command[1:]]


def _path_suffix(value: str) -> str:
    name = str(value).replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


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
                drained, last_output = _drain_after_grace(
                    events,
                    stdout_tail,
                    stderr_tail,
                    findings_tracker,
                    last_output,
                    stream_output=stream_output,
                    log_handle=log_handle,
                )
                if drained:
                    continue
                now = time.monotonic()
                if not idle_timed_out(last_output, now, idle_seconds):
                    continue
                idle_timeout = True
                _terminate(process)
                break
            if max_seconds > 0 and now - started > max_seconds:
                max_timeout = True
                _terminate(process)
                break

        for thread in threads:
            thread.join(timeout=1)
        _, last_output = _drain(
            events,
            stdout_tail,
            stderr_tail,
            findings_tracker,
            last_output,
            stream_output=stream_output,
            log_handle=log_handle,
        )
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


def _pump(name: str, stream: Any, events: queue.Queue[tuple[str, str]]) -> None:
    if stream is None:
        return
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending = ""
    try:
        while True:
            chunk = _read_chunk(stream)
            if not chunk:
                break
            text = decoder.decode(chunk)
            if text:
                pending += text
            if "\n" in pending or len(pending) >= PUMP_TEXT_FLUSH_CHARS:
                events.put((name, pending))
                pending = ""
            else:
                events.put((name, ""))
        final = decoder.decode(b"", final=True)
        if final:
            pending += final
        if pending:
            events.put((name, pending))
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
        if not text:
            continue
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


def _drain_after_grace(
    events: queue.Queue[tuple[str, str]],
    stdout_tail: TailBuffer,
    stderr_tail: TailBuffer,
    findings_tracker: ReviewFindingsTracker,
    last_output: float,
    *,
    stream_output: bool,
    log_handle: TextIO | None = None,
) -> tuple[bool, float]:
    try:
        name, text = events.get(timeout=IDLE_GRACE_SECONDS)
    except queue.Empty:
        return False, last_output
    events.put((name, text))
    return _drain(
        events,
        stdout_tail,
        stderr_tail,
        findings_tracker,
        last_output,
        stream_output=stream_output,
        log_handle=log_handle,
    )


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
