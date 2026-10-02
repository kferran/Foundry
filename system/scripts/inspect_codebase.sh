#!/bin/bash
# Stack evidence for one codebase as JSON (spec §6.13); the logic lives in vaultlib/codebase_inspect.py.
# No cd: <path> is resolved against the caller's working directory.
set -euo pipefail
exec "$(dirname "${BASH_SOURCE[0]}")/inspect_codebase.py" "$@"
