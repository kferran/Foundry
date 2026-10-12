#!/bin/bash
# Run one bats suite or one pytest target with the gate's environment (spec §6.14; FOUNDRY.md Development).
# Usage: test.sh <suite.bats | pytest path> [args…]. The gate itself is verify_setup.sh.
# One command with no leading assignment, so a single allow rule covers every per-task test run.
# Exit: the runner's exit code; 2 usage; 127 when the runner is not installed.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

(( $# >= 1 )) || { echo "usage: test.sh <suite.bats | pytest path> [args…]" >&2; exit 2; }
target="$1"
shift

# The same environment as verify_setup.sh: temp files under the ignored .scratch/, and a git ceiling so a
# repository created in a temp dir never finds this one.
export TMPDIR="$VAULT_ROOT/.scratch/tmp" GIT_CEILING_DIRECTORIES="$VAULT_ROOT/.scratch"
mkdir -p "$TMPDIR"

case "$target" in
  *.bats)
    command -v bats > /dev/null 2>&1 || { echo "test.sh: bats is not installed" >&2; exit 127; }
    exec bats "$target" "$@" ;;
  *.py|*/python|*/python/*)
    exec python3 -m pytest -q "$target" "$@" ;;
  *)
    echo "test.sh: $target is neither a .bats suite nor a pytest path" >&2
    exit 2 ;;
esac
