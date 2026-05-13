from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import init_storage


LOGGER = logging.getLogger(__name__)
DB_TABLES = ("task_state", "task_summary", "repo_decision", "distilled_asset")
HISTORY_DIR = "history"
ARCHIVE_DIR = "archives"


@dataclass(frozen=True)
class RetentionPaths:
    storage_dir: Path
    db_path: Path
    history_dir: Path
    archive_dir: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_archive_name(task_id: str) -> str:
    chars = [c if c.isalnum() or c in "._-" else "_" for c in task_id.strip()]
    name = "".join(chars).strip("._")
    return name or "task"


def _paths(scope: str | None = None, cwd: str | Path | None = None) -> RetentionPaths:
    layout = init_storage.ensure_storage_layout(scope=scope, cwd=cwd)
    storage_dir = Path(layout["storage_dir"])
    return RetentionPaths(
        storage_dir=storage_dir,
        db_path=Path(layout["db_path"]),
        history_dir=storage_dir / HISTORY_DIR,
        archive_dir=storage_dir / ARCHIVE_DIR,
    )


@contextmanager
def _connect(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _rows_for_task(conn: sqlite3.Connection, table: str, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {table} WHERE task_id = ?", (task_id,)).fetchall()
    return [dict(row) for row in rows]


def _jsonl_paths(history_dir: Path) -> list[Path]:
    if not history_dir.exists():
        return []
    return sorted(path for path in history_dir.glob("*.jsonl") if path.is_file())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            LOGGER.debug("memory retention skipped invalid jsonl line in %s", path.name)
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def _write_jsonl(path: Path, items: Iterable[dict[str, Any]]) -> None:
    lines = [json.dumps(item, ensure_ascii=False) for item in items]
    content = "\n".join(lines) + ("\n" if lines else "")
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _record_task_id(record: dict[str, Any]) -> str:
    payload = record.get("payload")
    nested_payload = payload.get("payload") if isinstance(payload, dict) else None
    candidates = [
        record.get("task_id"),
        payload.get("task_id") if isinstance(payload, dict) else None,
        nested_payload.get("task_id") if isinstance(nested_payload, dict) else None,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _history_matches(paths: RetentionPaths, task_id: str) -> dict[str, list[dict[str, Any]]]:
    matches: dict[str, list[dict[str, Any]]] = {}
    for path in _jsonl_paths(paths.history_dir):
        matched = [item for item in _read_jsonl(path) if _record_task_id(item) == task_id]
        if matched:
            matches[path.name] = matched
    return matches


def retention_status(*, scope: str | None = None, cwd: str | Path | None = None) -> dict[str, Any]:
    paths = _paths(scope=scope, cwd=cwd)
    with _connect(paths.db_path) as conn:
        table_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in DB_TABLES
        }
    history_counts = {
        path.name: len(_read_jsonl(path))
        for path in _jsonl_paths(paths.history_dir)
    }
    return {
        "ok": True,
        "storage_dir": str(paths.storage_dir),
        "db_path": str(paths.db_path),
        "history_dir": str(paths.history_dir),
        "archive_dir": str(paths.archive_dir),
        "table_counts": table_counts,
        "history_counts": history_counts,
    }


def build_task_plan(
    task_id: str,
    *,
    scope: str | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    if not task_id.strip():
        raise ValueError("task_id is required")
    paths = _paths(scope=scope, cwd=cwd)
    with _connect(paths.db_path) as conn:
        rows = {table: _rows_for_task(conn, table, task_id) for table in DB_TABLES}
    history = _history_matches(paths, task_id)
    counts = {
        "db_rows": {table: len(items) for table, items in rows.items()},
        "history_records": {name: len(items) for name, items in history.items()},
    }
    total = sum(counts["db_rows"].values()) + sum(counts["history_records"].values())
    return {
        "ok": True,
        "task_id": task_id,
        "mode": "dry-run",
        "would_change": total > 0,
        "counts": counts,
        "archive_path": "",
        "storage_dir": str(paths.storage_dir),
        "db_rows": rows,
        "history_records": history,
    }


def dry_run_task(
    task_id: str,
    *,
    scope: str | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    LOGGER.debug("memory retention dry-run started for task_id=%s", task_id)
    return build_task_plan(task_id, scope=scope, cwd=cwd)


def confirm_task(
    task_id: str,
    *,
    scope: str | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    plan = build_task_plan(task_id, scope=scope, cwd=cwd)
    if not plan["would_change"]:
        LOGGER.debug("memory retention confirm found no records for task_id=%s", task_id)
        return plan | {"mode": "confirm", "changed": False}

    paths = _paths(scope=scope, cwd=cwd)
    paths.archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = paths.archive_dir / f"{_safe_archive_name(task_id)}-{timestamp}.json"
    archive = {
        "archived_at": _utc_now(),
        "task_id": task_id,
        "counts": plan["counts"],
        "db_rows": plan["db_rows"],
        "history_records": plan["history_records"],
    }
    archive_path.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")

    with _connect(paths.db_path) as conn:
        for table in DB_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE task_id = ?", (task_id,))
        conn.commit()

    for path in _jsonl_paths(paths.history_dir):
        kept = [item for item in _read_jsonl(path) if _record_task_id(item) != task_id]
        _write_jsonl(path, kept)

    LOGGER.debug(
        "memory retention confirm archived and removed task_id=%s archive=%s",
        task_id,
        archive_path,
    )
    return plan | {
        "mode": "confirm",
        "changed": True,
        "archive_path": str(archive_path),
    }


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive and clean Codex Memory task records.")
    _add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show retention storage counts.")
    _add_common_args(status_parser, suppress_default=True)
    cleanup = subparsers.add_parser("cleanup", help="Archive and clean records for one task_id.")
    _add_common_args(cleanup, suppress_default=True)
    cleanup.add_argument("--task-id", required=True, help="Task id to archive and clean.")
    cleanup.add_argument(
        "--confirm",
        action="store_true",
        help="Apply cleanup. Omit this flag for dry-run.",
    )
    cleanup.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request dry-run. This is the default.",
    )

    args = parser.parse_args(argv)
    if args.command == "status":
        _print_json(retention_status(scope=args.scope, cwd=args.cwd))
        return 0
    if args.command == "cleanup":
        if args.confirm and args.dry_run:
            parser.error("--confirm and --dry-run are mutually exclusive")
        result = (
            confirm_task(args.task_id, scope=args.scope, cwd=args.cwd)
            if args.confirm
            else dry_run_task(args.task_id, scope=args.scope, cwd=args.cwd)
        )
        _print_json(result)
        return 0
    parser.error("unknown command")
    return 2


def _add_common_args(parser: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_default else None
    parser.add_argument(
        "--scope",
        choices=["project", "global", "auto"],
        default=default,
        help="Memory scope",
    )
    parser.add_argument(
        "--cwd",
        default=default,
        help="Directory used to resolve project storage",
    )


if __name__ == "__main__":
    raise SystemExit(main())
