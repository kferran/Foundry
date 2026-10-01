#!/bin/bash
# Deterministic vault linter: schema errors fail, dead links warn (spec §6.8).
set -euo pipefail
VAULT_ROOT="${VAULT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$VAULT_ROOT"
args=()
if [[ "${1:-}" == "--staged" ]]; then
  args+=(--staged)
fi
exec system/scripts/vault_index.py issues "${args[@]}"
