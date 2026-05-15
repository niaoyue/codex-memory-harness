from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import hook_runner
import memory_store
import workspace_runtime_policy
import workspace_router


POLICY = {
    "execution_model": "host_subagent_or_manual",
    "autostart": False,
    "task_types": ["implementation"],
    "risk_levels": ["medium", "high"],
    "reason": "Configured project policy requires host SubAgent dispatch.",
}


class SubagentRuntimePolicyConfigTests(unittest.TestCase):
    def test_project_profile_policy_is_injected_into_single_project_route_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _backoffice_project(root)
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": POLICY})

            plan = workspace_router.build_route_plan(root, _implementation_task(), max_depth=1)

        self.assertEqual(plan["mode"], "single_project")
        self.assertEqual(plan["subagent_runtime_policy"]["execution_model"], "host_subagent_or_manual")
        self.assertFalse(plan["subagent_runtime_policy"]["autostart"])
        self.assertEqual(plan["subagent_runtime_policy"]["reason"], POLICY["reason"])

    def test_workspace_routing_policy_is_injected_into_single_project_route_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / ".codex" / "harness" / "workspace-routing.json", _workspace_config(POLICY))

            plan = workspace_router.build_route_plan(
                root,
                {**_implementation_task(), "project_id": "dictionary-web"},
                max_depth=1,
            )

        self.assertEqual(plan["affected_projects"], ["dictionary-web"])
        self.assertEqual(plan["subagent_runtime_policy"]["execution_model"], "host_subagent_or_manual")

    def test_project_policy_single_route_generates_host_spawn_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _backoffice_project(root)
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": POLICY})
            with _memory_env(root):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event("before_task", _implementation_task())

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["trigger"], "route_policy")
        self.assertTrue(runtime["host_dispatch_allowed"])
        self.assertTrue(runtime["dispatch_plan_required"])
        self.assertEqual(runtime["main_agent_action"], "read_dispatch_plan_and_call_host_subagents")
        self.assertGreater(runtime["host_spawn_request_count"], 0)
        self.assertTrue(routing["subagent_dispatch_plan"]["host_spawn_requests"])

    def test_disabled_project_policy_keeps_complex_task_serial(self) -> None:
        policy = {
            "enabled": False,
            "execution_model": "host_subagent_or_manual",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Project owner disabled SubAgent runtime.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _backoffice_project(root)
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": policy})
            with _memory_env(root):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        **_implementation_task(),
                        "objective": "生成一个完整词典应用，包含查词、收藏和复习工作流",
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["status"], "main_agent_serial")
        self.assertEqual(runtime["trigger"], "policy_disabled")
        self.assertEqual(runtime["execution_model"], "main_agent_serial")
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["dispatch_plan_required"])
        self.assertNotIn("subagent_dispatch_plan", routing)

    def test_main_agent_serial_policy_keeps_high_risk_task_serial(self) -> None:
        policy = {
            "execution_model": "main_agent_serial",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Project owner requires main Agent serial execution.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _backoffice_project(root)
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": policy})
            with _memory_env(root):
                runner = hook_runner.HookRunner(memory_store=memory_store.MemoryStore())
                result = runner.run_event(
                    "before_task",
                    {
                        **_implementation_task(),
                        "objective": "Refactor cache framework when data refresh finishes and preserve existing behavior.",
                        "acceptance": ["Cache refresh preserves existing behavior."],
                        "architecture": ["Limit the change to cache framework boundaries."],
                    },
                )

        routing = result["result"]["task_state"]["metadata"]["workspace_routing"]
        runtime = routing["subagent_runtime"]
        self.assertEqual(runtime["status"], "main_agent_serial")
        self.assertEqual(runtime["trigger"], "policy_disabled")
        self.assertFalse(runtime["host_dispatch_allowed"])
        self.assertFalse(runtime["dispatch_plan_required"])
        self.assertNotIn("subagent_dispatch_plan", routing)

    def test_policy_selectors_do_not_apply_to_non_matching_task_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _backoffice_project(root)
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": POLICY})

            plan = workspace_router.build_route_plan(
                root,
                {
                    "task_id": "docs-only",
                    "objective": "Update docs for dictionary cache behavior",
                    "working_set": ["docs/cache.md"],
                },
                max_depth=1,
            )

        self.assertEqual(plan["task_type"], "docs")
        self.assertNotIn("subagent_runtime_policy", plan)

    def test_project_profile_policy_is_read_from_parent_when_cwd_is_child(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            child = root / "src"
            child.mkdir(parents=True)
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": POLICY})

            policy = workspace_runtime_policy.select_runtime_policy(
                child,
                {
                    "task_type": "implementation",
                    "risk_level": "medium",
                    "mode": "single_project",
                    "affected_projects": ["dictionary-web"],
                },
                _implementation_task(),
            )

        self.assertEqual(policy["execution_model"], "host_subagent_or_manual")
        self.assertEqual(policy["reason"], POLICY["reason"])

    def test_host_subagent_required_policy_is_accepted_and_autostarts(self) -> None:
        required_policy = {
            "execution_model": "host_subagent_required",
            "task_types": ["implementation"],
            "risk_levels": ["medium"],
            "reason": "OpenSpec execution requires host SubAgent dispatch.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": required_policy})

            policy = workspace_runtime_policy.select_runtime_policy(
                root,
                {
                    "task_type": "implementation",
                    "risk_level": "medium",
                    "mode": "single_project",
                    "affected_projects": ["dictionary-web"],
                },
                _implementation_task(),
            )

        self.assertEqual(policy["execution_model"], "host_subagent_required")
        self.assertTrue(policy["autostart"])
        self.assertEqual(policy["reason"], required_policy["reason"])

    def test_affected_child_project_profile_policy_is_injected_from_route_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = root / "client"
            _write_text(client / "Assets" / "Login.cs", "public class Login {}\n")
            _write_text(client / "ProjectSettings" / "ProjectVersion.txt", "m_EditorVersion: 2022\n")
            _write_json(client / "Packages" / "manifest.json", {"dependencies": {}})
            _write_json(client / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": POLICY})

            plan = workspace_router.build_route_plan(
                root,
                {
                    **_implementation_task(),
                    "working_set": ["client/Assets/Login.cs"],
                },
                max_depth=2,
            )

        self.assertEqual(plan["affected_projects"], ["unity-client"])
        self.assertEqual(plan["subagent_runtime_policy"]["execution_model"], "host_subagent_or_manual")
        self.assertEqual(plan["subagent_runtime_policy"]["reason"], POLICY["reason"])

    def test_child_route_profile_policy_precedes_matching_root_profile_policy(self) -> None:
        root_policy = {
            "execution_model": "host_subagent_or_manual",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Root allows SubAgent runtime.",
        }
        child_policy = {
            "execution_model": "main_agent_serial",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Child project requires serial execution.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = root / "client"
            _write_text(client / "Assets" / "Login.cs", "public class Login {}\n")
            _write_text(client / "ProjectSettings" / "ProjectVersion.txt", "m_EditorVersion: 2022\n")
            _write_json(client / "Packages" / "manifest.json", {"dependencies": {}})
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": root_policy})
            _write_json(client / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": child_policy})

            plan = workspace_router.build_route_plan(
                root,
                {
                    **_implementation_task(),
                    "working_set": ["client/Assets/Login.cs"],
                },
                max_depth=2,
            )

        self.assertEqual(plan["affected_projects"], ["unity-client"])
        self.assertEqual(plan["subagent_runtime_policy"]["execution_model"], "main_agent_serial")
        self.assertEqual(plan["subagent_runtime_policy"]["reason"], child_policy["reason"])

    def test_child_profile_policy_precedes_root_profile_when_root_route_is_first(self) -> None:
        root_policy = {
            "execution_model": "host_subagent_or_manual",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Root allows SubAgent runtime.",
        }
        child_policy = {
            "enabled": False,
            "execution_model": "host_subagent_or_manual",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Child project disables SubAgent runtime.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            child = root / "client"
            _write_json(root / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": root_policy})
            _write_json(child / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": child_policy})

            policy = workspace_runtime_policy.select_runtime_policy(
                root,
                {
                    "task_type": "implementation",
                    "risk_level": "medium",
                    "mode": "multi_project_parallel",
                    "affected_projects": ["workspace-root", "unity-client"],
                    "routes": [
                        {"project_id": "workspace-root", "cwd": "."},
                        {"project_id": "unity-client", "cwd": "client"},
                    ],
                },
                _implementation_task(),
            )

        self.assertEqual(policy["execution_model"], "main_agent_serial")
        self.assertEqual(policy["reason"], child_policy["reason"])

    def test_child_route_profile_policy_precedes_workspace_level_policy(self) -> None:
        workspace_policy = {
            "execution_model": "host_subagent_or_manual",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Workspace default allows SubAgent runtime.",
        }
        child_policy = {
            "execution_model": "main_agent_serial",
            "task_types": ["implementation"],
            "risk_levels": ["medium", "high"],
            "reason": "Child project requires serial execution.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = root / "client"
            _write_text(client / "Assets" / "Login.cs", "public class Login {}\n")
            _write_text(client / "ProjectSettings" / "ProjectVersion.txt", "m_EditorVersion: 2022\n")
            _write_json(client / "Packages" / "manifest.json", {"dependencies": {}})
            _write_json(root / ".codex" / "harness" / "workspace-routing.json", {
                "version": 1,
                "workspace": {"name": "game"},
                "subagent_runtime_policy": workspace_policy,
            })
            _write_json(client / ".codex" / "harness" / "project_profile.json", {"version": 1, "subagent_runtime_policy": child_policy})

            plan = workspace_router.build_route_plan(
                root,
                {
                    **_implementation_task(),
                    "working_set": ["client/Assets/Login.cs"],
                },
                max_depth=2,
            )

        self.assertEqual(plan["affected_projects"], ["unity-client"])
        self.assertEqual(plan["subagent_runtime_policy"]["execution_model"], "main_agent_serial")
        self.assertEqual(plan["subagent_runtime_policy"]["reason"], child_policy["reason"])


def _implementation_task() -> dict[str, object]:
    return {
        "task_id": "dictionary-cache",
        "objective": "Update dictionary cache behavior when data is refreshed",
        "working_set": ["src/cache.ts"],
        "acceptance": ["Cache refresh uses the existing data source and keeps current UI behavior."],
    }


def _backoffice_project(root: Path) -> None:
    _write_json(root / "package.json", {"scripts": {"build": "vite build"}})
    _write_text(root / "vite.config.ts", "export default {}\n")
    _write_text(root / "src" / "cache.ts", "export const cache = new Map();\n")


def _workspace_config(policy: dict[str, object]) -> dict[str, object]:
    return {
        "version": 1,
        "workspace": {"name": "dictionary"},
        "subagent_runtime_policy": policy,
        "projects": [
            {
                "id": "dictionary-web",
                "path": ".",
                "cwd": ".",
                "domain": "backoffice_web",
                "rules": ["workspace/base", "backoffice/base", "web/base"],
                "verification_profiles": {"quick": "primary"},
            }
        ],
        "fallback": {"rules": ["workspace/generic"], "verification_profiles": ["primary"]},
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _memory_env:
    def __init__(self, root: Path) -> None:
        self.root = root

    def __enter__(self) -> None:
        self.old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        self.old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        os.environ["CODEX_MEMORY_SCOPE"] = "project"
        os.environ["CODEX_MEMORY_CWD"] = str(self.root)
        (self.root / ".codex").mkdir(exist_ok=True)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _restore_env("CODEX_MEMORY_SCOPE", self.old_scope)
        _restore_env("CODEX_MEMORY_CWD", self.old_cwd)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
