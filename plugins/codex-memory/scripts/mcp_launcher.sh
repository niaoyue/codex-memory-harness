#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PLUGIN_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
MEMORY_SERVER="$PLUGIN_ROOT/mcp/memory_server.py"
PY_CMD=
PY_PREFIX=
PY_NAME=
DETECTED=

debug_log() {
    case "${CODEX_MEMORY_INSTALL_DEBUG:-}" in
        1|true|TRUE|yes|YES|on|ON|debug|DEBUG)
            printf '%s\n' "[codex-memory-mcp][DEBUG] $1" >&2
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
    try_python py "-3" && return 0
    try_python python "" && return 0
    try_python python3 "" && return 0
    try_python python3.14 "" && return 0
    try_python python3.13 "" && return 0
    try_python python3.12 "" && return 0
    try_python python3.11 "" && return 0
    return 1
}

resolve_python || true
if [ -z "$PY_CMD" ]; then
    echo "Python 3.11 or newer is required to run Codex Memory MCP." >&2
    if [ -n "$DETECTED" ]; then
        echo "Detected Python command(s): $DETECTED" >&2
        exit 126
    fi
    exit 127
fi

debug_log "runtime=$PY_NAME prefix_arg_count=$([ -n "$PY_PREFIX" ] && echo 1 || echo 0) server=memory_server.py"

if [ -n "$PY_PREFIX" ]; then
    "$PY_CMD" "$PY_PREFIX" -X utf8 "$MEMORY_SERVER" "$@"
else
    "$PY_CMD" -X utf8 "$MEMORY_SERVER" "$@"
fi
exit $?
