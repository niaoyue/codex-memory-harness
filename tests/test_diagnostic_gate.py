from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import diagnostic_gate


class DiagnosticGateTests(unittest.TestCase):
    def test_release_gate_finds_enabled_flags_and_bare_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "Feature.cs", "ai_diagnostics.enabled = true;\nDebug.Log(\"x\");\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual({item["type"] for item in gate["findings"]}, {"diagnostic_enabled", "bare_log"})
        self.assertEqual(gate["findings"][0]["path"], "client/Assets/Feature.cs")

    def test_release_gate_ignores_diagnostic_facade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "DiagnosticLog.cs", "Debug.Log(message);\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_does_not_exempt_every_diagnostic_named_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "DiagnosticsConfig.cs", "Debug.Log(\"bad\");\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["findings"][0]["type"], "bare_log")

    def test_release_gate_ignores_log_samples_in_strings_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "Feature.ts",
                "\n".join(
                    [
                        "const help = 'Debug.Log(\"sample\")';",
                        "const template = `console.log(\"sample\")`;",
                        "// cc.log('sample');",
                        "/* print('sample'); */",
                        "DiagnosticLog.Flow('ok');",
                    ]
                ),
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_ignores_log_samples_in_multiline_block_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "Feature.cs",
                "\n".join(
                    [
                        "/*",
                        "Debug.Log(\"sample\");",
                        "console.log(\"sample\");",
                        "*/",
                        "DiagnosticLog.Flow(\"ok\");",
                    ]
                ),
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_ignores_log_samples_in_multiline_csharp_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "Feature.cs",
                "\n".join(
                    [
                        "const string Help = @\"",
                        "Debug.Log(\"\"sample\"\");",
                        "\";",
                        "DiagnosticLog.Flow(\"ok\");",
                    ]
                ),
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_still_detects_string_sink_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "DiagnosticsConfig.cs", "diagnostic_logging.sink = \"http\";\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["findings"][0]["type"], "diagnostic_sink")

    def test_release_gate_detects_object_style_diagnostic_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "DiagnosticsConfig.ts",
                "const ai_diagnostics = { enabled: true, sink: \"console\" };\n",
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual({item["type"] for item in gate["findings"]}, {"diagnostic_enabled", "diagnostic_sink"})

    def test_release_gate_detects_multiline_object_style_diagnostic_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "DiagnosticsConfig.ts",
                "\n".join(["const aiDiagnostics = {", "  enabled: true,", "  sink: \"console\",", "};"]),
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual({item["type"] for item in gate["findings"]}, {"diagnostic_enabled", "diagnostic_sink"})

    def test_release_gate_detects_quoted_object_style_diagnostic_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "DiagnosticsConfig.ts",
                "\n".join(["const aiDiagnostics = {", "  \"enabled\": true,", "  \"sink\": \"console\",", "};"]),
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual({item["type"] for item in gate["findings"]}, {"diagnostic_enabled", "diagnostic_sink"})

    def test_release_gate_requires_manual_review_for_oversized_supported_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(diagnostic_gate, "MAX_BYTES", 20):
                _write_text(root / "client" / "Assets" / "ok.ts", "let ok=1;\n")
                _write_text(root / "client" / "Assets" / "large.ts", "let x='" + ("x" * 40) + "';\n")

                gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "manual_required")
        self.assertIn("oversized", gate["summary"])

    def test_release_gate_detects_bare_log_on_line_with_facade_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "Feature.cs", "DiagnosticLog.Flow(\"ok\"); Debug.Log(\"bad\");\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["findings"][0]["type"], "bare_log")

    def test_release_gate_detects_unity_debug_log_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "Feature.cs",
                "Debug.LogFormat(\"bad {0}\", value);\nDebug.LogException(error);\n",
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual([item["type"] for item in gate["findings"]], ["bare_log", "bare_log"])

    def test_release_gate_scans_template_literal_interpolations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "Feature.ts", "const value = `${console.log('bad')}`;\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["findings"][0]["type"], "bare_log")

    def test_release_gate_ignores_facade_raw_log_wrapper_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "Feature.cs", "ProjectLogger.Diagnostics.Debug.Log(\"ok\");\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_does_not_treat_suffix_facade_names_as_facade_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "Feature.cs", "NotDiagnosticLog.Debug.Log(\"bad\");\n")
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["findings"][0]["type"], "bare_log")

    def test_release_gate_tracks_lua_block_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(
                root / "client" / "Assets" / "Feature.lua",
                "\n".join(["--[[", "print('sample')", "]]", "DiagnosticLog.Flow('ok')"]),
            )
            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_scans_route_cwd_when_assigned_scope_is_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Assets" / "Touched.cs", "DiagnosticLog.Flow(\"ok\");\n")
            _write_text(root / "client" / "Assets" / "DiagnosticsConfig.cs", "ai_diagnostics.enabled = true;\n")
            route_plan = {
                "risk_level": "release_blocking",
                "routes": [{"cwd": "client", "assigned_scope": ["client/Assets/Touched.cs"]}],
            }

            gate = diagnostic_gate.evaluate_release_gate(root, route_plan)

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["findings"][0]["type"], "diagnostic_enabled")

    def test_release_gate_prunes_skipped_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "node_modules" / "bad.ts", "console.log('skip');\n")
            _write_text(root / "client" / "src" / "ok.ts", "DiagnosticLog.Flow('ok');\n")

            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_prunes_skipped_directories_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "Build" / "bundle.js", "console.log('generated');\n")
            _write_text(root / "client" / "src" / "ok.ts", "DiagnosticLog.Flow('ok');\n")

            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "passed")

    def test_release_gate_requires_manual_review_when_scan_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(diagnostic_gate, "MAX_FILES", 1):
                _write_text(root / "client" / "a.ts", "DiagnosticLog.Flow('a');\n")
                _write_text(root / "client" / "b.ts", "DiagnosticLog.Flow('b');\n")

                gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "manual_required")
        self.assertTrue(gate["truncated"])

    def test_release_gate_requires_manual_review_when_no_files_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_text(root / "client" / "README.md", "# no code\n")

            gate = diagnostic_gate.evaluate_release_gate(root, _route_plan())

        self.assertEqual(gate["status"], "manual_required")
        self.assertEqual(gate["scanned_files"], 0)


def _route_plan() -> dict[str, object]:
    return {
        "risk_level": "release_blocking",
        "routes": [{"assigned_scope": ["client/Assets"], "cwd": "client"}],
    }


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
