from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from task_spec import task_spec_path


EVIDENCE_KINDS = {
    "openspec_contract",
    "bmad_planning",
    "harness_task",
    "verification_artifact",
    "release_gate",
    "xhigh_review",
    "sync_archive",
}


def prepare(
    project_root: Path,
    *,
    task_id: str,
    change_id: str,
    release_profile_id: str = "",
    effective_cwd: str = ".",
    bmad_artifact_dir: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    context = context_payload(project_root, task_id, change_id, release_profile_id, effective_cwd, "", bmad_artifact_dir, dry_run)
    evidence = [
        openspec_evidence(project_root, change_id),
        bmad_evidence(project_root, bmad_artifact_dir),
        harness_task_evidence(project_root, task_id),
    ]
    return bundle(context, evidence)


def collect(
    project_root: Path,
    *,
    task_id: str,
    change_id: str,
    release_profile_id: str = "",
    effective_cwd: str = ".",
    commit_ref: str = "",
    verification_artifact: str = "",
    review_result: str = "",
    bmad_artifact_dir: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    context = context_payload(project_root, task_id, change_id, release_profile_id, effective_cwd, commit_ref, bmad_artifact_dir, dry_run)
    evidence = [
        openspec_evidence(project_root, change_id),
        bmad_evidence(project_root, bmad_artifact_dir),
        harness_task_evidence(project_root, task_id),
    ]
    evidence.extend(verification_evidence(project_root, verification_artifact))
    evidence.extend(review_evidence(project_root, review_result, commit_ref))
    return bundle(context, evidence)


def sync_archive(project_root: Path, bundle_payload: dict[str, Any], *, archive: bool = False) -> dict[str, Any]:
    safe = bool(bundle_payload.get("safe_to_archive"))
    evidence = list(bundle_payload.get("evidence") if isinstance(bundle_payload.get("evidence"), list) else [])
    status = "ready" if safe else "blocked"
    evidence.append(evidence_ref("sync_archive", str(bundle_payload.get("openspec_change_id") or ""), status=status))
    result = {**bundle_payload, "evidence": evidence, "safe_to_archive": safe, "archive_requested": archive}
    result["overall_status"] = "passed" if safe else "blocked"
    if archive and safe:
        path = archive_evidence_path(project_root, str(bundle_payload.get("task_id") or "governance"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["archive_evidence_path"] = str(path)
    return result


def bundle(context: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = blocking_gaps(evidence)
    safe = not gaps and has_clean_review(evidence) and has_passed_verification(evidence)
    return {
        "version": 1,
        "task_id": context["task_id"],
        "openspec_change_id": context["openspec_change_id"],
        "release_profile_id": context["release_profile_id"],
        "commit_ref": context["commit_ref"],
        "overall_status": "passed" if safe else "blocked" if gaps else "not_ready",
        "context": context,
        "evidence": evidence,
        "blocking_gaps": gaps,
        "safe_to_archive": safe,
    }


def context_payload(
    project_root: Path,
    task_id: str,
    change_id: str,
    release_profile_id: str,
    effective_cwd: str,
    commit_ref: str,
    bmad_artifact_dir: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "project_root": str(project_root.resolve()),
        "effective_cwd": str((project_root / effective_cwd).resolve()),
        "task_id": task_id,
        "openspec_change_id": change_id,
        "release_profile_id": release_profile_id,
        "commit_ref": commit_ref,
        "bmad_artifact_dir": bmad_artifact_dir,
        "dry_run": dry_run,
    }


def openspec_evidence(project_root: Path, change_id: str) -> dict[str, Any]:
    change_dir = project_root / "openspec" / "changes" / change_id
    required = ["proposal.md", "design.md", "tasks.md"]
    missing = [name for name in required if not (change_dir / name).exists()]
    status = "passed" if change_dir.exists() and not missing else "missing"
    return evidence_ref(
        "openspec_contract",
        change_id,
        path=relative_path(project_root, change_dir),
        status=status,
        summary="OpenSpec change contract is present." if status == "passed" else f"OpenSpec contract missing: {', '.join(missing) or change_id}",
    )


def bmad_evidence(project_root: Path, bmad_artifact_dir: str) -> dict[str, Any]:
    if not bmad_artifact_dir:
        return evidence_ref("bmad_planning", "not-required", status="skipped", summary="No BMAD planning artifact directory was requested.")
    path = project_root / bmad_artifact_dir
    status = "passed" if path.exists() and any(path.iterdir()) else "missing"
    return evidence_ref("bmad_planning", bmad_artifact_dir, path=relative_path(project_root, path), status=status)


def harness_task_evidence(project_root: Path, task_id: str) -> dict[str, Any]:
    path = task_spec_path(project_root, task_id)
    return evidence_ref(
        "harness_task",
        task_id,
        path=relative_path(project_root, path),
        status="passed" if path.exists() else "missing",
        summary="Harness task spec is present." if path.exists() else "Harness task spec is missing.",
    )


def verification_evidence(project_root: Path, artifact: str) -> list[dict[str, Any]]:
    if not artifact:
        return []
    payload = load_json_path(project_root, artifact)
    status = str(payload.get("overall_status") or payload.get("status") or "missing")
    evidence = [evidence_ref("verification_artifact", artifact, path=artifact, status="passed" if status == "passed" else status)]
    gates = payload.get("release_gates") if isinstance(payload.get("release_gates"), dict) else {}
    for key, gate in gates.items():
        if isinstance(gate, dict):
            evidence.append(evidence_ref("release_gate", str(key), status=str(gate.get("status") or "missing"), summary=str(gate.get("summary") or "")))
    return evidence


def review_evidence(project_root: Path, review_result: str, commit_ref: str) -> list[dict[str, Any]]:
    if not review_result:
        return []
    entries = load_jsonl_path(project_root, review_result)
    if not entries:
        return [evidence_ref("xhigh_review", review_result, path=review_result, status="missing")]
    latest = entries[-1]
    status = str(latest.get("status") or "missing")
    reviewed_commit = str(latest.get("commit_ref") or latest.get("review_commit_ref") or commit_ref)
    summary = "Commit-based xhigh review is clean." if status == "clean" else f"xhigh review status is {status}."
    return [evidence_ref("xhigh_review", reviewed_commit or review_result, path=review_result, status=status, summary=summary, fingerprint=str((latest.get("diff_fingerprint") or {}).get("fingerprint") or ""))]


def blocking_gaps(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    for item in evidence:
        if item.get("status") in {"passed", "clean", "skipped"}:
            continue
        gaps.append({"kind": item.get("kind"), "id": item.get("id"), "status": item.get("status"), "summary": item.get("summary")})
    return gaps


def has_clean_review(evidence: list[dict[str, Any]]) -> bool:
    return any(item.get("kind") == "xhigh_review" and item.get("status") == "clean" for item in evidence)


def has_passed_verification(evidence: list[dict[str, Any]]) -> bool:
    return any(item.get("kind") == "verification_artifact" and item.get("status") == "passed" for item in evidence)


def evidence_ref(kind: str, ident: str, *, path: str = "", status: str = "not_run", summary: str = "", fingerprint: str = "") -> dict[str, Any]:
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"Unsupported evidence kind: {kind}")
    return {"kind": kind, "id": ident, "path": path, "status": status, "summary": summary, "fingerprint": fingerprint}


def load_json_path(project_root: Path, path: str) -> dict[str, Any]:
    resolved = project_root / path
    if not resolved.exists():
        return {"status": "missing"}
    value = json.loads(resolved.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {"status": "invalid"}


def load_jsonl_path(project_root: Path, path: str) -> list[dict[str, Any]]:
    resolved = project_root / path
    if not resolved.exists():
        return []
    return [json.loads(line) for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()]


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def archive_evidence_path(project_root: Path, task_id: str) -> Path:
    return project_root / ".codex" / "harness" / "tasks" / task_id / "governance-evidence.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect OpenSpec/BMAD contracts with harness verification and review evidence.")
    parser.add_argument("--project-root", default=os.environ.get("CODEX_MEMORY_CWD") or os.getcwd())
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--change", required=True)
    parser.add_argument("--release-profile", default="")
    parser.add_argument("--effective-cwd", default=".")
    parser.add_argument("--commit", default="")
    parser.add_argument("--verification-artifact", default="")
    parser.add_argument("--review-result", default="")
    parser.add_argument("--bmad-artifact-dir", default="")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("collect")
    archive = sub.add_parser("sync-archive")
    archive.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    if args.command == "prepare":
        result = prepare(root, task_id=args.task_id, change_id=args.change, release_profile_id=args.release_profile, effective_cwd=args.effective_cwd, bmad_artifact_dir=args.bmad_artifact_dir)
    elif args.command == "collect":
        result = collect(root, task_id=args.task_id, change_id=args.change, release_profile_id=args.release_profile, effective_cwd=args.effective_cwd, commit_ref=args.commit, verification_artifact=args.verification_artifact, review_result=args.review_result, bmad_artifact_dir=args.bmad_artifact_dir)
    else:
        result = sync_archive(root, collect(root, task_id=args.task_id, change_id=args.change, release_profile_id=args.release_profile, effective_cwd=args.effective_cwd, commit_ref=args.commit, verification_artifact=args.verification_artifact, review_result=args.review_result, bmad_artifact_dir=args.bmad_artifact_dir), archive=args.archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("overall_status") in {"passed", "not_ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
