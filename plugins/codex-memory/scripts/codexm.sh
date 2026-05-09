#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PLUGIN_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH= cd "$PLUGIN_ROOT/../.." 2>/dev/null && pwd || pwd)
BOOTSTRAP_SCRIPT="$SCRIPT_DIR/codex_bootstrap.py"
HARNESS_SCRIPT="$SCRIPT_DIR/harness_controller.py"
HOOK_SCRIPT="$SCRIPT_DIR/hook_runner.py"
INSTALL_SCRIPT="$SCRIPT_DIR/install_codex_memory.py"
VERIFICATION_SCRIPT="$SCRIPT_DIR/verification_runner.py"
SHARED_MEMORY_SCRIPT="$SCRIPT_DIR/shared_memory.py"
LEGACY_GLOBAL_MIGRATION_SCRIPT="$SCRIPT_DIR/legacy_global_memory_migration.py"
WORKSPACE_SCRIPT="$SCRIPT_DIR/workspace_scanner.py"
WORKSPACE_ROUTER_SCRIPT="$SCRIPT_DIR/workspace_router.py"
WORKSPACE_VERIFIER_SCRIPT="$SCRIPT_DIR/workspace_verifier.py"
WORKSPACE_SUBAGENTS_SCRIPT="$SCRIPT_DIR/workspace_subagents.py"
SUBAGENT_SCHEDULER_SCRIPT="$SCRIPT_DIR/subagent_scheduler.py"
WORKSPACE_SESSION_SCRIPT="$SCRIPT_DIR/workspace_session.py"
REVIEW_GATE_SCRIPT="$SCRIPT_DIR/review_gate_runner.py"
REVIEW_WORKFLOW_SCRIPT="$SCRIPT_DIR/review_workflow.py"
GAME_CLIENT_PROFILES_SCRIPT="$SCRIPT_DIR/game_client_profiles.py"
WORKSPACE_BUSINESS_TEMPLATES_SCRIPT="$SCRIPT_DIR/workspace_business_templates.py"
HOOK_BRIDGE_SCRIPT="$SCRIPT_DIR/hook_bridge.py"
REVIEW_GATE_IDLE_SECONDS=1800
SKIP_BOOTSTRAP=0
DOCTOR_ONLY=0
INIT_PROJECT=0
VERBOSE_BOOTSTRAP=0
PY_CMD=
PY_PREFIX=
PY_NAME=
DETECTED=

debug_log() {
    case "${CODEX_MEMORY_WRAPPER_DEBUG:-${CODEX_MEMORY_INSTALL_DEBUG:-}}" in
        1|true|TRUE|yes|YES|on|ON|debug|DEBUG)
            printf '%s\n' "[codex-memory-wrapper][DEBUG] $1" >&2
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
    [ -n "$PY_CMD" ] && return 0
    try_python py "-3" && return 0
    try_python python "" && return 0
    try_python python3 "" && return 0
    try_python python3.14 "" && return 0
    try_python python3.13 "" && return 0
    try_python python3.12 "" && return 0
    try_python python3.11 "" && return 0
    return 1
}

require_python() {
    resolve_python || true
    if [ -n "$PY_CMD" ]; then
        return 0
    fi
    echo "Python 3.11 or newer is required to run Codex Memory commands." >&2
    if [ -n "$DETECTED" ]; then
        echo "Detected Python command(s): $DETECTED" >&2
        exit 126
    fi
    exit 127
}

run_py() {
    script_path=$1
    shift
    require_python
    debug_log "dispatch=python script=$(basename "$script_path") arg_count=$# runtime=$PY_NAME prefix_arg_count=$([ -n "$PY_PREFIX" ] && echo 1 || echo 0)"
    if [ -n "$PY_PREFIX" ]; then
        exec "$PY_CMD" "$PY_PREFIX" -X utf8 "$script_path" "$@"
    fi
    exec "$PY_CMD" -X utf8 "$script_path" "$@"
}

find_real_codex() {
    command -v codex 2>/dev/null || true
}

invoke_real_codex() {
    codex_path=$(find_real_codex)
    if [ -z "$codex_path" ]; then
        echo "Unable to find the real codex command in PATH." >&2
        exit 127
    fi
    debug_log "dispatch=real_codex path=$codex_path arg_count=$#"
    exec "$codex_path" "$@"
}

