from __future__ import annotations

import argparse
import json
import os
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
    if not str(manifest.get("release_id") or "").strip():
        gaps.append({"type": "release_id", "reason": "release manifest is missing release_id"})
    if not string_list(manifest.get("platforms")):
        gaps.append({"type": "platforms", "reason": "release manifest is missing target platforms"})
    if not _has_rollback_plan(manifest.get("rollback_plan")):
        gaps.append({"type": "rollback_plan", "reason": "release manifest is missing rollback plan"})
    artifacts = list_items(manifest.get("artifacts"))
    if not artifacts:
        gaps.append({"type": "artifacts", "reason": "release manifest is missing build artifacts"})
    for artifact in artifacts:
        path = str(artifact.get("path") or "").strip()
        if path and not (project_root / path).exists():
            gaps.append({"type": "artifact", "path": path, "reason": "artifact path does not exist"})
    for key, gate_value in gates.items():
        if gate_value.get("blocking") and gate_value.get("status") not in {"passed", "skipped"}:
            gaps.append({"type": "release_gate", "gate": key, "reason": gate_value.get("summary")})
    return gaps


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
        status = str(value.get("status") or "").strip() or ("passed" if value.get("ok") else "manual_required")
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
