from __future__ import annotations

from pathlib import Path
from typing import Any

from install_support import (
    POSIX_PROFILE_END,
    POSIX_PROFILE_START,
    PROFILE_END,
    PROFILE_START,
    ensure_posix_profile,
    ensure_profile,
    posix_profile_paths,
    profile_paths,
    remove_marked_block,
)


POWERSHELL_PROFILE_SHELLS = {"pwsh", "windows"}
POSIX_PROFILE_SHELLS = {"profile", "bash", "zsh"}
SHARED_PROFILE_SHELLS = {"all", "none"}


def ensure_launcher_profiles(
    home_plugin: Path,
    profile_shells: str,
    launcher_family: str,
) -> dict[str, Any]:
    if launcher_family == "posix":
        posix_shells = _install_profile_shells(profile_shells, "posix")
        return {
            "powershell_profiles": {
                "skipped": True,
                "reason": "launcher_family_posix",
            },
            "posix_profiles": ensure_posix_profile(home_plugin, posix_shells),
        }
    powershell_shells = _install_profile_shells(profile_shells, "powershell")
    return {
        "powershell_profiles": ensure_profile(home_plugin, powershell_shells),
        "posix_profiles": {
            "skipped": True,
            "reason": "launcher_family_not_posix",
        },
    }


def remove_launcher_profiles(profile_shells: str, launcher_family: str = "powershell") -> dict[str, Any]:
    powershell_shells, posix_shells = _uninstall_profile_shells(profile_shells, launcher_family)
    return {
        "powershell_profiles": [
            remove_marked_block(path, PROFILE_START, PROFILE_END)
            for path in profile_paths(powershell_shells)
        ],
        "posix_profiles": [
            remove_marked_block(path, POSIX_PROFILE_START, POSIX_PROFILE_END)
            for path in posix_profile_paths(posix_shells)
        ],
    }


def _install_profile_shells(profile_shells: str, launcher_family: str) -> str:
    if launcher_family == "posix":
        if profile_shells == "auto":
            return "all"
        if profile_shells in POSIX_PROFILE_SHELLS or profile_shells in SHARED_PROFILE_SHELLS:
            return profile_shells
        return "none"
    if profile_shells == "auto":
        return "pwsh"
    if profile_shells in POWERSHELL_PROFILE_SHELLS or profile_shells in SHARED_PROFILE_SHELLS:
        return profile_shells
    return "none"


def _uninstall_profile_shells(profile_shells: str, launcher_family: str) -> tuple[str, str]:
    if profile_shells == "auto":
        return ("none", "all") if launcher_family == "posix" else ("pwsh", "none")
    if profile_shells in SHARED_PROFILE_SHELLS:
        return profile_shells, profile_shells
    if profile_shells in POWERSHELL_PROFILE_SHELLS:
        return profile_shells, "none"
    if profile_shells in POSIX_PROFILE_SHELLS:
        return "none", profile_shells
    return "none", "none"
