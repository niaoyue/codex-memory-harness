from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_release


SCHEMA_FILES = [
    "workspace_project_inventory.schema.json",
    "workspace_route_plan.schema.json",
    "subagent_route_binding.schema.json",
    "subagent_dispatch_plan.schema.json",
    "verification_aggregation.schema.json",
    "workspace_routing_config.schema.json",
]


class WorkspaceRoutingSchemaTests(unittest.TestCase):
    def test_workspace_routing_schemas_are_valid_json_with_local_ids(self) -> None:
        for name in SCHEMA_FILES:
            schema = _read_json(PROJECT_ROOT / "schemas" / name)

            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["$id"], f"local://codex-memory-harness/schemas/{name}")
            self.assertEqual(schema["type"], "object")

    def test_schema_required_fields_cover_runtime_contracts(self) -> None:
        inventory = _read_json(PROJECT_ROOT / "schemas" / "workspace_project_inventory.schema.json")
        route_plan = _read_json(PROJECT_ROOT / "schemas" / "workspace_route_plan.schema.json")
        binding = _read_json(PROJECT_ROOT / "schemas" / "subagent_route_binding.schema.json")
        dispatch = _read_json(PROJECT_ROOT / "schemas" / "subagent_dispatch_plan.schema.json")
        aggregation = _read_json(PROJECT_ROOT / "schemas" / "verification_aggregation.schema.json")
        routing_config = _read_json(PROJECT_ROOT / "schemas" / "workspace_routing_config.schema.json")

        self.assertIn("projects", inventory["required"])
        self.assertIn("routes", route_plan["required"])
        self.assertIn("confidence", route_plan["required"])
        self.assertIn("workspace_root", route_plan["properties"])
        self.assertIn("requirements_gate", route_plan["properties"])
        self.assertNotIn("requirements_gate", route_plan["required"])
        self.assertIn("subagent_runtime_policy", route_plan["properties"])
        self.assertNotIn("subagent_runtime_policy", route_plan["required"])
        self.assertIn("assigned_scope", binding["required"])
        self.assertIn("artifact_policy", binding["required"])
        self.assertIn("requirements_gate_enforcement", binding["properties"])
        self.assertIn("write_blocked", binding["properties"]["permissions"]["properties"])
        self.assertIn("write_block_reason", binding["properties"]["permissions"]["properties"])
        self.assertEqual(
            binding["$defs"]["requirements_gate_enforcement"]["properties"]["status"]["const"],
            "blocked_by_requirements_gate",
        )
        self.assertIn("host_spawn_requests", dispatch["required"])
        self.assertIn("dispatch_required", dispatch["properties"])
        self.assertIn(
            "host_subagent_required",
            dispatch["properties"]["execution_model"]["enum"],
        )
        self.assertIn(
            "host_subagent_required",
            route_plan["$defs"]["subagent_runtime_policy"]["properties"]["execution_model"]["enum"],
        )
        self.assertIn(
            "host_subagent_required",
            routing_config["$defs"]["subagent_runtime_policy"]["properties"]["execution_model"]["enum"],
        )
        spawn = dispatch["$defs"]["host_spawn_request"]
        self.assertIn("total_timeout_policy", spawn["required"])
        self.assertEqual(spawn["properties"]["total_timeout_policy"]["enum"], ["none"])
        self.assertIn("review_commit_ref", spawn["properties"])
        self.assertIn("poll_only_never_interrupt", spawn["properties"]["observation_window_policy"]["enum"])
        self.assertEqual(spawn["properties"]["no_fixed_total_timeout"]["const"], True)
        recovery = spawn["properties"]["recoverable_failure_policy"]
        self.assertEqual(recovery["properties"]["primary_action"]["enum"], ["send_input_to_active_review_runner"])
        self.assertIn("primary_preconditions", recovery["required"])
        preconditions = recovery["properties"]["primary_preconditions"]["items"]["enum"]
        self.assertIn("review_commit_ref_unchanged_since_runner_start", preconditions)
        self.assertIn("reviewed_commit_unchanged_since_runner_start", preconditions)
        self.assertNotIn("workspace_diff_unchanged_since_runner_start", preconditions)
        restart_conditions = recovery["properties"]["restart_only_when"]["items"]["enum"]
        self.assertIn("review_commit_ref_changed_during_review", restart_conditions)
        self.assertIn("reviewed_commit_changed_during_review", restart_conditions)
        self.assertNotIn("workspace_diff_changed_during_review", restart_conditions)
        self.assertIn("failure_rules", recovery["required"])
        failure_rule = recovery["properties"]["failure_rules"]["items"]
        self.assertIn("max_resume_attempts", failure_rule["required"])
        self.assertIn("null", failure_rule["properties"]["max_resume_attempts"]["type"])
        self.assertIn("attempt_policy", failure_rule["properties"])
        self.assertIn("while_session_active", failure_rule["properties"]["attempt_policy"]["enum"])
        self.assertIn("single_retry", failure_rule["properties"]["attempt_policy"]["enum"])
        self.assertIn("http_429", failure_rule["properties"]["failure_type"]["enum"])
        self.assertIn("http_5xx", failure_rule["properties"]["failure_type"]["enum"])
        self.assertIn("timeout", failure_rule["properties"]["failure_type"]["enum"])
        self.assertEqual(recovery["properties"]["restart_action"]["enum"], ["restart_same_review_gate_command"])
        self.assertEqual(recovery["properties"]["pass_condition"]["enum"], ["review_gate_must_complete_cleanly"])
        self.assertIn("overall_status", aggregation["required"])
        self.assertIn("verification_plan", aggregation["required"])
        self.assertIn(
            "verification_cwd",
            routing_config["$defs"]["project_config"]["properties"],
        )
        self.assertIn("verification_cwd", inventory["$defs"]["project"]["properties"])
        self.assertIn("verification_cwd", route_plan["$defs"]["route"]["properties"])
        self.assertIn("verification_cwd", route_plan["$defs"]["verification_target"]["properties"])
        self.assertIn("verification_cwd", aggregation["$defs"]["verification_target"]["properties"])
        gate_properties = aggregation["$defs"]["gate_result"]["properties"]
        self.assertIn("scanned_files", gate_properties)
        self.assertIn("findings", gate_properties)
        self.assertIn("truncated", gate_properties)
        self.assertIn("memory_binding", inventory["$defs"])
        self.assertIn("memory_binding", route_plan["$defs"])
        self.assertIn("memory_binding", binding["$defs"])
        self.assertIn("$schema", routing_config["properties"])
        self.assertIn("subagent_runtime_policy", routing_config["properties"])
        self.assertIn("subagent_runtime_policy", routing_config["$defs"]["project_config"]["properties"])

    def test_workspace_routing_template_matches_schema_entrypoint(self) -> None:
        template = _read_json(
            PROJECT_ROOT / "templates" / "project" / ".codex" / "harness" / "workspace-routing.json"
        )
        schema = _read_json(PROJECT_ROOT / "schemas" / "workspace_routing_config.schema.json")

        self.assertEqual(
            template["$schema"],
            "local://codex-memory-harness/schemas/workspace_routing_config.schema.json",
        )
        self.assertFalse(set(template) - set(schema["properties"]))
        self.assertEqual(template["version"], 1)
        self.assertIn("projects", template)
        self.assertIn("fallback", template)
        self.assertIn("subagent_runtime_policy", template)
        self.assertEqual(template["subagent_runtime_policy"]["execution_model"], "host_subagent_or_manual")
        project_ids = [project["id"] for project in template["projects"]]
        self.assertEqual(len(project_ids), len(set(project_ids)))

        domains = {project["domain"] for project in template["projects"]}
        self.assertIn("game_client", domains)
        self.assertIn("game_server", domains)
        self.assertIn("backoffice_web", domains)
        self.assertIn("design_docs", domains)
        self.assertIn("art_pipeline", domains)

        client_engines = {
            project["engine"]
            for project in template["projects"]
            if project["domain"] == "game_client"
        }
        self.assertEqual(client_engines, {"unity", "laya", "cocos"})
        self.assertIn("primary", template["fallback"]["verification_profiles"])

    def test_release_package_includes_workspace_routing_contract_files(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            package_path = build_release.build(Path(output_dir))
            with zipfile.ZipFile(package_path) as archive:
                names = set(archive.namelist())

        for name in SCHEMA_FILES:
            self.assertIn(f"schemas/{name}", names)
        self.assertIn("templates/project/.codex/harness/workspace-routing.json", names)

    def test_blocking_requirements_gate_uses_schema_fallback_action_value(self) -> None:
        schema = _read_json(PROJECT_ROOT / "schemas" / "workspace_route_plan.schema.json")
        plan = {
            "version": 1,
            "task_id": "blocking-gate",
            "mode": "single_project",
            "affected_projects": ["unity-client"],
            "routes": [],
            "risk_level": "medium",
            "requirements_gate": {
                "version": 1,
                "task_intent": "feature_story",
                "status": "needs_clarification",
                "blocking": True,
                "requirement_sources": [],
                "missing": [{"field": "acceptance_criteria", "reason": "missing"}],
                "open_questions": ["本任务完成后按哪些验收条件判断通过？"],
                "assumptions_policy": "Ask first.",
                "technical_decision_policy": "Follow existing conventions.",
                "assumptions": [],
                "missing_requirements": [{"field": "acceptance_criteria", "reason": "missing"}],
                "logical_conflicts": [],
                "acceptance_gaps": ["missing"],
                "scope_gaps": [],
                "non_goals": [],
                "implementation_spec_mismatches": [],
                "safety_security_migration_rollback_gaps": [],
                "product_requirement_questions": [],
                "technical_decision_basis": [],
                "test_plan_gaps": [],
                "platform_constraint_gaps": [],
                "performance_package_constraints": [],
                "asset_bundle_constraints": [],
                "recommended_next_step": "Ask the user to resolve missing requirements before implementation.",
            },
            "confidence": 0.9,
            "reasons": ["test"],
            "fallback_action": "ask_user",
        }

        self.assert_route_plan_contract_accepts(schema, plan)

    def assert_route_plan_contract_accepts(self, schema: dict[str, object], plan: dict[str, object]) -> None:
        self.assertFalse(set(schema["required"]) - set(plan))
        self.assertIn(plan["fallback_action"], schema["properties"]["fallback_action"]["enum"])
        if "subagent_runtime_policy" in plan:
            policy_schema = schema["$defs"]["subagent_runtime_policy"]
            policy = plan["subagent_runtime_policy"]
            self.assertFalse(set(policy_schema["required"]) - set(policy))
            self.assertIn(policy["execution_model"], policy_schema["properties"]["execution_model"]["enum"])
        gate_schema = schema["$defs"]["requirements_gate"]
        gate = plan["requirements_gate"]
        self.assertFalse(set(gate_schema["required"]) - set(gate))
        self.assertIn(gate["task_intent"], gate_schema["properties"]["task_intent"]["enum"])
        self.assertIn(gate["status"], gate_schema["properties"]["status"]["enum"])


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
