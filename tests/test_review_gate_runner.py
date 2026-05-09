from __future__ import annotations

import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import review_gate_runner


class ReviewGateRunnerTests(unittest.TestCase):
    def test_build_review_command_sets_effort_and_preserves_args(self) -> None:
        command = review_gate_runner.build_review_command(
            "codex.exe",
            "xhigh",
            ["--uncommitted", "--base", "main"],
        )

        self.assertEqual(command[:3], ["codex.exe", "review", "-c"])
        self.assertIn('model_reasoning_effort="xhigh"', command)
        self.assertEqual(command[-3:], ["--uncommitted", "--base", "main"])

    def test_windows_powershell_script_command_is_wrapped_for_subprocess(self) -> None:
        with mock.patch.object(review_gate_runner.os, "name", "nt"):
            command = review_gate_runner.build_review_command(
                r"C:\Users\Test\AppData\Roaming\npm\codex.ps1",
                "xhigh",
                ["--uncommitted"],
            )

        self.assertEqual(command[:5], ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
        self.assertEqual(command[5], r"C:\Users\Test\AppData\Roaming\npm\codex.ps1")
        self.assertEqual(command[-4:], ["review", "-c", 'model_reasoning_effort="xhigh"', "--uncommitted"])

    def test_windows_default_codex_resolves_with_pathext(self) -> None:
        with (
            mock.patch.object(review_gate_runner.os, "name", "nt"),
            mock.patch.object(review_gate_runner.shutil, "which", return_value=r"C:\Tools\codex.CMD") as which_mock,
        ):
            command = review_gate_runner.build_review_command("codex", "xhigh", ["--uncommitted"])

        which_mock.assert_called_once_with("codex")
        self.assertEqual(command[0], r"C:\Tools\codex.CMD")
        self.assertEqual(command[-4:], ["review", "-c", 'model_reasoning_effort="xhigh"', "--uncommitted"])

    def test_windows_path_like_codex_is_not_path_searched(self) -> None:
        with (
            mock.patch.object(review_gate_runner.os, "name", "nt"),
            mock.patch.object(review_gate_runner.shutil, "which") as which_mock,
        ):
            command = review_gate_runner.build_review_command(r".\codex.cmd", "xhigh", ["--uncommitted"])

        which_mock.assert_not_called()
        self.assertEqual(command[0], r".\codex.cmd")

    def test_run_monitored_marks_child_process_as_review_gate(self) -> None:
        script = (
            "import os\n"
            "print(os.environ.get('CODEX_REVIEW_GATE_RUNNING', ''))\n"
            "print(os.environ.get('CODEX_XHIGH_REVIEW_DISPATCH_DISABLE', ''))\n"
        )

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=5,
            stream_output=False,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout_tail"], ["1", "1"])

    def test_idle_timeout_uses_last_output_time_not_total_duration(self) -> None:
        self.assertFalse(review_gate_runner.idle_timed_out(1500.0, 1601.0, 600.0))
        self.assertTrue(review_gate_runner.idle_timed_out(1000.0, 1601.0, 600.0))
        self.assertFalse(review_gate_runner.idle_timed_out(1000.0, 9999.0, 0.0))

    def test_detect_review_findings_from_codex_review_comments(self) -> None:
        findings = review_gate_runner.detect_review_findings(
            [
                "Full review comments:",
                "- [P1] Fix the incorrect gate result",
                "- [P2] Add coverage for review findings",
            ],
            [],
        )

        self.assertTrue(findings["review_findings_found"])
        self.assertTrue(findings["blocking_findings_found"])
        self.assertEqual(findings["review_findings_count"], 2)
        self.assertEqual(findings["review_finding_priorities"], ["P1", "P2"])
        self.assertEqual(findings["review_findings_sources"], ["stdout_tail"])
        self.assertTrue(findings["review_findings_marker_found"])

    def test_detect_review_findings_from_structured_json_titles(self) -> None:
        findings = review_gate_runner.detect_review_findings(
            [
                '{"findings":[{"title":"[P1] Fix the incorrect gate result"},'
                '{"title":"[P2] Add coverage for review findings"}]}',
            ],
            [],
        )

        self.assertTrue(findings["review_findings_found"])
        self.assertEqual(findings["review_findings_count"], 2)
        self.assertEqual(findings["review_finding_priorities"], ["P1", "P2"])
        self.assertEqual(findings["review_findings_sources"], ["stdout_tail"])

    def test_detect_review_findings_from_multiline_structured_json(self) -> None:
        findings = review_gate_runner.detect_review_findings(
            [
                "{",
                '  "findings": [',
                '    {"title": "[P1] Fix the incorrect gate result"},',
                '    {"message": "missing bracketed priority", "priority": 2}',
                "  ]",
                "}",
            ],
            [],
        )

        self.assertTrue(findings["review_findings_found"])
        self.assertEqual(findings["review_findings_count"], 2)
        self.assertEqual(findings["review_finding_priorities"], ["P1", "P2"])
        self.assertEqual(findings["review_findings_sources"], ["stdout_tail"])

    def test_detect_review_findings_from_multiline_json_without_priority(self) -> None:
        findings = review_gate_runner.detect_review_findings(
            [
                "{",
                '  "findings": [',
                '    {"title": "Gate misses structured output"}',
                "  ]",
                "}",
            ],
            [],
        )

        self.assertTrue(findings["review_findings_found"])
        self.assertTrue(findings["blocking_findings_found"])
        self.assertEqual(findings["review_findings_count"], 1)
        self.assertEqual(findings["review_finding_priorities"], [])
        self.assertEqual(findings["review_findings_sources"], ["stdout_tail"])

    def test_detect_review_findings_from_empty_structured_json_passes(self) -> None:
        findings = review_gate_runner.detect_review_findings(
            [
                "{",
                '  "findings": []',
                "}",
            ],
            [],
        )

        self.assertFalse(findings["review_findings_found"])
        self.assertFalse(findings["blocking_findings_found"])
        self.assertEqual(findings["review_findings_count"], 0)
        self.assertEqual(findings["review_finding_priorities"], [])
        self.assertEqual(findings["review_findings_sources"], [])

    def test_exit_zero_with_review_findings_fails_gate(self) -> None:
        script = (
            "print('Full review comments:')\n"
            "print('- [P1] Treat Codex review findings as blocking even with exit code 0')\n"
            "print('- [P2] Preserve the finding fields in the summary')\n"
        )

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=5,
            stream_output=False,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["gate_exit_code"], 1)
        self.assertTrue(result["review_findings_found"])
        self.assertTrue(result["blocking_findings_found"])
        self.assertEqual(result["review_findings_count"], 2)
        self.assertEqual(result["review_finding_priorities"], ["P1", "P2"])

    def test_exit_zero_with_multiline_json_review_findings_fails_gate(self) -> None:
        script = (
            "print('{')\n"
            "print('  \"findings\": [')\n"
            "print('    {\"title\": \"[P1] Treat structured findings as blocking\"}')\n"
            "print('  ]')\n"
            "print('}')\n"
        )

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=5,
            stream_output=False,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["gate_exit_code"], 1)
        self.assertTrue(result["review_findings_found"])
        self.assertTrue(result["blocking_findings_found"])
        self.assertEqual(result["review_findings_count"], 1)
        self.assertEqual(result["review_finding_priorities"], ["P1"])

    def test_exit_zero_with_empty_multiline_json_review_findings_passes_gate(self) -> None:
        script = "print('{')\nprint('  \"findings\": []')\nprint('}')\n"

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=5,
            stream_output=False,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["gate_exit_code"], 0)
        self.assertFalse(result["review_findings_found"])
        self.assertFalse(result["blocking_findings_found"])
        self.assertEqual(result["review_findings_count"], 0)

    def test_main_returns_gate_exit_code_when_findings_fail_gate(self) -> None:
        result = {
            "ok": False,
            "exit_code": 0,
            "gate_exit_code": 1,
            "review_findings_found": True,
            "blocking_findings_found": True,
        }

        with (
            mock.patch.object(review_gate_runner, "run_monitored", return_value=result),
            mock.patch.object(review_gate_runner, "write_summary"),
            mock.patch.object(sys, "argv", ["review_gate_runner.py", "--no-stream-output"]),
            mock.patch.object(review_gate_runner.sys.stderr, "write"),
            mock.patch.object(review_gate_runner.sys.stderr, "flush"),
        ):
            exit_code = review_gate_runner.main()

        self.assertEqual(exit_code, 1)

    def test_continuous_output_without_newlines_prevents_idle_timeout(self) -> None:
        script = (
            "import sys,time\n"
            "for _ in range(5):\n"
            "    sys.stdout.write('x')\n"
            "    sys.stdout.flush()\n"
            "    time.sleep(0.2)\n"
        )

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=0.5,
            max_seconds=5,
            stream_output=False,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["idle_timeout"])
        self.assertEqual(result["stdout_tail"], ["xxxxx"])

    def test_long_output_without_newlines_keeps_bounded_tail(self) -> None:
        buffer = review_gate_runner.TailBuffer(max_lines=3, partial_limit=8)

        buffer.append("x" * 100)

        self.assertEqual(buffer.snapshot(), ["x" * 8])
        self.assertEqual(len(buffer.partial), 8)

    def test_pump_uses_chunked_reads_instead_of_byte_events(self) -> None:
        class FakeStream:
            def __init__(self, data: bytes) -> None:
                self.data = data
                self.calls: list[int] = []
                self.closed = False

            def read(self, size: int) -> bytes:
                self.calls.append(size)
                if not self.data:
                    return b""
                chunk = self.data[:size]
                self.data = self.data[size:]
                return chunk

            def close(self) -> None:
                self.closed = True

        stream = FakeStream(b"x" * (review_gate_runner.PUMP_CHUNK_BYTES + 5))
        events: queue.Queue[tuple[str, str]] = queue.Queue()

        review_gate_runner._pump("stdout", stream, events)

        self.assertIn(review_gate_runner.PUMP_CHUNK_BYTES, stream.calls)
        self.assertLess(events.qsize(), 4)
        self.assertTrue(stream.closed)

    def test_idle_timeout_terminates_silent_process(self) -> None:
        script = "import time; time.sleep(2)"

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=0.5,
            max_seconds=5,
            stream_output=False,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["idle_timeout"])
        self.assertNotEqual(result["exit_code"], 0)
        self.assertFalse(result["max_timeout"])
        self.assertFalse(result["safety_cap_triggered"])
        self.assertEqual(result["timeout_policy"], "progress_output_observation")
        self.assertEqual(result["idle_policy"], "stdout_stderr_no_progress_only")

    def test_summary_and_log_files_capture_result_without_streaming(self) -> None:
        script = "import sys; print('review-output'); print('review-error', file=sys.stderr)"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            log_file = temp_path / "review.log"
            summary_file = temp_path / "summary.json"
            result = review_gate_runner.run_monitored(
                [sys.executable, "-c", script],
                cwd=PROJECT_ROOT,
                idle_seconds=5,
                max_seconds=5,
                stream_output=False,
                log_file=log_file,
            )
            review_gate_runner.write_summary(summary_file, result)

            self.assertTrue(result["ok"])
            self.assertFalse(result["total_timeout_disabled"])
            self.assertEqual(result["max_seconds"], 5)
            self.assertEqual(result["safety_cap_seconds"], 5)
            self.assertEqual(result["total_timeout_policy"], "infrastructure_safety_cap")
            self.assertIn("review-output", log_file.read_text(encoding="utf-8"))
            self.assertIn("review-error", log_file.read_text(encoding="utf-8"))
            self.assertIn('"exit_code": 0', summary_file.read_text(encoding="utf-8"))

    def test_default_runner_result_disables_total_timeout(self) -> None:
        script = "print('review-ok')"

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=5,
            stream_output=False,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["total_timeout_disabled"])
        self.assertEqual(result["max_seconds"], 0)
        self.assertFalse(result["max_timeout"])
        self.assertEqual(result["total_timeout_policy"], "none")

    def test_launch_failure_returns_structured_result_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_command = Path(temp_dir) / "missing-review-command.exe"
            log_file = Path(temp_dir) / "review.log"
            result = review_gate_runner.run_monitored(
                [str(missing_command)],
                cwd=PROJECT_ROOT,
                idle_seconds=5,
                stream_output=False,
                log_file=log_file,
            )

            self.assertFalse(result["ok"])
            self.assertTrue(result["launch_failed"])
            self.assertEqual(result["exit_code"], 127)
            self.assertFalse(result["idle_timeout"])
            self.assertFalse(result["max_timeout"])
            self.assertIn("FileNotFoundError", "\n".join(result["stderr_tail"]))
            self.assertIn("FileNotFoundError", log_file.read_text(encoding="utf-8"))

    def test_continuous_output_can_run_past_observation_windows_without_total_timeout(self) -> None:
        script = (
            "import sys,time\n"
            "for _ in range(8):\n"
            "    print('tick', flush=True)\n"
            "    time.sleep(0.2)\n"
        )

        result = review_gate_runner.run_monitored(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            idle_seconds=1.0,
            stream_output=False,
        )

        self.assertTrue(result["ok"])
        self.assertGreater(result["duration_seconds"], 1.0)
        self.assertTrue(result["total_timeout_disabled"])
        self.assertFalse(result["idle_timeout"])
        self.assertFalse(result["max_timeout"])

    def test_windows_timeout_terminates_process_tree(self) -> None:
        process = mock.Mock()
        process.pid = 1234
        process.poll.return_value = None
        process.wait.return_value = 0

        with (
            mock.patch.object(review_gate_runner.os, "name", "nt"),
            mock.patch.object(review_gate_runner.subprocess, "run") as run_mock,
        ):
            review_gate_runner._terminate(process)

        run_mock.assert_called_once()
        command = run_mock.call_args.args[0]
        self.assertEqual(command[:2], ["taskkill", "/PID"])
        self.assertIn("/T", command)
        self.assertIn("/F", command)
        process.terminate.assert_not_called()


if __name__ == "__main__":
    raise SystemExit(unittest.main())
