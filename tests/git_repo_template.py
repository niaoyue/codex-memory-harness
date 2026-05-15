from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


_TEMPLATES: dict[tuple[tuple[str, str], ...], tuple[tempfile.TemporaryDirectory[str], Path]] = {}


def copy_git_repo(path: Path, files: dict[str, str]) -> None:
    source = _template_repo(files)
    shutil.copytree(source, path, dirs_exist_ok=True)


def _template_repo(files: dict[str, str]) -> Path:
    key = tuple(sorted(files.items()))
    existing = _TEMPLATES.get(key)
    if existing is not None:
        return existing[1]

    temp_dir = tempfile.TemporaryDirectory()
    repo = Path(temp_dir.name) / "repo"
    repo.mkdir()
    _run_git(repo, ["init", "-b", "main"])
    _run_git(repo, ["config", "user.email", "test@example.com"])
    _run_git(repo, ["config", "user.name", "Test User"])
    for relative, text in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _run_git(repo, ["add", "."])
    _run_git(repo, ["commit", "-m", "initial"])
    _TEMPLATES[key] = (temp_dir, repo)
    return repo


def _run_git(path: Path, args: list[str]) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
