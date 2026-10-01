#!/bin/bash
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
echo "🚀 Invoking BATS Test Architecture Suite..."
bats system/tests/vault_integrity.bats
