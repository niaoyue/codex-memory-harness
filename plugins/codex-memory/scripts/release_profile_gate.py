from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


RELEASE_GATE_KEYS = (
    "localization_complete",
    "platform_matrix_passed",
    "webgl_minigame_compatible",
    "asset_bundle_dependency_policy",
    "package_budget",
    "performance_budget",
)
ARTIFACT_KINDS = {
    "package",
    "hot_update_manifest",
    "rollback_package",
    "build_report",
    "performance_report",
    "asset_manifest",
    "symbol_file",
    "other",
}
GATE_PASSING_STATUSES = {"passed", "skipped"}
GATE_KNOWN_STATUSES = {*GATE_PASSING_STATUSES, "manual_required", "failed", "blocked"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def evaluate_release_profile(route_plan: dict[str, Any]) -> dict[str, Any]:
    profile = route_plan.get("release_profile") if isinstance(route_plan.get("release_profile"), dict) else {}
    if route_plan.get("risk_level") != "release_blocking" or not profile:
        return {}
    evidence = profile.get("evidence") if isinstance(profile.get("evidence"), dict) else {}
    gates: dict[str, Any] = {}
    for key in RELEASE_GATE_KEYS:
        policy = gate_policy(profile, key)
        if not policy.get("required", True):
            gates[key] = gate("skipped", False, f"{key} is not required by release profile.", [])
            continue
        gates[key] = evidence_gate(key, evidence.get(key), policy)
    return gates


def evaluate_release_manifest(project_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate release evidence manifest without running platform builds."""
    gates = _manifest_evidence_gates(manifest)
    gaps = _manifest_gaps(project_root, manifest, gates)
    return {
        "version": 1,
        "status": "passed" if not gaps else "blocked",
        "blocking": bool(gaps),
        "release_id": str(manifest.get("release_id") or ""),
        "platforms": string_list(manifest.get("platforms")),
        "artifact_count": len(list_items(manifest.get("artifacts"))),
        "gates": gates,
        "blocking_gaps": gaps,
    }


def gate_policy(profile: dict[str, Any], key: str) -> dict[str, Any]:
    gates = profile.get("gates") if isinstance(profile.get("gates"), dict) else {}
    policy = gates.get(key) if isinstance(gates.get(key), dict) else {}
    return {
        "required": bool(policy.get("required", True)),
        "blocking": bool(policy.get("blocking", True)),
        "budget": policy.get("budget"),
    }


def _manifest_evidence_gates(manifest: dict[str, Any]) -> dict[str, Any]:
    profile = {
        "gates": manifest.get("gates") if isinstance(manifest.get("gates"), dict) else {},
    }
    evidence = manifest.get("evidence") if isinstance(manifest.get("evidence"), dict) else {}
    return {
        key: evidence_gate(key, evidence.get(key), gate_policy(profile, key))
        for key in RELEASE_GATE_KEYS
    }


def _manifest_gaps(project_root: Path, manifest: dict[str, Any], gates: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    target_platforms = set(string_list(manifest.get("platforms")))
    if not str(manifest.get("release_id") or "").strip():
        gaps.append({"type": "release_id", "reason": "release manifest is missing release_id"})
    if not target_platforms:
        gaps.append({"type": "platforms", "reason": "release manifest is missing target platforms"})
    if not _has_rollback_plan(manifest.get("rollback_plan")):
        gaps.append({"type": "rollback_plan", "reason": "release manifest is missing rollback plan"})
    artifacts = list_items(manifest.get("artifacts"))
    if not artifacts:
        gaps.append({"type": "artifacts", "reason": "release manifest is missing build artifacts"})
    covered_platforms: set[str] = set()
    for index, artifact in enumerate(artifacts):
        artifact_gaps, platforms = _artifact_gaps(project_root, artifact, target_platforms, index)
        gaps.extend(artifact_gaps)
        covered_platforms.update(platforms)
    missing_platforms = sorted(target_platforms - covered_platforms)
    if artifacts and missing_platforms:
        gaps.append({
            "type": "artifact_platform_coverage",
            "platforms": missing_platforms,
            "reason": "target platform is not covered by any valid artifact",
        })
    gaps.extend(_evidence_report_gaps(project_root, manifest))
    for key, gate_value in gates.items():
        status = str(gate_value.get("status") or "").strip()
        if status and status not in GATE_KNOWN_STATUSES:
            gaps.append({"type": "release_gate_status", "gate": key, "status": status, "reason": "unknown release evidence status"})
        if gate_value.get("blocking") and status not in GATE_PASSING_STATUSES:
            gaps.append({"type": "release_gate", "gate": key, "reason": gate_value.get("summary")})
    return gaps


def _artifact_gaps(
    project_root: Path,
    artifact: dict[str, Any],
    target_platforms: set[str],
    index: int,
) -> tuple[list[dict[str, Any]], set[str]]:
    gaps: list[dict[str, Any]] = []
    kind = str(artifact.get("kind") or "").strip()
    if kind not in ARTIFACT_KINDS:
        gaps.append({"type": "artifact_kind", "index": index, "kind": kind, "reason": "artifact kind is missing or unsupported"})

    path = str(artifact.get("path") or "").strip()
    artifact_path = _resolve_manifest_path(project_root, path)
    if not path or artifact_path is None:
        gaps.append({"type": "artifact_path", "index": index, "path": path, "reason": "artifact path is missing or outside project root"})
    elif not artifact_path.exists():
        gaps.append({"type": "artifact", "index": index, "path": path, "reason": "artifact path does not exist"})
    else:
        gaps.extend(_artifact_integrity_gaps(artifact, artifact_path, index, path))

    platforms = set(string_list(artifact.get("platforms")))
    if target_platforms:
        if not platforms:
            gaps.append({"type": "artifact_platform", "index": index, "reason": "artifact is missing target platform mapping"})
        unsupported = sorted(platforms - target_platforms)
        if unsupported:
            gaps.append({"type": "artifact_platform", "index": index, "platforms": unsupported, "reason": "artifact declares platforms outside release target matrix"})
    valid_path = bool(path and artifact_path is not None and artifact_path.exists())
    return gaps, platforms if valid_path else set()


def _artifact_integrity_gaps(
    artifact: dict[str, Any],
    artifact_path: Path,
    index: int,
    manifest_path: str,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    expected_sha = str(artifact.get("sha256") or "").strip().lower()
    if expected_sha:
        actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if not SHA256_PATTERN.match(expected_sha) or actual_sha != expected_sha:
            gaps.append({"type": "artifact_checksum", "index": index, "path": manifest_path, "reason": "artifact sha256 does not match local file"})
    if "size_bytes" in artifact:
        expected_size = artifact.get("size_bytes")
        if not isinstance(expected_size, int) or expected_size < 0 or artifact_path.stat().st_size != expected_size:
            gaps.append({"type": "artifact_size", "index": index, "path": manifest_path, "reason": "artifact size_bytes does not match local file"})
    return gaps


def _evidence_report_gaps(project_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = manifest.get("evidence") if isinstance(manifest.get("evidence"), dict) else {}
    gaps: list[dict[str, Any]] = []
    for key, value in evidence.items():
        if not isinstance(value, dict):
            continue
        report_path = str(value.get("report_path") or "").strip()
        if not report_path:
            continue
        resolved = _resolve_manifest_path(project_root, report_path)
        if resolved is None or not resolved.exists():
            gaps.append({"type": "evidence_report", "gate": key, "path": report_path, "reason": "evidence report_path does not exist"})
    return gaps


def _resolve_manifest_path(project_root: Path, value: str) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(project_root.resolve(strict=False))
        return resolved
    except ValueError:
        return None


def _has_rollback_plan(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(str(value.get("summary") or value.get("procedure") or value.get("owner") or "").strip())
    return False


def evidence_gate(key: str, value: Any, policy: dict[str, Any]) -> dict[str, Any]:
    if value is True:
        return gate("passed", bool(policy["blocking"]), f"{key} evidence passed.", [])
    if isinstance(value, dict):
        status = str(value.get("status") or "").strip().lower() or ("passed" if value.get("ok") else "manual_required")
        findings = value.get("findings") if isinstance(value.get("findings"), list) else []
        summary = str(value.get("summary") or f"{key} evidence status is {status}.")
        return gate(status, bool(policy["blocking"]), summary, findings)
    return gate(
        "manual_required",
        bool(policy["blocking"]),
        f"{key} requires release evidence for the selected targets, locales, budgets, or asset policy.",
        [{"type": key, "reason": "missing release profile evidence"}],
    )


def gate(status: str, blocking: bool, summary: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": status,
        "blocking": blocking,
        "summary": summary,
        "findings": findings[:50],
    }


def list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a release manifest without running platform builds.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--manifest-file", required=True)
    args = parser.parse_args()
    manifest_value = json.loads(Path(args.manifest_file).read_text(encoding="utf-8"))
    if not isinstance(manifest_value, dict):
        raise ValueError("manifest-file must contain a JSON object.")
    result = evaluate_release_manifest(Path(args.project_root).resolve(), manifest_value)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
