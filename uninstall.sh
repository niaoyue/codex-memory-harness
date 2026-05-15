#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
exec sh "$SCRIPT_DIR/install.sh" --uninstall "$@"
