from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"

if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import distillation_store
import harness_controller
import init_storage
import memory_store
import sensitive_scan
import shared_memory
import task_spec


class ReviewFindingsRegressionTests(unittest.TestCase):
    def test_sanitizer_blocks_private_key_under_sensitive_key(self) -> None:
        result = sensitive_scan.sanitize_for_persistence(
            {
                "metadata": {
                    "private_key": (
                        "-----BEGIN PRIVATE KEY-----\n"
                        "sample-private-key-value\n"
                        "-----END PRIVATE KEY-----"
                    )
                }
            }
        )

        self.assertTrue(result.blocked)
        self.assertIn("private_key", result.report()["categories"])

    def test_sanitizer_redacts_full_quoted_secret_assignment(self) -> None:
        result = sensitive_scan.sanitize_for_persistence('password="abc def"')

        self.assertEqual(result.value, "password=[REDACTED]")
        self.assertNotIn("abc", result.value)
        self.assertNotIn("def", result.value)

    def test_sanitizer_redacts_full_unquoted_secret_assignment(self) -> None:
        result = sensitive_scan.sanitize_for_persistence("password: abc def")

        self.assertEqual(result.value, "password: [REDACTED]")
        self.assertNotIn("abc", result.value)
        self.assertNotIn("def", result.value)

    def test_sanitizer_redacts_json_quoted_secret_assignment(self) -> None:
        result = sensitive_scan.sanitize_for_persistence(
            '{"api_key": "sampletokenvalue12345"}'
        )

        self.assertEqual(json.loads(result.value), {"api_key": "[REDACTED]"})
        self.assertNotIn("sampletokenvalue12345", result.value)
        self.assertIn("api_key", result.report()["categories"])

    def test_sanitizer_redacts_non_bearer_authorization_header(self) -> None:
        result = sensitive_scan.sanitize_for_persistence(
            "Authorization: Basic dXNlcjpwYXNzd29yZA=="
        )

        self.assertEqual(result.value, "Authorization: [REDACTED]")
        self.assertNotIn("Basic", result.value)
        self.assertIn("authorization", result.report()["categories"])

    def test_sanitizer_redacts_standalone_bearer_token(self) -> None:
        result = sensitive_scan.sanitize_for_persistence(
            "curl output: Bearer sampletokenvalue12345"
        )

        self.assertEqual(result.value, "curl output: Bearer [REDACTED]")
        self.assertNotIn("sampletokenvalue12345", result.value)
        self.assertIn("bearer_token", result.report()["categories"])

    def test_sanitizer_does_not_redact_non_bearer_phrase(self) -> None:
        result = sensitive_scan.sanitize_for_persistence("Authorization non-Bearer credentials")

        self.assertEqual(result.value, "Authorization non-Bearer credentials")
        self.assertEqual(result.report()["finding_count"], 0)

    def test_sanitizer_accepts_redacted_authorization_header(self) -> None:
        result = sensitive_scan.sanitize_for_persistence("Authorization: [REDACTED]")

        self.assertEqual(result.value, "Authorization: [REDACTED]")
        self.assertEqual(result.report()["finding_count"], 0)

    def test_sanitizer_redacts_prefixed_env_secret_assignment(self) -> None:
        result = sensitive_scan.sanitize_for_persistence(
            "OPENAI_API_KEY=sk-sampletokenvalue12345"
        )

        self.assertEqual(result.value, "OPENAI_API_KEY=[REDACTED]")
        self.assertNotIn("sampletokenvalue12345", result.value)
        self.assertIn("openai_api_key", result.report()["categories"])

    def test_promoted_redacted_token_placeholder_validates(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = str(project_root)
                store = memory_store.MemoryStore()
                store.write_task_summary("task-token", "# Token Fact\n\ntoken=sampletokenvalue12345")

                shared_memory.promote_task(
                    project_root,
                    "task-token",
                    kind="fact",
                    title="Token Fact",
                )
                validation = shared_memory.validate_shared(project_root)

                self.assertTrue(validation["ok"], validation["failures"])
            finally:
                restore_env("CODEX_MEMORY_SCOPE", old_scope)
                restore_env("CODEX_MEMORY_CWD", old_cwd)

    def test_promote_sanitizes_title_before_shared_path_generation(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = str(project_root)
                store = memory_store.MemoryStore()
                store.write_task_summary("task-title-token", "# Safe Fact\n\nNo secret remains.")

                result = shared_memory.promote_task(
                    project_root,
                    "task-title-token",
                    kind="fact",
                    title="token=sampletokenvalue12345",
                )

                self.assertNotIn("sampletokenvalue12345", result["entry_id"])
                self.assertNotIn("sampletokenvalue12345", result["path"])
                self.assertIn("token-redacted", result["entry_id"])
            finally:
                restore_env("CODEX_MEMORY_SCOPE", old_scope)
                restore_env("CODEX_MEMORY_CWD", old_cwd)

    def test_shared_memory_project_root_resolves_from_child_directory(self) -> None:
        old_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir).resolve()
            child_dir = project_root / "docs"
            (project_root / ".codex" / "shared").mkdir(parents=True)
            child_dir.mkdir()
            try:
                os.chdir(child_dir)
                resolved_root = shared_memory._project_root(str(child_dir))
                validation = shared_memory.validate_shared(resolved_root)
            finally:
                os.chdir(old_cwd)

        self.assertEqual(resolved_root, project_root)
        self.assertTrue(validation["ok"], validation["failures"])
        self.assertFalse((child_dir / ".codex").exists())

    def test_shared_memory_validate_rejects_schema_invalid_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            path = project_root / ".codex" / "shared" / "facts" / "bad.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "\n".join(
                    [
                        "---",
                        "id: bad id",
                        "scope: project",
                        "status: proposed",
                        "confidence: medium",
                        "source: task:bad",
                        "updated_at: not-a-date",
                        "---",
                        "",
                        "# Bad",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            validation = shared_memory.validate_shared(project_root)

        errors = {item["error"] for item in validation["failures"]}
        self.assertFalse(validation["ok"])
        self.assertIn("invalid id", errors)
        self.assertIn("invalid updated_at", errors)

    def test_promote_restores_memory_environment(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as other_dir:
            project_root = Path(temp_dir).resolve()
            other_root = Path(other_dir).resolve()
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = str(project_root)
                store = memory_store.MemoryStore()
                store.write_task_summary("task-env", "# Env Safe\n\nNo shared secret.")

                os.environ["CODEX_MEMORY_SCOPE"] = "global"
                os.environ["CODEX_MEMORY_CWD"] = str(other_root)
                shared_memory.promote_task(
                    project_root,
                    "task-env",
                    kind="fact",
                    title="Env Safe",
                )

                self.assertEqual(os.environ.get("CODEX_MEMORY_SCOPE"), "global")
                self.assertEqual(os.environ.get("CODEX_MEMORY_CWD"), str(other_root))
            finally:
                restore_env("CODEX_MEMORY_SCOPE", old_scope)
                restore_env("CODEX_MEMORY_CWD", old_cwd)

    def test_distillation_sanitizes_derived_fields_before_persisting(self) -> None:
        old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        secret = "sampletokenvalue12345"
        raw_task_id = f"token={secret}"
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            Path(temp_dir, ".codex").mkdir()
            try:
                os.environ["CODEX_MEMORY_SCOPE"] = "project"
                os.environ["CODEX_MEMORY_CWD"] = str(project_root)
                with mock.patch.object(init_storage, "GLOBAL_STORAGE_DIR", project_root / ".codex" / "global"):
                    store = distillation_store.DistillationStore(
                        memory_store=FakeDistillationMemory(secret),
                        context_builder=FakeDistillationContext(secret),
                    )
                    result = store.distill_task(
                        task_id=raw_task_id,
                        queries=[f"token={secret}"],
                        asset_type=f"token={secret}",
                    )
                asset = result["asset"]
                paths = init_storage.resolve_storage_paths(scope="project", cwd=project_root)
                conn = sqlite3.connect(paths.db_path)
                try:
                    row = conn.execute(
                        """
                        SELECT task_id, asset_type, title, summary_text, file_path, tags_json, payload_json
                        FROM distilled_asset
                        """
                    ).fetchone()
                finally:
                    conn.close()
                db_payload = json.dumps(list(row), ensure_ascii=False)
                event_log = paths.event_log_path.read_text(encoding="utf-8")
                asset_file = Path(asset["file_path"])

                self.assertNotIn(secret, json.dumps(asset, ensure_ascii=False))
                self.assertNotIn(secret, json.dumps(result["context_pack"], ensure_ascii=False))
                self.assertNotIn(secret, db_payload)
                self.assertNotIn(secret, event_log)
                self.assertNotIn(secret, asset_file.name)
                self.assertNotIn(secret, asset_file.read_text(encoding="utf-8"))
                self.assertIsNotNone(store.get_distilled_asset(task_id=raw_task_id))
                self.assertEqual(len(store.list_distilled_assets(task_id=raw_task_id)), 1)
            finally:
                restore_env("CODEX_MEMORY_SCOPE", old_scope)
                restore_env("CODEX_MEMORY_CWD", old_cwd)

    def test_checkpoint_forwards_signals_to_after_tool_hook(self) -> None:
        captured: dict[str, object] = {}

        class FakeHookRunner:
            def run_event(self, event: str, payload: dict[str, object]) -> dict[str, object]:
                captured["event"] = event
                captured["payload"] = payload
                return {"ok": True}

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            spec = task_spec.TaskSpec(
                task_id="signal-task",
                objective="Capture signals",
                project_root=str(project_root),
            )
            spec.save(task_spec.task_spec_path(project_root, spec.task_id))
            payload = {
                "tool_name": "workspace_router",
                "phase": "verification",
                "summary": "Generated route plan",
                "dispatch_id": "dispatch-binding-client",
                "binding_id": "binding-client",
                "subagent_id": "agent-client",
                "project_id": "client-unity",
                "domain": "game_client",
                "assigned_scope": ["client/Assets"],
                "signals": {
                    "route_plan": {
                        "task_id": "signal-task",
                        "route_plan_id": "route-signal-task",
                    }
                },
            }
            args = argparse.Namespace(
                project_root=str(project_root),
                task_id=spec.task_id,
                result_file=None,
                payload_json=json.dumps(payload),
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=FakeHookRunner()):
                result = harness_controller.checkpoint_task(args)

        self.assertEqual(captured["event"], "after_tool")
        hook_payload = captured["payload"]
        self.assertEqual(
            hook_payload["signals"]["route_plan"]["route_plan_id"],
            "route-signal-task",
        )
        self.assertEqual(hook_payload["dispatch_id"], "dispatch-binding-client")
        self.assertEqual(hook_payload["binding_id"], "binding-client")
        self.assertEqual(hook_payload["project_id"], "client-unity")
        self.assertEqual(hook_payload["phase"], "verification")
        self.assertEqual(result["artifact"]["phase"], "verification")
        self.assertEqual(result["artifact"]["dispatch_id"], "dispatch-binding-client")
        self.assertEqual(result["artifact"]["subagent_id"], "agent-client")
        self.assertEqual(result["artifact"]["assigned_scope"], ["client/Assets"])
        self.assertEqual(result["artifact"]["signals"]["route_plan"]["task_id"], "signal-task")

    def test_checkpoint_preserves_sensitive_scan_report_on_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            spec = task_spec.TaskSpec(
                task_id="sensitive-checkpoint-task",
                objective="Capture sensitive scan",
                project_root=str(project_root),
            )
            spec.save(task_spec.task_spec_path(project_root, spec.task_id))
            args = argparse.Namespace(
                project_root=str(project_root),
                task_id=spec.task_id,
                result_file=None,
                payload_json=json.dumps(
                    {
                        "tool_name": "subagent",
                        "summary": "password=sampletokenvalue12345",
                        "binding_id": "binding-client",
                        "subagent_id": "agent-client",
                        "project_id": "client-unity",
                        "domain": "game_client",
                        "assigned_scope": ["client/Assets"],
                        "touched_paths": ["client/Assets/Login.cs"],
                    }
                ),
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=NoopHookRunner()):
                result = harness_controller.checkpoint_task(args)

        artifact = result["artifact"]
        self.assertIn("_sensitive_scan", artifact)
        self.assertTrue(artifact["_sensitive_scan"]["redacted"])
        self.assertNotIn("sampletokenvalue12345", json.dumps(artifact, ensure_ascii=False))

    def test_workspace_verification_checkpoint_sets_verifying_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            spec = task_spec.TaskSpec(
                task_id="verify-task",
                objective="Verify workspace",
                project_root=str(project_root),
            )
            spec.save(task_spec.task_spec_path(project_root, spec.task_id))
            args = argparse.Namespace(
                project_root=str(project_root),
                task_id=spec.task_id,
                result_file=None,
                payload_json=json.dumps(
                    {
                        "tool_name": "workspace_verifier",
                        "phase": "workspace_verification",
                        "summary": "Workspace verification aggregation status: blocked.",
                        "signals": {"verification_aggregation": {"overall_status": "blocked"}},
                    }
                ),
            )

            with mock.patch.object(harness_controller, "HookRunner", return_value=NoopHookRunner()):
                result = harness_controller.checkpoint_task(args)
            state = json.loads(task_spec.run_state_path(project_root, spec.task_id).read_text(encoding="utf-8"))

        self.assertEqual(result["task_spec"]["status"], "verifying")
        self.assertEqual(state["status"], "verifying")


def restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


class NoopHookRunner:
    def run_event(self, event: str, payload: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "event": event, "payload": payload}


class FakeDistillationMemory:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def get_task_state(self, task_id: str | None = None) -> dict[str, object]:
        return {
            "task_id": task_id,
            "objective": f"token={self.secret}",
            "status": "done",
            "next_step": f"token={self.secret}",
            "working_set": ["client/login.cs"],
        }

    def get_task_summary(self, task_id: str | None = None) -> dict[str, object]:
        return {"task_id": task_id, "summary_markdown": f"# Summary\n\ntoken={self.secret}"}

    def list_repo_decisions(self, *, task_id: str | None = None, limit: int = 20) -> list[dict[str, object]]:
        return [{"title": f"token={self.secret}", "details": f"token={self.secret}"}]


class FakeDistillationContext:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def build_context_pack(self, **kwargs: object) -> dict[str, object]:
        return {
            "task_id": kwargs.get("task_id"),
            "evidence_queries": [f"token={self.secret}"],
            "rendered_context": f"token={self.secret}",
        }


if __name__ == "__main__":
    unittest.main()
