#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
INSTALLER="$SCRIPT_DIR/plugins/codex-memory/scripts/install_codex_memory.py"
AUTO_INSTALL=${CODEX_MEMORY_AUTO_INSTALL_PYTHON:-0}
DRY_RUN=0
PY_CMD=
PY_NAME=
PY_PREFIX=
DETECTED=
LAUNCHER_FAMILY=${CODEX_MEMORY_LAUNCHER_FAMILY:-}

debug_log() {
    case "${CODEX_MEMORY_INSTALL_DEBUG:-}" in
        1|true|TRUE|yes|YES|on|ON|debug|DEBUG)
            printf '%s\n' "[codex-memory-install.sh][DEBUG] $1" >&2
            ;;
    esac
}

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

normalize_launcher_family() {
    if [ -z "$LAUNCHER_FAMILY" ]; then
        case "$(uname -s 2>/dev/null || echo unknown)" in
            MINGW*|MSYS*|CYGWIN*)
                if command -v powershell >/dev/null 2>&1; then
                    LAUNCHER_FAMILY=powershell
                else
                    LAUNCHER_FAMILY=posix
                fi
                ;;
            *)
                LAUNCHER_FAMILY=posix
                ;;
        esac
    fi
    case "$LAUNCHER_FAMILY" in
        posix|powershell)
            ;;
        *)
            echo "CODEX_MEMORY_LAUNCHER_FAMILY must be posix or powershell." >&2
            exit 2
            ;;
    esac
}

require_launcher_family() {
    normalize_launcher_family
    if [ "$LAUNCHER_FAMILY" = "powershell" ] && ! command -v powershell >/dev/null 2>&1; then
        echo "CODEX_MEMORY_LAUNCHER_FAMILY=powershell requires a powershell command on PATH." >&2
        echo "Use the default POSIX launcher on Linux/macOS, or run from a Windows POSIX shell with powershell on PATH." >&2
        exit 125
    fi
    debug_log "launcher_family=$LAUNCHER_FAMILY powershell_available=$(command -v powershell >/dev/null 2>&1 && echo 1 || echo 0)"
}

install_python_best_effort() {
    if command -v brew >/dev/null 2>&1; then
        brew install python@3.12 || brew install python
        return $?
    fi
    if command -v apt-get >/dev/null 2>&1; then
        run_as_root apt-get update &&
            (run_as_root apt-get install -y python3.12 python3.12-venv ||
                run_as_root apt-get install -y python3.11 python3.11-venv ||
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
    echo "Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y python3.11"
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
            --launcher-family "$LAUNCHER_FAMILY" \
            "$@"
    else
        "$PY_CMD" -X utf8 "$INSTALLER" \
            --mcp-python-command "$PY_NAME" \
            --launcher-family "$LAUNCHER_FAMILY" \
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
        --dry-run)
            DRY_RUN=1
            AUTO_INSTALL=0
            set -- "$@" "--dry-run"
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
        -SkipSkills)
            set -- "$@" "--skip-skills"
            ;;
        -DryRun)
            DRY_RUN=1
            AUTO_INSTALL=0
            set -- "$@" "--dry-run"
            ;;
        -RemoveHomePlugin)
            set -- "$@" "--remove-home-plugin"
            ;;
        --launcher-family)
            if [ "$remaining" -eq 0 ]; then
                echo "--launcher-family requires a value: posix or powershell." >&2
                exit 2
            fi
            LAUNCHER_FAMILY=$1
            shift
            remaining=$((remaining - 1))
            ;;
        --launcher-family=*)
            LAUNCHER_FAMILY=${arg#*=}
            ;;
        -LauncherFamily)
            if [ "$remaining" -eq 0 ]; then
                echo "-LauncherFamily requires a value: posix or powershell." >&2
                exit 2
            fi
            LAUNCHER_FAMILY=$1
            shift
            remaining=$((remaining - 1))
            ;;
        -ProfileShells)
            if [ "$remaining" -eq 0 ]; then
                echo "-ProfileShells requires a value: auto, pwsh, windows, all, none, profile, bash, or zsh." >&2
                exit 2
            fi
            value=$1
            shift
            remaining=$((remaining - 1))
            set -- "$@" "--profile-shells" "$value"
            ;;
        -Mode)
            if [ "$remaining" -eq 0 ]; then
                echo "-Mode requires a value: auto, junction, symlink, or copy." >&2
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

require_launcher_family
resolve_python || true
if [ -z "$PY_CMD" ]; then
    if [ "$DRY_RUN" != "1" ] && [ "$AUTO_INSTALL" = "1" ]; then
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

debug_log "python_command=$PY_NAME prefix_arg_count=$([ -n "$PY_PREFIX" ] && echo 1 || echo 0)"
run_installer "$@"
