from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS_DIR = PROJECT_ROOT / "plugins" / "codex-memory" / "scripts"
if str(PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS_DIR))

import openspec_upstream  # noqa: E402


class OpenSpecUpstreamTests(unittest.TestCase):
    def test_sync_from_package_dir_writes_verifiable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)

            result = openspec_upstream.sync_from_package_dir(
                package_dir,
                root / "openspec" / "upstream" / "openspec",
                package_name="@fission-ai/openspec",
                view_metadata={
                    "version": "1.3.1",
                    "engines": {"node": ">=20.19.0"},
                    "repository": {"type": "git", "url": "git+https://github.com/Fission-AI/OpenSpec.git"},
                    "homepage": "https://github.com/Fission-AI/OpenSpec",
                    "license": "MIT",
                    "dist-tags": {"latest": "1.3.1"},
                },
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            verify = openspec_upstream.verify_project(root)
            license_text = (root / "openspec" / "upstream" / "openspec" / "LICENSE").read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertTrue(verify["ok"])
        self.assertEqual(verify["resolved_version"], "1.3.1")
        self.assertFalse(license_text.endswith("\n\n"))

    def test_official_npm_args_pin_registry(self) -> None:
        args = openspec_upstream.official_npm_args(["npm.cmd", "pack", "@fission-ai/openspec@1.3.1"])

        self.assertIn("--registry=https://registry.npmjs.org/", args)
        self.assertIn("--@fission-ai:registry=https://registry.npmjs.org/", args)

    def test_validate_official_npm_metadata_rejects_non_official_tarball(self) -> None:
        with self.assertRaises(RuntimeError):
            openspec_upstream.validate_official_npm_metadata(
                {
                    "dist": {
                        "tarball": "https://mirror.example.invalid/@fission-ai/openspec/-/openspec-1.3.1.tgz",
                        "integrity": "sha512-test",
                        "shasum": "abc",
                    }
                },
                {"integrity": "sha512-test", "shasum": "abc"},
            )

    def test_validate_official_npm_metadata_rejects_insecure_tarball(self) -> None:
        with self.assertRaises(RuntimeError):
            openspec_upstream.validate_official_npm_metadata(
                {
                    "dist": {
                        "tarball": "http://registry.npmjs.org/@fission-ai/openspec/-/openspec-1.3.1.tgz",
                        "integrity": "sha512-test",
                        "shasum": "abc",
                    }
                },
                {"integrity": "sha512-test", "shasum": "abc"},
            )

    def test_validate_official_npm_metadata_rejects_integrity_mismatch(self) -> None:
        with self.assertRaises(RuntimeError):
            openspec_upstream.validate_official_npm_metadata(
                {
                    "dist": {
                        "tarball": "https://registry.npmjs.org/@fission-ai/openspec/-/openspec-1.3.1.tgz",
                        "integrity": "sha512-expected",
                        "shasum": "abc",
                    }
                },
                {"integrity": "sha512-actual", "shasum": "abc"},
            )

    def test_validate_official_npm_metadata_rejects_missing_integrity(self) -> None:
        with self.assertRaises(RuntimeError):
            openspec_upstream.validate_official_npm_metadata(
                {
                    "dist": {
                        "tarball": "https://registry.npmjs.org/@fission-ai/openspec/-/openspec-1.3.1.tgz",
                        "shasum": "abc",
                    }
                },
                {"shasum": "abc"},
            )

    def test_verify_detects_snapshot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            (target / "LICENSE").write_text("changed\n", encoding="utf-8")

            verify = openspec_upstream.verify_project(root)

        self.assertFalse(verify["ok"])
        self.assertIn("sha256 mismatch LICENSE", verify["failures"])

    def test_sync_prunes_stale_snapshot_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            target.mkdir(parents=True)
            (target / "stale.txt").write_text("stale\n", encoding="utf-8")

            result = openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )

            self.assertTrue(result["ok"])
            self.assertFalse((target / "stale.txt").exists())

    def test_sync_preserves_current_snapshot_when_required_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            existing_license = (target / "LICENSE").read_text(encoding="utf-8")
            (package_dir / "LICENSE").unlink()

            with self.assertRaises(FileNotFoundError):
                openspec_upstream.sync_from_package_dir(
                    package_dir,
                    target,
                    package_name="@fission-ai/openspec",
                    view_metadata={"version": "1.3.1", "license": "MIT"},
                    pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                    schema_name="spec-driven",
                )

            self.assertEqual((target / "LICENSE").read_text(encoding="utf-8"), existing_license)
            self.assertTrue(openspec_upstream.verify_project(root)["ok"])

    def test_sync_preserves_current_snapshot_when_staged_verify_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            existing_readme = (target / "README.md").read_text(encoding="utf-8")
            (package_dir / "README.md").write_text("replacement\n", encoding="utf-8")

            result = openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "", "shasum": ""},
                schema_name="spec-driven",
            )

            self.assertFalse(result["ok"])
            self.assertIn("manifest integrity missing", result["failures"])
            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), existing_readme)
            self.assertTrue(openspec_upstream.verify_project(root)["ok"])

    def test_verify_rejects_unmanifested_snapshot_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            (target / "stale.txt").write_text("stale\n", encoding="utf-8")

            verify = openspec_upstream.verify_project(root)

        self.assertFalse(verify["ok"])
        self.assertIn("unmanifested file stale.txt", verify["failures"])

    def test_verify_rejects_invalid_manifest_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "openspec" / "upstream" / "openspec"
            target.mkdir(parents=True)
            (target / "manifest.json").write_text("{invalid\n", encoding="utf-8")

            verify = openspec_upstream.verify_project(root)

        self.assertFalse(verify["ok"])
        self.assertIn("manifest invalid JSON", verify["failures"])

    def test_verify_rejects_manifest_missing_required_file_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = [item for item in manifest["files"] if item["path"] != "LICENSE"]
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            verify = openspec_upstream.verify_project(root)

        self.assertFalse(verify["ok"])
        self.assertIn("manifest record missing LICENSE", verify["failures"])

    def test_verify_rejects_wrong_manifest_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["package"] = "evil"
            manifest["schema"] = "wrong"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            verify = openspec_upstream.verify_project(root)

        self.assertFalse(verify["ok"])
        self.assertIn("manifest package mismatch", verify["failures"])
        self.assertIn("manifest schema mismatch", verify["failures"])

    def test_verify_accepts_newer_synced_version_when_package_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir, version="1.3.2")

            result = openspec_upstream.sync_from_package_dir(
                package_dir,
                root / "openspec" / "upstream" / "openspec",
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.2", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["resolved_version"], "1.3.2")

    def test_verify_requires_manifest_license(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            _write_fake_package(package_dir)
            target = root / "openspec" / "upstream" / "openspec"
            openspec_upstream.sync_from_package_dir(
                package_dir,
                target,
                package_name="@fission-ai/openspec",
                view_metadata={"version": "1.3.1", "license": "MIT"},
                pack_metadata={"integrity": "sha512-test", "shasum": "abc"},
                schema_name="spec-driven",
            )
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("license")
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            verify = openspec_upstream.verify_project(root)

        self.assertFalse(verify["ok"])
        self.assertIn("manifest license missing", verify["failures"])

    def test_safe_extract_rejects_link_members_before_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tar_path = root / "bad.tgz"
            with tarfile.open(tar_path, "w:gz") as archive:
                member = tarfile.TarInfo("package/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)

            with self.assertRaises(RuntimeError):
                openspec_upstream.safe_extract_tar(tar_path, root / "extract")

    def test_run_json_retries_429_with_backoff(self) -> None:
        calls = []
        sleeps = []
        original_run = openspec_upstream.subprocess.run
        original_sleep = openspec_upstream.time.sleep

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(kwargs)
            if len(calls) == 1:
                return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="429 rate limit")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="{\"ok\": true}", stderr="")

        try:
            openspec_upstream.subprocess.run = fake_run  # type: ignore[assignment]
            openspec_upstream.time.sleep = lambda seconds: sleeps.append(seconds)  # type: ignore[assignment]
            result = openspec_upstream.run_json(["npm.cmd", "view"], Path("."))
        finally:
            openspec_upstream.subprocess.run = original_run  # type: ignore[assignment]
            openspec_upstream.time.sleep = original_sleep  # type: ignore[assignment]

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [openspec_upstream.BACKOFF_429_SECONDS])
        self.assertEqual(calls[0]["timeout"], openspec_upstream.NPM_TIMEOUT_SECONDS)

    def test_run_json_retries_timeout_once(self) -> None:
        calls = []
        sleeps = []
        original_run = openspec_upstream.subprocess.run
        original_sleep = openspec_upstream.time.sleep

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(kwargs)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(cmd=["npm.cmd"], timeout=1)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="{\"ok\": true}", stderr="")

        try:
            openspec_upstream.subprocess.run = fake_run  # type: ignore[assignment]
            openspec_upstream.time.sleep = lambda seconds: sleeps.append(seconds)  # type: ignore[assignment]
            result = openspec_upstream.run_json(["npm.cmd", "pack"], Path("."))
        finally:
            openspec_upstream.subprocess.run = original_run  # type: ignore[assignment]
            openspec_upstream.time.sleep = original_sleep  # type: ignore[assignment]

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [openspec_upstream.BACKOFF_TRANSIENT_SECONDS])
        self.assertEqual(len(calls), 2)


def _write_fake_package(package_dir: Path, *, version: str = "1.3.1") -> None:
    for rel in openspec_upstream.UPSTREAM_FILES:
        path = package_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{rel}\n", encoding="utf-8")
    (package_dir / "LICENSE").write_text("license\n\n", encoding="utf-8")
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "@fission-ai/openspec",
                "version": version,
                "license": "MIT",
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
