from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from api_authority_common import (
    AUTO_INSTALL_POLICY,
    FRAMEWORK_PACKAGE_NAMES,
    base_project_payload,
    detect_web_framework,
    dict_value,
    existing_rel,
    find_schema_locators,
    mcp_status,
    package_dependencies,
    read_csproj_target_framework,
    read_go_version,
    read_json_object,
    read_pyproject_version,
    read_unity_version,
    relative,
    unique,
)


OPENAI_TASK_RE = re.compile(
    r"(?i)\b(?:openai|chatgpt|responses\s+api|agents\s+sdk|codex\s+(?:api|cli|mcp|docs?|sdk))\b"
)
CONTEXT7_TASK_RE = re.compile(r"(?i)\bcontext7\b")
UNITY_TASK_RE = re.compile(r"(?i)\b(unity|unityengine|unityeditor|addressables|textmeshpro)\b")
MCP_TASK_RE = re.compile(r"(?i)\bmcp\b|model context protocol")


def project_authority_plan(
    workspace_root: Path,
    project: dict[str, Any],
    installed_mcp_servers: list[str],
) -> dict[str, Any]:
    domain = str(project.get("domain") or "unknown")
    engine = str(project.get("engine") or "")
    language = str(project.get("language") or "")
    framework = str(project.get("framework") or "")
    cwd = str(project.get("cwd") or ".")
    project_root = workspace_root / "" if cwd == "." else workspace_root / cwd

    if domain == "game_client" and engine == "unity":
        return unity_plan(workspace_root, project_root, project, installed_mcp_servers)
    if domain == "game_client":
        return game_client_plan(workspace_root, project_root, project, installed_mcp_servers)
    if domain in {"game_server", "backoffice_service"}:
        return server_plan(workspace_root, project_root, project, installed_mcp_servers)
    if domain == "backoffice_web":
        return web_plan(workspace_root, project_root, project, installed_mcp_servers)
    if domain == "workspace_meta":
        return workspace_meta_plan(workspace_root, project_root, project)
    return generic_plan(workspace_root, project_root, project, language, framework)


def unity_plan(
    workspace_root: Path,
    project_root: Path,
    project: dict[str, Any],
    installed_mcp_servers: list[str],
) -> dict[str, Any]:
    manifest = read_json_object(project_root / "Packages" / "manifest.json")
    dependencies = dict_value(manifest.get("dependencies"))
    api_surfaces = ["UnityEngine", "UnityEditor"]
    if "com.unity.addressables" in dependencies:
        api_surfaces.append("Addressables")
    if "com.unity.textmeshpro" in dependencies:
        api_surfaces.append("TMP")
    locators = existing_rel(
        workspace_root,
        project_root,
        ["ProjectSettings/ProjectVersion.txt", "Packages/manifest.json"],
    )
    locators.append("https://docs.unity3d.com/ScriptReference/index.html")
    package_docs = [
        {
            "package": name,
            "version": str(version),
            "authority": "Unity Package Manager manifest; resolve package docs for this version before use",
        }
        for name, version in dependencies.items()
        if name.startswith("com.unity.")
    ][:8]
    return base_project_payload(
        project,
        ecosystem="unity",
        detected_version=read_unity_version(project_root),
        api_surfaces=api_surfaces,
        authority_channels=["official_docs", "local_project_files", "local_sdk", "compiler", "test"],
        locators=locators,
        verification=["unity_batchmode_compile", "package_restore_or_asset_database_refresh"],
        mcp=mcp_status(["context7"], installed_mcp_servers, optional=True),
        extra={"package_docs": package_docs},
    )


def game_client_plan(
    workspace_root: Path,
    project_root: Path,
    project: dict[str, Any],
    installed_mcp_servers: list[str],
) -> dict[str, Any]:
    engine = str(project.get("engine") or "game_client")
    package = read_json_object(project_root / "package.json")
    engine_versions = game_client_engine_versions(engine, package_dependencies(package))
    detected_version = game_client_detected_version(engine_versions)
    locators = existing_rel(workspace_root, project_root, ["package.json", "project.json"])
    return base_project_payload(
        project,
        ecosystem=engine,
        detected_version=detected_version,
        api_surfaces=[detected_version] if engine_versions else [engine],
        authority_channels=["official_docs", "local_project_files", "local_sdk", "package_manifest", "compiler"],
        locators=locators,
        verification=["engine_compile_or_build_smoke"],
        mcp=mcp_status(["context7"], installed_mcp_servers, optional=True),
        extra={"engine_dependency_versions": engine_versions},
    )


