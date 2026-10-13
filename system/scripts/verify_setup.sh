#!/bin/bash
# Run the gate (spec §6.14): lint_vault.sh, then every system/tests/*.bats except system_health.bats and
# pytest when bats and pytest are installed. --require-suites fails when they are not (verify_on_host.sh, so a
# host proof always runs the suites). --health also runs system_health.bats; its result is reported but never
# changes the exit code.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

health=0 require_suites=0
for a in "$@"; do
  case "$a" in
    --health) health=1 ;;
    --require-suites) require_suites=1 ;;
    *) echo "usage: verify_setup.sh [--health] [--require-suites]" >&2; exit 2 ;;
  esac
done

# Suites' temp files go in the vault's ignored .scratch/ (Claude Code's working directory), not /tmp.
# The ceiling keeps git in a temp dir from finding this vault's repository, as it would not under /tmp.
export TMPDIR="$VAULT_ROOT/.scratch/tmp" GIT_CEILING_DIRECTORIES="$VAULT_ROOT/.scratch"
mkdir -p "$TMPDIR"

results=() failed=0
# Each suite's exit status is read directly, never through a pipe, so a failing suite cannot report green.
gate() {  # <label> <command…>
  local label="$1" rc=0
  shift
  echo "===== $label"
  "$@" || rc=$?
  if (( rc == 0 )); then results+=("PASS $label"); else results+=("FAIL $label (exit $rc)"); failed=1; fi
}

gate lint system/scripts/lint_vault.sh

# bats and pytest are development tools (express install spec §2): without them a vault is linted only,
# and the summary says so on every run.
have_bats=0
command -v bats >/dev/null 2>&1 && have_bats=1
if (( have_bats )) && python3 -m pytest --version >/dev/null 2>&1; then
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
elif (( require_suites )); then
  results+=("FAIL suites: bats or pytest is not installed (development tools)")
  failed=1
else
  results+=("SKIP suites: bats or pytest is not installed (development tools)")
fi

if (( health )); then
  if (( ! have_bats )); then
    results+=("HEALTH skipped: bats is not installed")
  elif [[ -f system/tests/system_health.bats ]]; then
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
