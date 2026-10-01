#!/bin/bash
# Wheeljack intake daemon entry point (spec §6.4); the logic lives in vaultlib/intake.py.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
exec system/scripts/intake.py "$@"