run_py_capture() {
    script_path=$1
    shift
    require_python
    debug_log "dispatch=python_capture script=$(basename "$script_path") arg_count=$# runtime=$PY_NAME prefix_arg_count=$([ -n "$PY_PREFIX" ] && echo 1 || echo 0)"
    if [ -n "$PY_PREFIX" ]; then
        "$PY_CMD" "$PY_PREFIX" -X utf8 "$script_path" "$@"
    else
        "$PY_CMD" -X utf8 "$script_path" "$@"
    fi
}

write_bootstrap_meta() {
    doctor_file=$1
    require_python
    if [ -n "$PY_PREFIX" ]; then
        "$PY_CMD" "$PY_PREFIX" -X utf8 -c 'import json, shlex, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
project = data.get("project") if isinstance(data.get("project"), dict) else {}
env = data.get("recommended_env") if isinstance(data.get("recommended_env"), dict) else {}
init_needed = bool(project.get("detected")) and any(not bool(checks.get(k)) for k in ("project_memory_exists", "project_commands_exists", "project_profile_exists", "project_shared_exists", "project_shared_index_exists"))
print(f"INIT_NEEDED={1 if init_needed else 0}")
print("CODEX_MEMORY_SCOPE_VALUE=" + shlex.quote(str(env.get("CODEX_MEMORY_SCOPE") or "")))
print("CODEX_MEMORY_CWD_VALUE=" + shlex.quote(str(env.get("CODEX_MEMORY_CWD") or "")))' "$doctor_file"
    else
        "$PY_CMD" -X utf8 -c 'import json, shlex, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
project = data.get("project") if isinstance(data.get("project"), dict) else {}
env = data.get("recommended_env") if isinstance(data.get("recommended_env"), dict) else {}
init_needed = bool(project.get("detected")) and any(not bool(checks.get(k)) for k in ("project_memory_exists", "project_commands_exists", "project_profile_exists", "project_shared_exists", "project_shared_index_exists"))
print(f"INIT_NEEDED={1 if init_needed else 0}")
print("CODEX_MEMORY_SCOPE_VALUE=" + shlex.quote(str(env.get("CODEX_MEMORY_SCOPE") or "")))
print("CODEX_MEMORY_CWD_VALUE=" + shlex.quote(str(env.get("CODEX_MEMORY_CWD") or "")))' "$doctor_file"
    fi
}

load_bootstrap_meta() {
    doctor_file=$1
    meta_file=$(mktemp "${TMPDIR:-/tmp}/codex-memory-meta.XXXXXX") || exit 1
    write_bootstrap_meta "$doctor_file" >"$meta_file"
    . "$meta_file"
    rm -f "$meta_file"
}

invoke_bootstrap() {
    [ "$SKIP_BOOTSTRAP" = "1" ] && return 0
    cwd=$(pwd)
    doctor_file=$(mktemp "${TMPDIR:-/tmp}/codex-memory-doctor.XXXXXX") || exit 1
    run_py_capture "$BOOTSTRAP_SCRIPT" --cwd "$cwd" --doctor >"$doctor_file"
    doctor_status=$?
    if [ "$DOCTOR_ONLY" = "1" ]; then
        cat "$doctor_file"
        rm -f "$doctor_file"
        exit "$doctor_status"
    fi
    load_bootstrap_meta "$doctor_file"
    if [ "$INIT_PROJECT" = "1" ] || [ "${INIT_NEEDED:-0}" = "1" ]; then
        init_file=$(mktemp "${TMPDIR:-/tmp}/codex-memory-init.XXXXXX") || exit 1
        run_py_capture "$BOOTSTRAP_SCRIPT" --cwd "$cwd" --init-project >"$init_file"
        init_status=$?
        [ "$VERBOSE_BOOTSTRAP" = "1" ] && cat "$init_file"
        rm -f "$init_file"
        if [ "$init_status" -ne 0 ]; then
            echo "Codex Memory project init reported a non-ready state." >&2
        fi
        run_py_capture "$BOOTSTRAP_SCRIPT" --cwd "$cwd" --doctor >"$doctor_file"
        doctor_status=$?
        load_bootstrap_meta "$doctor_file"
    fi
    [ "$VERBOSE_BOOTSTRAP" = "1" ] && cat "$doctor_file"
    [ -n "${CODEX_MEMORY_SCOPE_VALUE:-}" ] && export CODEX_MEMORY_SCOPE=$CODEX_MEMORY_SCOPE_VALUE
    [ -n "${CODEX_MEMORY_CWD_VALUE:-}" ] && export CODEX_MEMORY_CWD=$CODEX_MEMORY_CWD_VALUE
    rm -f "$doctor_file"
    if [ "$doctor_status" -ne 0 ]; then
        echo "Codex Memory bootstrap reported a non-ready state; launching Codex with degraded memory support." >&2
    fi
}

