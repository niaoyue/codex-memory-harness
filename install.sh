#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
INSTALLER="$SCRIPT_DIR/plugins/codex-memory/scripts/install_codex_memory.py"
AUTO_INSTALL=${CODEX_MEMORY_AUTO_INSTALL_PYTHON:-0}
PY_CMD=
PY_NAME=
PY_PREFIX=
DETECTED=

python_version_text() {
    command_name=$1
    prefix_arg=${2:-}
    if [ -n "$prefix_arg" ]; then
        "$command_name" "$prefix_arg" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null
    else
        "$command_name" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null
    fi
}

python_version_ok() {
    command_name=$1
    prefix_arg=${2:-}
    if [ -n "$prefix_arg" ]; then
        "$command_name" "$prefix_arg" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
    else
        "$command_name" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
    fi
}

try_python() {
    command_name=$1
    prefix_arg=${2:-}
    command -v "$command_name" >/dev/null 2>&1 || return 1
    version_text=$(python_version_text "$command_name" "$prefix_arg" || true)
    if [ -n "$version_text" ]; then
        if [ -n "$DETECTED" ]; then
            DETECTED="$DETECTED, $command_name $version_text"
        else
            DETECTED="$command_name $version_text"
        fi
    fi
    python_version_ok "$command_name" "$prefix_arg" || return 1
    PY_CMD=$command_name
    PY_NAME=$command_name
    PY_PREFIX=$prefix_arg
    return 0
}

resolve_python() {
    PY_CMD=
    PY_NAME=
    PY_PREFIX=
    DETECTED=
    try_python py "-3" && return 0
    try_python python "" && return 0
    try_python python3 "" && return 0
    try_python python3.14 "" && return 0
    try_python python3.13 "" && return 0
    try_python python3.12 "" && return 0
    try_python python3.11 "" && return 0
    return 1
}

run_as_root() {
    if [ "$(id -u 2>/dev/null || echo 1)" = "0" ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        echo "sudo was not found. Install Python 3.11+ manually, then rerun sh ./install.sh." >&2
        return 1
    fi
}

require_powershell_launcher() {
    if command -v powershell >/dev/null 2>&1; then
        return 0
    fi
    echo "install.sh currently supports POSIX shells only when the powershell command is available." >&2
    echo "Codex Memory hooks and MCP still invoke the PowerShell launcher command named powershell." >&2
    if command -v pwsh >/dev/null 2>&1; then
        echo "Detected pwsh, but this release does not generate native pwsh/POSIX hook launchers yet." >&2
    fi
    echo "Use install.bat or install.ps1 on Windows, or run from a Windows POSIX shell with powershell on PATH." >&2
    exit 125
}

install_python_best_effort() {
    if command -v brew >/dev/null 2>&1; then
        brew install python@3.12 || brew install python
        return $?
    fi
    if command -v apt-get >/dev/null 2>&1; then
        run_as_root apt-get update &&
            (run_as_root apt-get install -y python3.12 python3.12-venv ||
                run_as_root apt-get install -y python3 python3-venv)
        return $?
    fi
    if command -v dnf >/dev/null 2>&1; then
        run_as_root dnf install -y python3.12 || run_as_root dnf install -y python3
        return $?
    fi
    if command -v yum >/dev/null 2>&1; then
        run_as_root yum install -y python3.12 || run_as_root yum install -y python3
        return $?
    fi
    if command -v pacman >/dev/null 2>&1; then
        run_as_root pacman -Sy --needed --noconfirm python
        return $?
    fi
    echo "No supported package manager was found for automatic Python installation." >&2
    return 1
}

write_python_hint() {
    echo "Python 3.11 or newer is required to run the Codex Memory installer."
    if [ -n "$DETECTED" ]; then
        echo "Detected Python command(s): $DETECTED"
    fi
    echo "Install Python, then rerun: sh ./install.sh"
    echo "macOS Homebrew: brew install python@3.12"
    echo "Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y python3"
    echo "Fedora: sudo dnf install -y python3.12"
    echo "Arch: sudo pacman -Sy --needed python"
    echo "Manual installer: https://www.python.org/downloads/"
    echo "To let this script try a supported package manager, rerun: sh ./install.sh --install-python"
}

run_installer() {
    if [ -n "$PY_PREFIX" ]; then
        "$PY_CMD" "$PY_PREFIX" -X utf8 "$INSTALLER" \
            --mcp-python-command "$PY_NAME" \
            --mcp-python-prefix-arg "$PY_PREFIX" \
            "$@"
    else
        "$PY_CMD" -X utf8 "$INSTALLER" \
            --mcp-python-command "$PY_NAME" \
            "$@"
    fi
}

remaining=$#
while [ "$remaining" -gt 0 ]; do
    arg=$1
    shift
    remaining=$((remaining - 1))
    case "$arg" in
        --install-python)
            AUTO_INSTALL=1
            ;;
        -UpdateExisting)
            set -- "$@" "--update-existing"
            ;;
        -ReplaceExisting)
            set -- "$@" "--replace-existing"
            ;;
        -SkipAgents)
            set -- "$@" "--skip-agents"
            ;;
        -RemoveHomePlugin)
            set -- "$@" "--remove-home-plugin"
            ;;
        -ProfileShells)
            if [ "$remaining" -eq 0 ]; then
                echo "-ProfileShells requires a value: pwsh, windows, all, or none." >&2
                exit 2
            fi
            value=$1
            shift
            remaining=$((remaining - 1))
            set -- "$@" "--profile-shells" "$value"
            ;;
        -Mode)
            if [ "$remaining" -eq 0 ]; then
                echo "-Mode requires a value: auto, junction, or copy." >&2
                exit 2
            fi
            value=$1
            shift
            remaining=$((remaining - 1))
            set -- "$@" "--mode" "$value"
            ;;
        *)
            set -- "$@" "$arg"
            ;;
    esac
done

require_powershell_launcher
resolve_python || true
if [ -z "$PY_CMD" ]; then
    if [ "$AUTO_INSTALL" = "1" ]; then
        install_python_best_effort || {
            write_python_hint
            exit 1
        }
        resolve_python || true
    fi
    if [ -z "$PY_CMD" ]; then
        write_python_hint
        if [ -n "$DETECTED" ]; then
            exit 126
        fi
        exit 127
    fi
fi

run_installer "$@"
