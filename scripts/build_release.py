from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = PROJECT_ROOT / "plugins" / "codex-memory" / ".codex-plugin" / "plugin.json"

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
}

EXCLUDED_NAMES = {
    "memory.db",
    "events.jsonl",
}


EXCLUDED_PATH_PREFIXES = (
    (".codex",),
    ("dist",),
)


def version() -> str:
    payload = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    return str(payload["version"])


def _has_prefix(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(parts) >= len(prefix) and parts[: len(prefix)] == prefix


def should_skip(path: Path) -> bool:
    relative = path.relative_to(PROJECT_ROOT)
    parts = relative.parts
    if any(_has_prefix(parts, prefix) for prefix in EXCLUDED_PATH_PREFIXES):
        return True
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def iter_files() -> list[Path]:
    return [
        path
        for path in sorted(PROJECT_ROOT.rglob("*"))
        if path.is_file() and not should_skip(path)
    ]


def build(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    package_name = f"codex-memory-harness-{version()}.zip"
    package_path = output_dir / package_name
    if package_path.exists():
        package_path.unlink()

    manifest = {
        "name": "codex-memory-harness",
        "version": version(),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "install": "Run install.ps1 or py -X utf8 plugins/codex-memory/scripts/install_codex_memory.py",
    }

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("PACKAGE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for path in iter_files():
            archive.write(path, path.relative_to(PROJECT_ROOT).as_posix())
    return package_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a distributable Codex Memory Harness zip.")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "dist"))
    args = parser.parse_args()

    package_path = build(Path(args.output_dir))
    print(package_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
