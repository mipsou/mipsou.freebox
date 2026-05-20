#!/usr/bin/env bash
# Run integration tests against the real Freebox.
# Usage: ./tests/integration/run_tests.sh [target1 target2 ...]
# Default: runs all cloud/freebox targets.

set -euo pipefail
LANG=C.UTF-8
export LANG

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VPF="$SCRIPT_DIR/get_vault_password.py"
VAULT="$SCRIPT_DIR/integration_config.yml.vault"
# ansible-test auto-loads tests/integration/integration_config.yml
CFG="$SCRIPT_DIR/integration_config.yml"

# Auto-generate vault if needed
if [ ! -f "$VAULT" ]; then
    echo "Vault not found — running setup..."
    python3 "$SCRIPT_DIR/setup_integration.py"
fi

# Decrypt to integration_config.yml (gitignored), cleanup on exit
ansible-vault decrypt \
    --vault-password-file "$VPF" \
    --output "$CFG" \
    "$VAULT"
trap 'rm -f "$CFG"' EXIT

# Targets: args or all cloud/freebox
if [ $# -gt 0 ]; then
    TARGETS="$*"
else
    TARGETS=$(find "$SCRIPT_DIR/targets" -name aliases -exec grep -l 'cloud/freebox' {} \; \
        | xargs -I{} dirname {} | xargs -I{} basename {} | sort | tr '\n' ' ')
fi

echo "Running targets: $TARGETS"

cd "$COL_DIR"
# shellcheck disable=SC2086
ansible-test integration --local $TARGETS
