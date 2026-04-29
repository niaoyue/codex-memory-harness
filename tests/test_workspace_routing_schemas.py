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
        aggregation = _read_json(PROJECT_ROOT / "schemas" / "verification_aggregation.schema.json")
        routing_config = _read_json(PROJECT_ROOT / "schemas" / "workspace_routing_config.schema.json")

        self.assertIn("projects", inventory["required"])
        self.assertIn("routes", route_plan["required"])
        self.assertIn("confidence", route_plan["required"])
        self.assertIn("assigned_scope", binding["required"])
        self.assertIn("artifact_policy", binding["required"])
        self.assertIn("overall_status", aggregation["required"])
        self.assertIn("verification_plan", aggregation["required"])
        self.assertIn("memory_binding", inventory["$defs"])
        self.assertIn("memory_binding", route_plan["$defs"])
        self.assertIn("memory_binding", binding["$defs"])
        self.assertIn("$schema", routing_config["properties"])

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


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
