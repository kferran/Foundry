#!/bin/bash
# Deterministic vault linter: schema errors fail, dead links warn (spec §6.8).
set -euo pipefail
VAULT_ROOT="${VAULT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$VAULT_ROOT"
args=()
if [[ "${1:-}" == "--staged" ]]; then
  args+=(--staged)
fi
# A client never syncs raw/inbox/ (gitignored; two-machine spec §5.7), so files there would be lost to the server.
if [[ -d raw/inbox && "$(system/scripts/vault_index.py field system/config.md machine_role 2>/dev/null)" == client ]]; then
  n="$(find raw/inbox -maxdepth 1 -type f ! -name '.*' 2>/dev/null | wc -l)"
  (( n == 0 )) || echo "warning: raw/inbox/ holds $n file(s); a client does not sync them, so write notes in the briefing"
fi
# Secret shapes in tracked and untracked files, as a report (secret-shape lint spec §2, #166): findings leave the exit
# status alone, an unscanned tree exits 2. With --staged the pre-commit hook has already scanned the staged blobs.
if (( ${#args[@]} == 0 )); then
  rc=0
  python3 system/scripts/secret_scan.py || rc=$?
  (( rc < 2 )) || exit 2
fi
exec system/scripts/vault_index.py issues "${args[@]}"
