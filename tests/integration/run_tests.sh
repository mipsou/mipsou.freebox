#!/usr/bin/env bash
# Run integration tests against the real Freebox.
# Usage: ./tests/integration/run_tests.sh [target1 target2 ...]
# Default: runs all targets.

set -euo pipefail
LANG=C.UTF-8
export LANG

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CFG="$SCRIPT_DIR/integration_config.yml"

# Auto-generate config if needed
if [ ! -f "$CFG" ]; then
    echo "Config not found — run: python3 tests/integration/pair_freebox.py"
    exit 1
fi

# Targets: args or all
if [ $# -gt 0 ]; then
    TARGETS="$*"
else
    TARGETS=$(find "$SCRIPT_DIR/targets" -mindepth 1 -maxdepth 1 -type d \
        | xargs -I{} basename {} | sort | tr '\n' ' ')
fi

echo "Running targets: $TARGETS"
cd "$COL_DIR"
# shellcheck disable=SC2086
ansible-test integration --local $TARGETS