write_memory_help() {
    cat <<'EOF'
Codex Memory commands:
  codex memory doctor/init/install/update/check-install/uninstall
  codex memory hook <event> [...]
  codex memory promote --task-id <task-id> [--kind fact]
  codex memory shared validate|index rebuild
  codex memory migrate-legacy-global [--dry-run|--confirm]
EOF
}

write_harness_help() {
    cat <<'EOF'
Codex Harness commands:
  codex harness start --task-file task.json
  codex harness checkpoint --task-id <task-id> --result-file result.json
  codex harness complete --task-id <task-id> --summary-file summary.md
  codex harness verify list
  codex harness verify run --profile primary
EOF
}

write_package_help() {
    cat <<'EOF'
Codex Package commands:
  codex package build
  codex package verify
EOF
}

write_workspace_help() {
    cat <<'EOF'
Codex Workspace commands:
  doctor|scan|route|verify|bind|schedule|scope-check|summarize
  session status|bind|heartbeat|release
  worktree list
  worktree prune --dry-run
  write-guard --session-id <id> --task-id <id> [--path <path>]
  game-client init --engine unity|laya|cocos
  project-template init --domain game_server|backoffice_web|design_docs|art_pipeline
EOF
}

resolve_repo_script() {
    script_name=$1
    cwd=$(pwd)
    if [ -f "$cwd/scripts/$script_name" ]; then
        printf '%s\n' "$cwd/scripts/$script_name"
        return 0
    fi
    if [ -f "$REPO_ROOT/scripts/$script_name" ]; then
        printf '%s\n' "$REPO_ROOT/scripts/$script_name"
        return 0
    fi
    echo "Cannot find $script_name. Run this command from the Codex Memory Harness repository root." >&2
    exit 64
}

run_repo_py() {
    script_path=$(resolve_repo_script "$1") || exit $?
    shift
    run_py "$script_path" "$@"
}

invoke_memory() {
    cwd=$(pwd)
    command_name=${1:-help}
    [ "$#" -gt 0 ] && shift
    case "$command_name" in
        help|-h|--help) write_memory_help; exit 0 ;;
        doctor|status) run_py "$BOOTSTRAP_SCRIPT" --cwd "$cwd" --doctor ;;
        init|init-project) run_py "$BOOTSTRAP_SCRIPT" --cwd "$cwd" --init-project ;;
        install) run_py "$INSTALL_SCRIPT" --launcher-family posix "$@" ;;
        update) run_py "$INSTALL_SCRIPT" --update-existing --launcher-family posix "$@" ;;
        check-install|check) run_py "$INSTALL_SCRIPT" --check ;;
        uninstall) run_py "$INSTALL_SCRIPT" --uninstall --launcher-family posix "$@" ;;
        hook)
            if [ "$#" -eq 0 ]; then
                echo "Missing hook event. Run 'codex memory help' for usage." >&2
                exit 64
            fi
            case "$1" in
                -*) run_py "$HOOK_SCRIPT" "$@" ;;
                *) hook_event=$1; shift; run_py "$HOOK_SCRIPT" --event "$hook_event" "$@" ;;
            esac
            ;;
        codex-hook) run_py "$HOOK_BRIDGE_SCRIPT" "$@" ;;
        promote) run_py "$SHARED_MEMORY_SCRIPT" --project-root "$cwd" promote "$@" ;;
        shared) run_py "$SHARED_MEMORY_SCRIPT" --project-root "$cwd" shared "$@" ;;
        migrate-legacy-global) run_py "$LEGACY_GLOBAL_MIGRATION_SCRIPT" "$@" ;;
        verify) invoke_harness verify "$@" ;;
        harness) invoke_harness "$@" ;;
        *) echo "Unknown Codex Memory command: $command_name. Run 'codex memory help' for usage." >&2; exit 64 ;;
    esac
}

invoke_harness() {
    cwd=$(pwd)
    command_name=${1:-help}
    [ "$#" -gt 0 ] && shift
    case "$command_name" in
        help|-h|--help) write_harness_help; exit 0 ;;
        start|checkpoint|complete) run_py "$HARNESS_SCRIPT" --project-root "$cwd" "$command_name" "$@" ;;
        verify) run_py "$VERIFICATION_SCRIPT" --project-root "$cwd" "$@" ;;
        *) echo "Unknown Codex Harness command: $command_name. Run 'codex harness help' for usage." >&2; exit 64 ;;
    esac
}

