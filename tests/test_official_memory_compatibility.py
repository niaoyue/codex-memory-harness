from __future__ import annotations

import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import init_storage
import install_support
import codex_bootstrap
import codex_config_status
import official_memory_status


class OfficialMemoryCompatibilityTests(unittest.TestCase):
    def test_harness_global_memory_uses_dedicated_codex_home_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            try:
                os.environ.pop("CODEX_HOME", None)
                status = official_memory_status.inspect_official_memory(Path(temp_dir))
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        official_dir = status["official_memories_dir"].replace("\\", "/")
        self.assertTrue(official_dir.endswith(".codex/memories"))
        self.assertIn("codex-memory-harness", status["harness_global_memory_dir"])
        self.assertNotEqual(status["official_memories_dir"], status["harness_global_memory_dir"])
        self.assertTrue(status["official_dir_reserved_for_codex"])
        self.assertFalse(status["chronicle"]["content_read"])

    def test_official_memory_status_reads_feature_flag_without_reading_memories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "[features]\nmemories = true\n\n[memories]\ngenerate_memories = true\n",
                encoding="utf-8",
            )
            official_dir = codex_home / "memories"
            official_dir.mkdir()
            (official_dir / "memory.db").write_text("", encoding="utf-8")
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = official_memory_status.inspect_official_memory()
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(status["config_parse_ok"])
        self.assertTrue(status["features_memories"])
        self.assertTrue(status["memories_generate_memories"])
        self.assertTrue(status["official_feature_enabled"])
        self.assertEqual(status["legacy_harness_markers_in_official_dir"], ["memory.db"])

    def test_official_memory_status_defaults_omitted_generation_flag_to_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "[features]\nmemories = true\n",
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = official_memory_status.inspect_official_memory()
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(status["features_memories"])
        self.assertIsNone(status["memories_generate_memories"])
        self.assertTrue(status["official_feature_enabled"])

    def test_official_memory_status_reports_feature_disable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "[features]\nmemories = false\n",
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = official_memory_status.inspect_official_memory()
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertFalse(status["features_memories"])
        self.assertIsNone(status["memories_generate_memories"])
        self.assertFalse(status["official_feature_enabled"])

    def test_official_memory_status_reports_explicit_generation_disable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "[features]\nmemories = true\n\n[memories]\ngenerate_memories = false\n",
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = official_memory_status.inspect_official_memory()
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(status["features_memories"])
        self.assertFalse(status["memories_generate_memories"])
        self.assertFalse(status["official_feature_enabled"])

    def test_official_memory_status_reports_explicit_use_disable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "[features]\nmemories = true\n\n[memories]\nuse_memories = false\n",
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = official_memory_status.inspect_official_memory()
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(status["features_memories"])
        self.assertFalse(status["memories_use_memories"])
        self.assertFalse(status["official_feature_enabled"])

    def test_global_storage_respects_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "custom-codex"
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                with mock.patch.object(init_storage, "GLOBAL_STORAGE_DIR", None):
                    paths = init_storage.resolve_storage_paths(scope="global", cwd=temp_dir)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertEqual(paths.storage_dir, codex_home / "codex-memory-harness" / "memories")

    def test_installed_guidance_respects_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "custom-codex"
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                block = install_support.agents_block(Path("C:/Users/Test/plugins/codex-memory"))
                agents_path = install_support.home_agents_path()
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertIn(str(codex_home / "memories"), block)
        self.assertIn(str(codex_home / "codex-memory-harness" / "memories"), block)
        self.assertIn("subagent_dispatch_plan.host_spawn_requests", block)
        self.assertIn("host_dispatch_allowed=true", block)
        self.assertIn("subagent_runtime.recommended=true", block)
        self.assertIn("spawn_agent", block)
        self.assertIn("actual_subagents=0", block)
        self.assertIn("复杂/应用级/多阶段实现", block)
        self.assertIn("host_subagent_required", block)
        self.assertIn("dispatch_required=true", block)
        self.assertIn("autostart=true", block)
        self.assertIn("openspec/specs/", block)
        self.assertIn("subagent_runtime_policy", block)
        self.assertIn("正式 implementation 任务", block)
        self.assertIn("timeout 只能作为本次观察窗口", block)
        self.assertIn("不得仅因观察窗口到期而中断", block)
        self.assertIn("OpenSpec upstream snapshot 是默认项目骨架和启动自检的一部分", block)
        self.assertIn("codex openspec upstream sync --version 1.3.1", block)
        self.assertIn("codex openspec upstream verify", block)
        self.assertIn("candidate commit", block)
        self.assertIn("codex xhigh review --commit $commitSha", block)
        self.assertEqual(agents_path, codex_home / "AGENTS.md")

    def test_bootstrap_doctor_reads_agents_from_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            temp_root = Path(temp_dir)
            codex_home = temp_root / "custom-codex"
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text(
                "Codex Memory\ncodex memory doctor\n",
                encoding="utf-8",
            )
            project_root = temp_root / "project"
            (project_root / ".codex" / "memories").mkdir(parents=True)
            harness_dir = project_root / ".codex" / "harness"
            harness_dir.mkdir(parents=True)
            (harness_dir / "commands.json").write_text("{}", encoding="utf-8")
            (harness_dir / "project_profile.json").write_text("{}", encoding="utf-8")
            home_marketplace = temp_root / "marketplace.json"
            home_marketplace.write_text(
                '{"plugins": [{"name": "codex-memory"}]}',
                encoding="utf-8",
            )
            stale_default_agents = temp_root / "missing-default" / "AGENTS.md"
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                with (
                    mock.patch.object(codex_bootstrap, "HOME_AGENTS", stale_default_agents),
                    mock.patch.object(codex_bootstrap, "HOME_PLUGIN", codex_bootstrap._plugin_root()),
                    mock.patch.object(codex_bootstrap, "HOME_MARKETPLACE", home_marketplace),
                ):
                    result = codex_bootstrap.inspect_state(project_root, init=False)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertEqual(result["memory"]["official_codex"]["codex_home"], str(codex_home))
        self.assertTrue(result["checks"]["home_agents_exists"])
        self.assertTrue(result["checks"]["home_agents_mentions_cli_entrypoints"])
        self.assertFalse(
            any("codex memory doctor/init" in item for item in result["recommendations"])
        )

    def test_codex_config_status_reports_native_alignment_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                'sandbox_mode = "danger-full-access"\napproval_policy = "never"\n',
                encoding="utf-8",
            )
            plugin_root = Path(temp_dir) / "plugin"
            plugin_root.mkdir()
            (plugin_root / "hooks.json").write_text(
                '{"hooks": {"PostToolUse": []}}',
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = codex_config_status.inspect_codex_config(plugin_root=plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertFalse(status["hooks_enabled"])
        self.assertTrue(status["native_alignment"]["needs_hooks_feature"])
        self.assertTrue(status["native_alignment"]["needs_hook_event_update"])
        self.assertTrue(status["native_alignment"]["high_risk_unattended_permissions"])
        self.assertEqual(
            status["plugin_hooks"]["missing_recommended_events"],
            ["UserPromptSubmit", "PostToolUse", "Stop"],
        )

    def test_codex_config_status_accepts_recommended_hook_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "[features]\nhooks = true\n\n[mcp_servers.codex-memory]\ncommand = \"py\"\n",
                encoding="utf-8",
            )
            plugin_root = Path(temp_dir) / "plugin"
            plugin_root.mkdir()
            command_hook = {"hooks": [{"type": "command", "command": "py hook_bridge.py"}]}
            (plugin_root / "hooks.json").write_text(
                json.dumps({"hooks": {
                    "UserPromptSubmit": [command_hook],
                    "PostToolUse": [command_hook],
                    "Stop": [command_hook],
                }}),
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = codex_config_status.inspect_codex_config(plugin_root=plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(status["hooks_enabled"])
        self.assertTrue(status["codex_memory_mcp_configured"])
        self.assertTrue(status["plugin_hooks"]["covers_recommended_events"])
        self.assertTrue(status["native_alignment"]["ok"])

    def test_codex_config_status_rejects_empty_hook_event_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "[features]\nhooks = true\n",
                encoding="utf-8",
            )
            plugin_root = Path(temp_dir) / "plugin"
            plugin_root.mkdir()
            (plugin_root / "hooks.json").write_text(
                '{"hooks": {"UserPromptSubmit": [], "PostToolUse": [], "Stop": []}}',
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                status = codex_config_status.inspect_codex_config(plugin_root=plugin_root)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertFalse(status["plugin_hooks"]["covers_recommended_events"])
        self.assertEqual(
            status["plugin_hooks"]["missing_recommended_events"],
            ["UserPromptSubmit", "PostToolUse", "Stop"],
        )
        self.assertTrue(status["native_alignment"]["needs_hook_event_update"])

    def test_ensure_codex_config_enables_hooks_feature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                result = codex_config_status.ensure_codex_config()
                status = codex_config_status.inspect_codex_config()
                text = (codex_home / "config.toml").read_text(encoding="utf-8")
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(result["modified"])
        self.assertTrue(status["hooks_enabled"])
        self.assertIn("[features]", text)
        self.assertIn("hooks = true", text)
        self.assertNotIn("codex_hooks = true", text)

    def test_ensure_codex_config_updates_existing_features_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            config_path = codex_home / "config.toml"
            config_path.write_text(
                'sandbox_mode = "workspace-write"\n\n[features]\nmemories = true\ncodex_hooks = false\n',
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                result = codex_config_status.ensure_codex_config()
                status = codex_config_status.inspect_codex_config()
                text = config_path.read_text(encoding="utf-8")
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(result["modified"])
        self.assertTrue(status["hooks_enabled"])
        self.assertIn('sandbox_mode = "workspace-write"', text)
        self.assertIn("memories = true", text)
        self.assertIn("hooks = true", text)
        self.assertNotIn("codex_hooks = false", text)
        self.assertNotIn("codex_hooks = true", text)

    def test_ensure_codex_config_preserves_existing_dotted_features_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            config_path = codex_home / "config.toml"
            config_path.write_text(
                'sandbox_mode = "workspace-write"\nfeatures.memories = true\n',
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                result = codex_config_status.ensure_codex_config()
                status = codex_config_status.inspect_codex_config()
                text = config_path.read_text(encoding="utf-8")
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(result["modified"])
        self.assertEqual(result["error"], "")
        self.assertTrue(status["hooks_enabled"])
        self.assertIn("features.memories = true", text)
        self.assertIn("features.hooks = true", text)
        self.assertNotIn("features.codex_hooks = true", text)
        self.assertNotIn("[features]", text)

    def test_ensure_codex_config_does_not_rewrite_invalid_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            config_path = codex_home / "config.toml"
            original = "[features\nhooks = false\n"
            config_path.write_text(original, encoding="utf-8")
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                result = codex_config_status.ensure_codex_config()
                text = config_path.read_text(encoding="utf-8")
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertFalse(result["modified"])
        self.assertTrue(result["error"])
        self.assertEqual(text, original)

    def test_bootstrap_doctor_recommends_official_hook_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            temp_root = Path(temp_dir)
            codex_home = temp_root / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                'sandbox_mode = "danger-full-access"\napproval_policy = "never"\n',
                encoding="utf-8",
            )
            (codex_home / "AGENTS.md").write_text(
                "Codex Memory\ncodex memory doctor\n",
                encoding="utf-8",
            )
            project_root = temp_root / "project"
            (project_root / ".codex" / "memories").mkdir(parents=True)
            harness_dir = project_root / ".codex" / "harness"
            harness_dir.mkdir(parents=True)
            (harness_dir / "commands.json").write_text("{}", encoding="utf-8")
            (harness_dir / "project_profile.json").write_text("{}", encoding="utf-8")
            home_marketplace = temp_root / "marketplace.json"
            home_marketplace.write_text(
                '{"plugins": [{"name": "codex-memory"}]}',
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                with (
                    mock.patch.object(codex_bootstrap, "HOME_PLUGIN", codex_bootstrap._plugin_root()),
                    mock.patch.object(codex_bootstrap, "HOME_MARKETPLACE", home_marketplace),
                ):
                    result = codex_bootstrap.inspect_state(project_root, init=False)
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertFalse(result["codex"]["native_integration"]["hooks_enabled"])
        self.assertTrue(
            any("features] hooks" in item for item in result["recommendations"])
        )
        self.assertTrue(
            any("danger-full-access" in item for item in result["recommendations"])
        )

    def test_ensure_codex_config_replaces_deprecated_dotted_codex_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_codex_home = os.environ.get("CODEX_HOME")
            codex_home = Path(temp_dir) / "codex-home"
            codex_home.mkdir()
            config_path = codex_home / "config.toml"
            config_path.write_text(
                "features.memories = true\nfeatures.codex_hooks = true\n",
                encoding="utf-8",
            )
            try:
                os.environ["CODEX_HOME"] = str(codex_home)
                result = codex_config_status.ensure_codex_config()
                status = codex_config_status.inspect_codex_config()
                text = config_path.read_text(encoding="utf-8")
            finally:
                _restore_env("CODEX_HOME", old_codex_home)

        self.assertTrue(result["modified"])
        self.assertTrue(status["hooks_enabled"])
        self.assertIn("features.hooks = true", text)
        self.assertNotIn("features.codex_hooks", text)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
