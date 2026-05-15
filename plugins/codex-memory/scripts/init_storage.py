from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
GLOBAL_STORAGE_DIR: Path | None = None
PROJECT_MARKERS = [".git", "AGENTS.md", "pyproject.toml", "package.json", "README.md"]


@dataclass(frozen=True)
class StoragePaths:
    scope: str
    project_root: Path | None
    storage_dir: Path
    db_path: Path
    event_log_path: Path
    summary_dir: Path
    distilled_dir: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "scope": self.scope,
            "project_root": str(self.project_root) if self.project_root else "",
            "storage_dir": str(self.storage_dir),
            "db_path": str(self.db_path),
            "event_log_path": str(self.event_log_path),
            "summary_dir": str(self.summary_dir),
            "distilled_dir": str(self.distilled_dir),
        }


def _env_value(name: str) -> str:
    return os.environ.get(name, "").strip()


def _codex_home() -> Path:
    configured = _env_value("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def _global_storage_dir() -> Path:
    return GLOBAL_STORAGE_DIR or (_codex_home() / "codex-memory-harness" / "memories")


def _find_project_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".codex").is_dir():
            return candidate
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    return None


def resolve_storage_paths(
    scope: str | None = None,
    cwd: str | Path | None = None,
    *,
    project_root_override: str | Path | None = None,
) -> StoragePaths:
    requested_scope = (scope or _env_value("CODEX_MEMORY_SCOPE") or "project").lower()
    if requested_scope not in {"project", "global", "auto"}:
        raise ValueError("CODEX_MEMORY_SCOPE must be one of: project, global, auto")

    start = Path(cwd or _env_value("CODEX_MEMORY_CWD") or Path.cwd()).resolve()
    project_root = (
        Path(project_root_override).resolve()
        if project_root_override and requested_scope in {"project", "auto"}
        else _find_project_root(start)
    )
    if requested_scope == "global" or (requested_scope == "auto" and project_root is None):
        storage_dir = _global_storage_dir()
        resolved_scope = "global"
        resolved_project_root = None
    else:
        resolved_project_root = project_root or start
        storage_dir = resolved_project_root / ".codex" / "memories"
        resolved_scope = "project"

    return StoragePaths(
        scope=resolved_scope,
        project_root=resolved_project_root,
        storage_dir=storage_dir,
        db_path=storage_dir / "memory.db",
        event_log_path=storage_dir / "events.jsonl",
        summary_dir=storage_dir / "summaries",
        distilled_dir=storage_dir / "distilled",
    )


def _paths() -> StoragePaths:
    return resolve_storage_paths()


def __getattr__(name: str):
    paths = _paths()
    values = {
        "STORAGE_DIR": paths.storage_dir,
        "DB_PATH": paths.db_path,
        "EVENT_LOG_PATH": paths.event_log_path,
        "SUMMARY_DIR": paths.summary_dir,
        "DISTILLED_DIR": paths.distilled_dir,
    }
    if name in values:
        return values[name]
    raise AttributeError(name)


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_def: str,
) -> None:
    if column_name not in _column_names(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def ensure_storage_layout(
    scope: str | None = None,
    cwd: str | Path | None = None,
    *,
    project_root_override: str | Path | None = None,
) -> dict[str, str]:
    paths = resolve_storage_paths(
        scope=scope,
        cwd=cwd,
        project_root_override=project_root_override,
    )
    paths.storage_dir.mkdir(parents=True, exist_ok=True)
    paths.summary_dir.mkdir(parents=True, exist_ok=True)
    paths.distilled_dir.mkdir(parents=True, exist_ok=True)

    if not paths.event_log_path.exists():
        paths.event_log_path.write_text("", encoding="utf-8")

    with closing(sqlite3.connect(paths.db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plugin_meta (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_state (
                task_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS repo_decision (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                title TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_summary (
                task_id TEXT PRIMARY KEY,
                summary_markdown TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS distilled_asset (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                asset_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                file_path TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(conn, "repo_decision", "task_id", "TEXT")
        _ensure_column(conn, "task_summary", "updated_at", "TEXT")
        conn.execute(
            """
            UPDATE task_summary
            SET updated_at = COALESCE(updated_at, created_at)
            WHERE updated_at IS NULL OR updated_at = ''
            """
        )
        conn.commit()

    return paths.as_dict()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize storage for the Codex Memory plugin."
    )
    parser.add_argument("--scope", choices=["project", "global", "auto"], help="Memory scope")
    parser.add_argument("--cwd", help="Directory used to resolve project storage")
    args = parser.parse_args()

    layout = ensure_storage_layout(scope=args.scope, cwd=args.cwd)
    for key, value in layout.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