def game_client_engine_versions(engine: str, dependencies: dict[str, Any]) -> dict[str, str]:
    prefixes_by_engine = {
        "laya": ("@laya/",),
        "cocos": ("@cocos/",),
    }
    names_by_engine = {
        "laya": {"laya", "layaair", "layaair-cmd", "layaair2-cmd"},
        "cocos": {"cc", "cocos", "cocos-engine", "cocos-creator"},
    }
    names = names_by_engine.get(engine, {engine})
    prefixes = prefixes_by_engine.get(engine, ())
    result = {
        name: str(version)
        for name, version in sorted(dependencies.items())
        if dependency_matches_engine(name, names, prefixes) and str(version).strip()
    }
    return result


def dependency_matches_engine(name: str, names: set[str], prefixes: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return lowered in names or any(lowered.startswith(prefix) for prefix in prefixes)


def game_client_detected_version(engine_versions: dict[str, str]) -> str:
    if not engine_versions:
        return "dependency_version_unknown"
    name = sorted(engine_versions)[0]
    return f"{name}@{engine_versions[name]}"


def server_plan(
    workspace_root: Path,
    project_root: Path,
    project: dict[str, Any],
    installed_mcp_servers: list[str],
) -> dict[str, Any]:
    schema_locators = find_schema_locators(workspace_root, project_root)
    if (project_root / "go.mod").exists():
        ecosystem = "go"
        version = read_go_version(project_root / "go.mod")
        locators = existing_rel(workspace_root, project_root, ["go.mod", "go.sum"]) + schema_locators
        official = ["https://go.dev/doc/", "https://pkg.go.dev/"]
        verification = ["go test ./...", "go build ./...", "schema_codegen_or_contract_test"]
    elif list(project_root.glob("*.csproj")):
        ecosystem = "dotnet"
        version = read_csproj_target_framework(project_root)
        locators = [relative(workspace_root, item) for item in project_root.glob("*.csproj")] + schema_locators
        official = ["https://learn.microsoft.com/dotnet/api/"]
        verification = ["dotnet test", "dotnet build", "schema_codegen_or_contract_test"]
    else:
        ecosystem = str(project.get("language") or "server")
        version = "n/a"
        locators = schema_locators
        official = []
        verification = ["server_build_or_contract_test"]
    return base_project_payload(
        project,
        ecosystem=ecosystem,
        detected_version=version,
        api_surfaces=["server_api_contracts"] + (["protobuf_or_openapi"] if schema_locators else []),
        authority_channels=["official_docs", "local_project_files", "schema", "compiler", "test"],
        locators=locators + official,
        verification=verification,
        mcp=mcp_status(["context7"], installed_mcp_servers, optional=True),
    )


def web_plan(
    workspace_root: Path,
    project_root: Path,
    project: dict[str, Any],
    installed_mcp_servers: list[str],
) -> dict[str, Any]:
    package = read_json_object(project_root / "package.json")
    dependencies = package_dependencies(package)
    framework = str(project.get("framework") or detect_web_framework(dependencies) or "web")
    dependency_versions = {
        name: str(dependencies[name])
        for name in sorted(dependencies)
        if str(dependencies[name]).strip()
    }
    surfaces = [
        f"{name}@{dependency_versions[name]}"
        for name in sorted(dependency_versions)
    ]
    framework_surface = versioned_framework_surface(framework, dependency_versions)
    if framework_surface:
        surfaces = [framework_surface] + [item for item in surfaces if item != framework_surface]
    api_surfaces = surfaces[:12]
    if framework and not framework_surface and not any(item.startswith(f"{framework}@") for item in api_surfaces):
        api_surfaces.insert(0, framework)
    locators = existing_rel(
        workspace_root,
        project_root,
        ["package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json"],
    )
    return base_project_payload(
        project,
        ecosystem="javascript",
        detected_version="dependency_versions",
        api_surfaces=api_surfaces,
        authority_channels=["official_docs", "context7", "local_project_files", "local_sdk", "compiler", "test"],
        locators=locators,
        verification=["npm_test_or_package_script", "typescript_or_lint_check"],
        mcp=mcp_status(["context7"], installed_mcp_servers, optional=True),
        extra={"dependency_versions": dependency_versions},
    )


def versioned_framework_surface(framework: str, dependency_versions: dict[str, str]) -> str:
    for name in FRAMEWORK_PACKAGE_NAMES.get(framework, (framework,)):
        version = dependency_versions.get(name)
        if version:
            return f"{name}@{version}"
    return ""


def workspace_meta_plan(
    workspace_root: Path,
    project_root: Path,
    project: dict[str, Any],
) -> dict[str, Any]:
    locators = existing_rel(workspace_root, project_root, ["pyproject.toml", "README.md", "AGENTS.md", "scripts", "plugins"])
    return base_project_payload(
        project,
        ecosystem="python_tooling",
        detected_version=read_pyproject_version(project_root / "pyproject.toml"),
        api_surfaces=["python_stdlib", "local_harness_scripts"],
        authority_channels=["source_code", "local_project_files", "compiler", "test"],
        locators=locators,
        verification=["python_compile", "unit_tests", "package_verify"],
        mcp={"required": [], "installed": [], "missing": [], "optional": True, "auto_install": False},
    )


def generic_plan(
    workspace_root: Path,
    project_root: Path,
    project: dict[str, Any],
    language: str,
    framework: str,
) -> dict[str, Any]:
    locators = existing_rel(workspace_root, project_root, ["README.md", "package.json", "pyproject.toml"])
    return base_project_payload(
        project,
        ecosystem=language or framework or str(project.get("domain") or "unknown"),
        detected_version="n/a",
        api_surfaces=[item for item in [language, framework] if item],
        authority_channels=["local_project_files", "compiler", "test"],
        locators=locators,
        verification=["project_specific_build_or_test"],
        mcp={"required": [], "installed": [], "missing": [], "optional": True, "auto_install": False},
    )


def global_task_authorities(task: dict[str, Any], installed_mcp_servers: list[str]) -> list[dict[str, Any]]:
    text = str(task.get("text") or "")
    plans: list[dict[str, Any]] = []
    if OPENAI_TASK_RE.search(text):
        plans.append(
            global_authority(
                "openai",
                ["OpenAI API", "Codex", "Responses API"],
                ["official_mcp", "official_docs", "local_examples", "test"],
                ["https://platform.openai.com/docs/", "https://developers.openai.com/"],
                ["api_request_smoke_or_mocked_contract_test"],
                mcp_status(["openai-docs"], installed_mcp_servers, optional=False),
            )
        )
    if CONTEXT7_TASK_RE.search(text):
        plans.append(
            global_authority(
                "context7",
                ["MCP docs retrieval", "library documentation snippets"],
                ["official_docs", "source_code", "context7_mcp"],
                ["https://github.com/upstash/context7"],
                ["verify_mcp_tool_result_against_local_dependency_version"],
                mcp_status(["context7"], installed_mcp_servers, optional=True),
            )
        )
    if MCP_TASK_RE.search(text):
        plans.append(
            global_authority(
                "mcp",
                ["MCP server configuration", "tool trust boundary"],
                ["official_docs", "local_config", "host_tool_visibility"],
                ["Codex config.toml", "configured MCP server manifest or README"],
                ["host_lists_expected_mcp_resources_or_templates"],
                {"required": [], "installed": installed_mcp_servers, "missing": [], "optional": True, "auto_install": False},
            )
        )
    if UNITY_TASK_RE.search(text) and not any(plan.get("ecosystem") == "unity" for plan in plans):
        plans.append(
            global_authority(
                "unity",
                ["UnityEngine", "UnityEditor"],
                ["official_docs", "local_unity_project", "compiler"],
                ["https://docs.unity3d.com/ScriptReference/index.html"],
                ["unity_batchmode_compile"],
                mcp_status(["context7"], installed_mcp_servers, optional=True),
            )
        )
    return plans


def global_authority(
    ecosystem: str,
    api_surfaces: list[str],
    channels: list[str],
    locators: list[str],
    verification: list[str],
    mcp: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ecosystem": ecosystem,
        "api_surfaces": api_surfaces,
        "authority_channels": channels,
        "locators": locators,
        "verification": verification,
        "mcp": mcp,
        "status": "plan_ready",
    }


def build_recommendations(projects: list[dict[str, Any]], global_plans: list[dict[str, Any]]) -> list[str]:
    items = [
        "Resolve official documentation or local SDK evidence before naming external APIs.",
        "Pin every API claim to the detected project version, lockfile, schema, or package manifest.",
        "Treat compilers, type checkers, Unity batchmode, and contract tests as completion gates.",
        "Do not auto-install MCP servers in Phase 1; record a plan and fall back to official docs or local files.",
    ]
    all_plans = projects + global_plans
    if any(plan.get("mcp", {}).get("missing") for plan in all_plans):
        items.append("Missing MCP servers are advisory in Phase 1 and must not be treated as verified sources.")
    if not all_plans:
        items.append("No project or API surface was detected; ask for a working set or inspect local dependency files.")
    return items
