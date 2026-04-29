from __future__ import annotations

from typing import Any

import sensitive_scan


def sensitive_artifact_gaps(bindings: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for artifact in artifacts:
        binding = matching_sensitive_binding(bindings, artifact)
        if not binding:
            continue
        scan_report = sensitive_scan_report(artifact)
        if not scan_report:
            continue
        gaps.append(
            {
                "type": "sensitive_artifact_output",
                "binding_id": binding.get("binding_id"),
                "subagent_id": binding.get("subagent_id"),
                "project_id": binding.get("project_id"),
                "blocking": True,
                "reason": "artifact contains raw sensitive output",
                "scan": scan_report,
            }
        )
    return gaps


def matching_sensitive_binding(bindings: list[dict[str, Any]], artifact: dict[str, Any]) -> dict[str, Any] | None:
    for binding in bindings:
        policy = binding.get("artifact_policy") if isinstance(binding.get("artifact_policy"), dict) else {}
        if policy.get("forbid_raw_sensitive_output") and artifact_matches_binding(binding, artifact):
            return binding
    return None


def sensitive_scan_report(artifact: dict[str, Any]) -> dict[str, Any] | None:
    preserved = artifact.get("_sensitive_scan") if isinstance(artifact.get("_sensitive_scan"), dict) else {}
    if scan_report_has_findings(preserved):
        return preserved
    result = sensitive_scan.sanitize_for_persistence(artifact)
    if result.findings or result.blocked:
        return result.report()
    return None


def scan_report_has_findings(report: dict[str, Any]) -> bool:
    try:
        finding_count = int(report.get("finding_count") or 0)
    except (TypeError, ValueError):
        finding_count = 0
    return bool(report.get("blocked") or report.get("redacted") or finding_count > 0)


def artifact_matches_binding(binding: dict[str, Any], artifact: dict[str, Any]) -> bool:
    binding_ids = {str(binding.get("binding_id") or ""), str(binding.get("subagent_id") or "")}
    artifact_ids = {str(artifact.get("binding_id") or ""), str(artifact.get("subagent_id") or "")}
    if (binding_ids - {""}) & (artifact_ids - {""}):
        return True
    project_id = str(binding.get("project_id") or "")
    artifact_project_id = str(artifact.get("project_id") or "")
    return bool(project_id and artifact_project_id and project_id == artifact_project_id)
