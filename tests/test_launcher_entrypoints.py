from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import install_support
import profile_blocks


class LauncherEntrypointTests(unittest.TestCase):
    def test_project_template_prefers_codex_entrypoints(self) -> None:
        template = json.loads(
            (PROJECT_ROOT / "templates" / "project" / ".codex" / "harness" / "commands.json").read_text(
                encoding="utf-8",
            )
        )

        commands = template["commands"]
        self.assertEqual(commands["memory_check"]["command"], "codex memory check-install")
        self.assertEqual(commands["bootstrap_doctor"]["command"], "codex memory doctor")
        self.assertNotIn("py -X utf8", json.dumps(template))

    def test_generated_profile_routes_doctor_through_memory_subcommand(self) -> None:
        block = profile_blocks.profile_block(Path("C:/Users/Test/plugins/codex-memory"))

        self.assertIn("function codex", block)
        self.assertIn("function codexm", block)
        self.assertIn("memory doctor", block)

    def test_generated_posix_profile_routes_codex_memory_subcommand(self) -> None:
        block = profile_blocks.posix_profile_block(Path("/home/test/plugins/codex-memory"))

        self.assertIn("codexm()", block)
        self.assertIn("codex()", block)
        self.assertIn("codexm.sh", block)
        self.assertIn("codex-memory-doctor", block)
        self.assertIn("memory doctor", block)

    def test_generated_agents_prefers_codex_memory_commands(self) -> None:
        block = install_support.agents_block(Path("C:/Users/Test/plugins/codex-memory"))

        self.assertIn("codex memory doctor", block)
        self.assertIn("codex memory init", block)
        self.assertIn("codex harness verify run --profile primary", block)
        self.assertIn("codex package verify", block)
        self.assertIn("codex xhigh review --commit $commitSha", block)
        self.assertIn("timeout 只能作为本次观察窗口", block)
        self.assertIn("不得仅因观察窗口到期而中断", block)
        self.assertIn("stdout/stderr 进度输出观察", block)
        self.assertIn("subagent_dispatch_plan.host_spawn_requests", block)
        self.assertIn("host_dispatch_allowed=true", block)
        self.assertIn("subagent_runtime.recommended=true", block)
        self.assertIn("spawn_agent", block)
        self.assertIn("actual_subagents=0", block)
        self.assertIn("不得只生成 dispatch plan", block)
        self.assertIn("复杂/应用级/多阶段实现", block)
        self.assertIn("hook_launcher.ps1", block)
        self.assertIn("hook_launcher.sh", block)
        self.assertIn("Get-Command pwsh -ErrorAction SilentlyContinue", block)
        self.assertIn("if (-not $POWERSHELL)", block)
        self.assertIn("Get-Command powershell -ErrorAction Stop", block)
        self.assertIn("--event before_task", block)
        self.assertIn("--payload-file <payload.json>", block)
        self.assertIn("codex memory hook ...", block)
        self.assertIn("codex-memory-harness", block)
        self.assertIn("memories", block)
        self.assertIn("官方 Codex Memories", block)
        self.assertIn("~/.agents/skills", block)
        self.assertIn("bundled-skills.json", block)
        self.assertIn("需求澄清", block)
        self.assertIn("接口设计", block)
        self.assertIn("release gate", block)
        self.assertIn("TDD", block)
        self.assertNotIn("codex_bootstrap.py --cwd", block)

    def test_launcher_declares_memory_command_dispatcher(self) -> None:
        launcher = (PLUGIN_SCRIPTS_DIR / "codexm.ps1").read_text(encoding="utf-8")
        workspace_helper = (PLUGIN_SCRIPTS_DIR / "codexm_workspace.ps1").read_text(encoding="utf-8")
        powershell_dispatch = launcher + "\n" + workspace_helper

        self.assertIn("function Invoke-MemoryCommand", launcher)
        self.assertIn("function Invoke-HarnessCommand", launcher)
        self.assertIn("function Invoke-PackageCommand", launcher)
        self.assertIn("function Invoke-WorkspaceCommand", workspace_helper)
        self.assertIn("function Invoke-ReviewCommand", launcher)
        self.assertIn("function Resolve-CodexReviewAlias", launcher)
        self.assertIn("review_workflow.py", launcher)
        self.assertIn("review_gate_runner.py", launcher)
        self.assertIn("--idle-seconds", launcher)
        self.assertIn("$ReviewGateIdleSeconds = 1800", launcher)
        self.assertIn("--max-seconds", launcher)
        self.assertIn('"0"', launcher)
        self.assertIn('@("Application", "ExternalScript")', launcher)
        self.assertIn('model_reasoning_effort=`"$effort`"', launcher)
        self.assertIn("codex xhigh review --commit <commit-sha>", launcher)
        self.assertIn("codex memory migrate-legacy-global", launcher)
        self.assertIn("codex workspace schedule", launcher)
        self.assertIn("codex workspace game-client", launcher)
        self.assertIn("write-guard --session-id", launcher)
        self.assertIn("worktree list|prune --dry-run|--confirm|recover <binding-id>", launcher)
        self.assertIn("workspace_session.py", powershell_dispatch)
        self.assertIn("workspace_business_templates.py", powershell_dispatch)
        self.assertIn("project-template", powershell_dispatch)
        self.assertIn('"write-guard"', powershell_dispatch)
        self.assertIn('"session"', powershell_dispatch)
        self.assertIn('"worktree"', powershell_dispatch)
        self.assertIn('"verify"', powershell_dispatch)
        self.assertIn('"harness"', launcher)
        self.assertIn('"hook"', launcher)
        self.assertIn("function Resolve-PythonRuntime", launcher)
        self.assertIn("python3", launcher)
        self.assertNotIn("& py -X utf8", launcher)

    def test_posix_launcher_declares_memory_command_dispatcher(self) -> None:
        launcher = (PLUGIN_SCRIPTS_DIR / "codexm.sh").read_text(encoding="utf-8")

        self.assertIn("invoke_memory()", launcher)
        self.assertIn("invoke_harness()", launcher)
        self.assertIn("invoke_package()", launcher)
        self.assertIn("invoke_review()", launcher)
        self.assertIn("review_gate_runner.py", launcher)
        self.assertIn("review_workflow.py", launcher)
        self.assertIn("--idle-seconds", launcher)
        self.assertIn("REVIEW_GATE_IDLE_SECONDS=1800", launcher)
        self.assertIn("--max-seconds", launcher)
        self.assertIn("codex memory hook <event>", launcher)
        self.assertIn("game-client", launcher)
        self.assertIn("write-guard --session-id", launcher)
        self.assertIn("worktree recover <binding-id>", launcher)
        self.assertIn("workspace_session.py", launcher)
        self.assertIn("workspace_business_templates.py", launcher)
        self.assertIn("project-template", launcher)
        self.assertIn("hook)", launcher)
        self.assertIn("try_python python3", launcher)
        self.assertIn("invoke_bootstrap", launcher)
        self.assertIn("CODEX_MEMORY_SCOPE_VALUE", launcher)
        self.assertIn("CODEX_MEMORY_DISABLE_WRAPPER", launcher)
        self.assertNotIn("powershell", launcher.lower())

    def test_install_script_passes_selected_python_runtime_to_mcp_config(self) -> None:
        installer = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")

        self.assertIn("--mcp-python-command", installer)
        self.assertIn("$PythonRuntime.Name", installer)
        self.assertIn("--mcp-python-prefix-arg", installer)

    def test_launcher_respects_disable_wrapper_before_memory_dispatch(self) -> None:
        launcher = (PLUGIN_SCRIPTS_DIR / "codexm.ps1").read_text(encoding="utf-8")

        disable_check = 'if ($env:CODEX_MEMORY_DISABLE_WRAPPER -eq "1")'
        memory_dispatch = 'if ($CodexArgs.Count -gt 0 -and $CodexArgs[0].ToLowerInvariant() -eq "memory")'
        self.assertLess(launcher.index(disable_check), launcher.index(memory_dispatch))
        self.assertIn("project_shared_exists", launcher)
        self.assertIn("project_shared_index_exists", launcher)

    def test_launcher_only_intercepts_harness_review_subcommands(self) -> None:
        powershell_launcher = (PLUGIN_SCRIPTS_DIR / "codexm.ps1").read_text(encoding="utf-8")
        posix_launcher = (PLUGIN_SCRIPTS_DIR / "codexm.sh").read_text(encoding="utf-8")

        self.assertIn("function Is-HarnessReviewCommand", powershell_launcher)
        self.assertIn('"preflight"', powershell_launcher)
        self.assertIn('Invoke-RealCodex -Arguments (Resolve-CodexReviewAlias -Arguments $CodexArgs)', powershell_launcher)
        self.assertIn("is_harness_review_command()", posix_launcher)
        self.assertIn("invoke_real_codex \"$@\"", posix_launcher)
        self.assertIn("review)", posix_launcher)

    def test_launcher_restores_review_gate_env_after_xhigh_alias(self) -> None:
        launcher = (PLUGIN_SCRIPTS_DIR / "codexm.ps1").read_text(encoding="utf-8")

        self.assertIn('$oldReviewGateRunning = [Environment]::GetEnvironmentVariable($ReviewGateRunningEnv, "Process")', launcher)
        self.assertIn(
            '$oldXHighDispatchDisable = [Environment]::GetEnvironmentVariable($XHighReviewDispatchDisableEnv, "Process")',
            launcher,
        )
        self.assertIn("} finally {", launcher)
        self.assertIn(
            '[Environment]::SetEnvironmentVariable($ReviewGateRunningEnv, $oldReviewGateRunning, "Process")',
            launcher,
        )
        self.assertIn(
            '[Environment]::SetEnvironmentVariable($XHighReviewDispatchDisableEnv, $oldXHighDispatchDisable, "Process")',
            launcher,
        )
        self.assertIn("exit $exitCode", launcher)


if __name__ == "__main__":
    unittest.main()
