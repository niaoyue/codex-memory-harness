from __future__ import annotations

from pathlib import Path

from install_support import POSIX_PROFILE_END, POSIX_PROFILE_START, PROFILE_END, PROFILE_START


def profile_block(home_plugin: Path) -> str:
    launcher = home_plugin / "scripts" / "codexm.ps1"
    return f"""
{PROFILE_START}
function codexm {{
    & "{launcher}" @args
}}

function codex {{
    & "{launcher}" @args
}}

function codex-raw {{
    $env:CODEX_MEMORY_DISABLE_WRAPPER = "1"
    try {{
        & "{launcher}" -SkipBootstrap @args
    }} finally {{
        Remove-Item Env:\\CODEX_MEMORY_DISABLE_WRAPPER -ErrorAction SilentlyContinue
    }}
}}

function codex-memory-doctor {{
    & "{launcher}" memory doctor
}}
{PROFILE_END}
"""


def posix_profile_block(home_plugin: Path) -> str:
    launcher = _shell_quote(str(home_plugin / "scripts" / "codexm.sh"))
    return f"""
{POSIX_PROFILE_START}
_codex_memory_launcher={launcher}
unalias codex codexm codex-raw codex-memory-doctor 2>/dev/null || true
codexm() {{
    sh "$_codex_memory_launcher" "$@"
}}
codex() {{
    sh "$_codex_memory_launcher" "$@"
}}
_codex_memory_raw() {{
    if [ "${{1:-}}" = "--" ]; then
        shift
    fi
    CODEX_MEMORY_DISABLE_WRAPPER=1 sh "$_codex_memory_launcher" "$@"
}}
if [ -n "${{BASH_VERSION:-}}" ] && [ -z "${{POSIXLY_CORRECT:-}}" ]; then
    eval 'codex-raw() {{ _codex_memory_raw "$@"; }}'
    eval 'codex-memory-doctor() {{ sh "$_codex_memory_launcher" memory doctor "$@"; }}'
fi
alias codex-raw='_codex_memory_raw'
alias codex-memory-doctor='sh "$_codex_memory_launcher" memory doctor'
{POSIX_PROFILE_END}
"""


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
