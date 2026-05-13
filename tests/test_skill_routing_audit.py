from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import skill_routing_audit  # noqa: E402


class SkillRoutingAuditTests(unittest.TestCase):
    def test_matches_manifest_driven_skills_from_task_text(self) -> None:
        manifest = {
            "version": 1,
            "skills": [
                {
                    "name": "design-an-interface",
                    "source_group": "local",
                    "trigger_keywords": ["interface", "接口"],
                },
                {
                    "name": "openai-docs",
                    "source_group": "local",
                    "trigger_keywords": ["openai"],
                },
            ],
        }

        audit = skill_routing_audit.match_task_skills(
            task_id="skill-audit",
            task={"objective": "Design an interface for a plugin API", "working_set": []},
            manifest=manifest,
        )

        names = {item["name"] for item in audit["skills"]}
        self.assertEqual(names, {"design-an-interface"})
        self.assertEqual(audit["summary"]["matched_count"], 1)
        self.assertFalse(audit["summary"]["degraded"])

    def test_records_used_and_renders_skipped_for_unrecorded_matches(self) -> None:
        audit = skill_routing_audit.match_task_skills(
            task_id="skill-audit",
            task={"objective": "Design an interface and use TDD tests", "working_set": []},
            manifest={
                "version": 1,
                "skills": [
                    {"name": "design-an-interface", "source_group": "local", "trigger_keywords": ["interface"]},
                    {"name": "tdd", "source_group": "local", "trigger_keywords": ["tdd", "tests"]},
                ],
            },
        )
        audit = skill_routing_audit.record_skill_decision(
            audit=audit,
            skill_name="design-an-interface",
            decision="used",
            reason="read_skill_and_applied_interface_evaluation",
        )

        brief = skill_routing_audit.render_skill_audit(audit=audit, target="brief")["brief"]

        self.assertTrue(any("used: design-an-interface" in line for line in brief))
        self.assertTrue(any("tdd(not_recorded_as_used)" in line for line in brief))

    def test_merge_payload_decisions_accepts_checkpoint_signal(self) -> None:
        incoming = {
            "signals": {
                "skill_routing_audit": {
                    "skills": [
                        {
                            "name": "git-safe-commit",
                            "status": "skipped",
                            "skip_reason": "no_commit_requested",
                            "source": "payload",
                        }
                    ]
                }
            }
        }

        audit = skill_routing_audit.merge_payload_decisions({}, incoming, event="after_tool")

        self.assertEqual(audit["skills"][0]["name"], "git-safe-commit")
        self.assertEqual(audit["skills"][0]["status"], "skipped")
        self.assertEqual(audit["skills"][0]["skip_reason"], "no_commit_requested")
        json.dumps(audit, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
