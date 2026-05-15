from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import review_workflow


def fingerprint(value: str = "current", *, mode: str = "uncommitted") -> dict[str, object]:
    return {"algorithm": "sha256", "fingerprint": f"sha256:{value}", "mode": mode, "changed_files": []}


def patched_fingerprint(value: str = "current") -> object:
    return mock.patch.object(review_workflow, "diff_fingerprint", return_value=fingerprint(value))


class fast_review_project:
    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patch = patched_fingerprint()
        self.patch.__enter__()
        return Path(self.temp_dir.name)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.patch.__exit__(exc_type, exc, tb)
        self.temp_dir.cleanup()