invoke_package() {
    command_name=${1:-help}
    [ "$#" -gt 0 ] && shift
    case "$command_name" in
        help|-h|--help) write_package_help; exit 0 ;;
        build) run_repo_py build_release.py "$@" ;;
        verify|check) run_repo_py verify_project.py "$@" ;;
        *) echo "Unknown Codex Package command: $command_name. Run 'codex package help' for usage." >&2; exit 64 ;;
    esac
}

invoke_workspace() {
    cwd=$(pwd)
    command_name=${1:-help}
    [ "$#" -gt 0 ] && shift
    case "$command_name" in
        help|-h|--help) write_workspace_help; exit 0 ;;
        doctor|scan) run_py "$WORKSPACE_SCRIPT" --workspace-root "$cwd" "$command_name" "$@" ;;
        route) run_py "$WORKSPACE_ROUTER_SCRIPT" --workspace-root "$cwd" "$@" ;;
        verify) run_py "$WORKSPACE_VERIFIER_SCRIPT" --project-root "$cwd" "$@" ;;
        bind|scope-check|summarize) run_py "$WORKSPACE_SUBAGENTS_SCRIPT" --project-root "$cwd" "$command_name" "$@" ;;
        schedule) run_py "$SUBAGENT_SCHEDULER_SCRIPT" --project-root "$cwd" "$@" ;;
        session|worktree|write-guard) run_py "$WORKSPACE_SESSION_SCRIPT" --project-root "$cwd" "$command_name" "$@" ;;
        game-client) run_py "$GAME_CLIENT_PROFILES_SCRIPT" --project-root "$cwd" "$@" ;;
        project-template) run_py "$WORKSPACE_BUSINESS_TEMPLATES_SCRIPT" --project-root "$cwd" "$@" ;;
        *) echo "Unknown Codex Workspace command: $command_name. Run 'codex workspace help' for usage." >&2; exit 64 ;;
    esac
}

invoke_review() {
    cwd=$(pwd)
    command_name=${1:-help}
    case "$command_name" in
        help|-h|--help)
            echo "Codex Review commands: status|preflight|plan|record|findings list|findings resolve|ledger show"
            exit 0
            ;;
        *) run_py "$REVIEW_WORKFLOW_SCRIPT" --project-root "$cwd" "$@" ;;
    esac
}

is_harness_review_command() {
    [ "${1:-}" = "review" ] || return 1
    case "${2:-}" in
        status|preflight|plan|record|findings|ledger) return 0 ;;
        *) return 1 ;;
    esac
}

invoke_review_alias() {
    effort=$1
    shift 2
    codex_path=$(find_real_codex)
    if [ -z "$codex_path" ]; then
        echo "Unable to find the real codex command in PATH." >&2
        exit 127
    fi
    run_py "$REVIEW_GATE_SCRIPT" --codex "$codex_path" --effort "$effort" --idle-seconds "$REVIEW_GATE_IDLE_SECONDS" --max-seconds 0 --cwd "$(pwd)" -- "$@"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --skip-bootstrap|-SkipBootstrap)
            SKIP_BOOTSTRAP=1
            shift
            ;;
        --doctor-only|-DoctorOnly)
            DOCTOR_ONLY=1
            shift
            ;;
        --init-project|-InitProject)
            INIT_PROJECT=1
            shift
            ;;
        --verbose-bootstrap|-VerboseBootstrap)
            VERBOSE_BOOTSTRAP=1
            shift
            ;;
        *)
            break
            ;;
    esac
done

if [ "${CODEX_MEMORY_DISABLE_WRAPPER:-}" = "1" ]; then
    invoke_real_codex "$@"
fi

case "${1:-}" in
    memory) shift; invoke_memory "$@" ;;
    harness) shift; invoke_harness "$@" ;;
    package) shift; invoke_package "$@" ;;
    workspace) shift; invoke_workspace "$@" ;;
    review)
        if is_harness_review_command "$@"; then
            shift
            invoke_review "$@"
        fi
        invoke_bootstrap
        invoke_real_codex "$@"
        ;;
    low|medium|high|xhigh)
        if [ "${2:-}" = "review" ]; then
            invoke_bootstrap
            invoke_review_alias "$@"
        fi
        invoke_real_codex "$@"
        ;;
    *)
        invoke_bootstrap
        invoke_real_codex "$@"
        ;;
esac
