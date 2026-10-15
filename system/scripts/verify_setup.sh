#!/bin/bash
# Run the gate (spec §6.14): lint_vault.sh, then every system/tests/*.bats except system_health.bats and
# pytest when bats and pytest are installed (side by side with GNU parallel and pytest-xdist). --require-suites fails when they are not (verify_on_host.sh, so a
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
record() {  # <label> <exit status>
  if [[ "$2" == 0 ]]; then results+=("PASS $1"); else results+=("FAIL $1 (exit $2)"); failed=1; fi
}
gate() {  # <label> <command…>
  local label="$1" rc=0
  shift
  echo "===== $label"
  "$@" || rc=$?
  record "$label" "$rc"
}

gate lint system/scripts/lint_vault.sh

# bats and pytest are development tools (express install spec §2): without them a vault is linted only,
# and the summary says so on every run.
have_bats=0
command -v bats >/dev/null 2>&1 && have_bats=1
if (( have_bats )) && python3 -m pytest --version >/dev/null 2>&1; then
  # Suites copy system/scripts into their fixture vaults while other suites run Python from it. Bytecode
  # written into the tree (a __pycache__ temp file renamed into place) can vanish mid-copy and fail the
  # copy, so every suite and pytest write their bytecode to one throwaway directory outside the tree.
  PYTHONPYCACHEPREFIX="$(mktemp -d)"
  export PYTHONPYCACHEPREFIX
  trap 'rm -rf "$PYTHONPYCACHEPREFIX"' EXIT
  shopt -s nullglob
  suites=()
  for f in system/tests/*.bats; do
    [[ "${f##*/}" == system_health.bats ]] || suites+=("$f")
  done
  if (( ${#suites[@]} == 0 )); then
    results+=("FAIL no gating bats suites in system/tests/")
    failed=1
  fi
  # With GNU parallel (moreutils ships another program of that name) the suites run side by side, one bats
  # process each. Every suite writes its own log and its exit status to its own file; a suite with no status
  # file fails. The largest files start first, so a long suite does not start last. Without GNU parallel
  # they run one after another.
  if (( ${#suites[@]} )) && [[ "$(parallel --version 2>/dev/null || true)" == "GNU parallel"* ]]; then
    GATE_LOGS="$(mktemp -d)"
    export GATE_LOGS
    ls -S -- "${suites[@]}" | parallel --will-cite --jobs "$(nproc)" \
      'bats {} > "$GATE_LOGS/{/}.log" 2>&1; echo $? > "$GATE_LOGS/{/}.rc"' || true
    for f in "${suites[@]}"; do
      echo "===== $f"
      cat "$GATE_LOGS/${f##*/}.log" 2>/dev/null || true
      record "$f" "$(cat "$GATE_LOGS/${f##*/}.rc" 2>/dev/null || echo 'no status')"
    done
    rm -rf "$GATE_LOGS"
  else
    for f in "${suites[@]}"; do gate "$f" bats "$f"; done
  fi
  # pytest-xdist, when installed, spreads the tests over every core.
  xdist=()
  if python3 -c 'import xdist' >/dev/null 2>&1; then xdist=(-n auto); fi
  gate "pytest system/tests/python" python3 -m pytest system/tests/python -q "${xdist[@]}"
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
