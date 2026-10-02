#!/bin/bash
# Run the gating suites (spec §6.14): every system/tests/*.bats except system_health.bats, then pytest.
# --health also runs system_health.bats; its result is reported but never changes the exit code.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

health=0
case "${1:-}" in
  "") ;;
  --health) health=1 ;;
  *) echo "usage: verify_setup.sh [--health]" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { echo "usage: verify_setup.sh [--health]" >&2; exit 2; }

results=() failed=0
# Each suite's exit status is read directly, never through a pipe, so a failing suite cannot report green.
gate() {  # <label> <command…>
  local label="$1" rc=0
  shift
  echo "===== $label"
  "$@" || rc=$?
  if (( rc == 0 )); then results+=("PASS $label"); else results+=("FAIL $label (exit $rc)"); failed=1; fi
}

shopt -s nullglob
suites=()
for f in system/tests/*.bats; do
  [[ "${f##*/}" == system_health.bats ]] || suites+=("$f")
done
if (( ${#suites[@]} == 0 )); then
  results+=("FAIL no gating bats suites in system/tests/")
  failed=1
fi
for f in "${suites[@]}"; do gate "$f" bats "$f"; done
gate "pytest system/tests/python" python3 -m pytest system/tests/python -q

if (( health )); then
  if [[ -f system/tests/system_health.bats ]]; then
    echo "===== system/tests/system_health.bats (advisory)"
    rc=0
    bats system/tests/system_health.bats || rc=$?
    if (( rc == 0 )); then results+=("HEALTH PASS"); else results+=("HEALTH FAIL (exit $rc; advisory)"); fi
  else
    results+=("HEALTH skipped: system/tests/system_health.bats is not present")
  fi
fi

echo "===== summary"
printf '%s\n' "${results[@]}"
exit "$failed"
