from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

import workspace_lifecycle


def route_plan() -> dict[str, object]:
    return {
        "version": 1,
        "task_id": "route-task",
        "route_plan_id": "route-route-task",
        "mode": "single_project",
        "affected_projects": ["client-unity"],
        "routes": [
            {
                "route_id": "client-route",
                "project_id": "client-unity",
                "domain": "game_client",
                "cwd": "client",
                "assigned_scope": ["client/Assets"],
                "rules": ["workspace/base", "game_client/unity"],
                "verification_profile_ids": ["client_quick"],
                "confidence": 0.9,
            }
        ],
        "risk_level": "medium",
        "confidence": 0.9,
        "reasons": ["test"],
        "verification_plan": [],
    }


def multi_route_plan() -> dict[str, object]:
    plan = route_plan()
    plan["mode"] = "multi_project_parallel"
    plan["affected_projects"] = ["client-unity", "design-docs"]
    plan["routes"] = [
        plan["routes"][0],
        {
            "route_id": "docs-route",
            "project_id": "design-docs",
            "domain": "design_docs",
            "cwd": "docs",
            "assigned_scope": ["docs"],
            "rules": ["workspace/base", "docs/design"],
            "verification_profile_ids": ["primary"],
            "confidence": 0.8,
        },
    ]
    return plan


def client_server_route_plan() -> dict[str, object]:
    plan = multi_route_plan()
    plan["affected_projects"] = ["client-unity", "server-game"]
    plan["routes"][1] = {
        "route_id": "server-route",
        "project_id": "server-game",
        "domain": "game_server",
        "cwd": "server",
        "assigned_scope": ["server/api"],
        "rules": ["workspace/base", "game_server/base"],
        "verification_profile_ids": ["server_unit"],
        "confidence": 0.8,
    }
    return plan


def root_and_docs_route_plan() -> dict[str, object]:
    plan = multi_route_plan()
    plan["task_id"] = "root-docs"
    plan["route_plan_id"] = "route-root-docs"
    plan["affected_projects"] = ["workspace-root", "design-docs"]
    plan["coordinator_required"] = True
    plan["routes"][0] = {
        "route_id": "root-route",
        "project_id": "workspace-root",
        "domain": "workspace_meta",
        "cwd": ".",
        "task_type": "implementation",
        "assigned_scope": ["."],
        "rules": ["workspace/base"],
        "verification_profile_ids": ["primary"],
        "confidence": 0.8,
    }
    plan["routes"][1]["task_type"] = "docs"
    plan["confidence"] = 0.8
    return plan


def routing_mocks() -> object:
    return mock.patch.object(workspace_lifecycle.workspace_router, "build_route_plan", return_value=route_plan())


class MemoryEnv:
    def __enter__(self) -> str:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_scope = os.environ.get("CODEX_MEMORY_SCOPE")
        self.old_cwd = os.environ.get("CODEX_MEMORY_CWD")
        os.environ["CODEX_MEMORY_SCOPE"] = "project"
        os.environ["CODEX_MEMORY_CWD"] = self.temp_dir.name
        Path(self.temp_dir.name, ".codex").mkdir()
        return self.temp_dir.name

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        restore_env("CODEX_MEMORY_SCOPE", self.old_scope)
        restore_env("CODEX_MEMORY_CWD", self.old_cwd)
        self.temp_dir.cleanup()


def restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
