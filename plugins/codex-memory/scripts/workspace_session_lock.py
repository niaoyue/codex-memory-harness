from __future__ import annotations

import os
import secrets
import time
from pathlib import Path


LOCK_TIMEOUT_SECONDS = 30.0
LOCK_STALE_SECONDS = 300.0
OWNED_LOCK_TOKENS: dict[Path, str] = {}


def acquire_registry_lock(registry_path: Path, created_at: str) -> Path:
    lock_path = registry_path.with_name(f"{registry_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            token = secrets.token_hex(16)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"pid={os.getpid()} token={token} created_at={created_at}\n".encode("utf-8"))
            finally:
                os.close(fd)
            OWNED_LOCK_TOKENS[lock_key(lock_path)] = token
            return lock_path
        except FileExistsError:
            reclaim_stale_lock(lock_path)
            if time.monotonic() >= deadline:
                raise RuntimeError(f"registry lock timeout: {lock_path}")
            time.sleep(0.05)


def reclaim_stale_lock(lock_path: Path) -> bool:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return False
    if age < LOCK_STALE_SECONDS:
        return False
    owner_pid = lock_owner_pid(lock_path)
    if owner_pid is not None and process_is_alive(owner_pid):
        return False
    try:
        lock_path.unlink()
        return True
    except FileNotFoundError:
        return True


def release_registry_lock(lock_path: Path) -> None:
    token = OWNED_LOCK_TOKENS.pop(lock_key(lock_path), None)
    if token is None or lock_owner_token(lock_path) != token:
        return
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def lock_key(lock_path: Path) -> Path:
    return lock_path.resolve(strict=False)


def lock_owner_pid(lock_path: Path) -> int | None:
    value = lock_owner_field(lock_path, "pid")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def lock_owner_token(lock_path: Path) -> str | None:
    return lock_owner_field(lock_path, "token")


def lock_owner_field(lock_path: Path, name: str) -> str | None:
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    for part in text.split():
        if part.startswith(f"{name}="):
            return part.split("=", 1)[1]
    return None


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
