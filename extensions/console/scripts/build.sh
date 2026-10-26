#!/bin/bash
# Build the console outside the vault (console C1 spec §5, §8.1): copy extensions/console/app/ to
# <console_build_dir>/src without node_modules or a build, then mise install, npm ci and nuxi build there. Obsidian,
# Obsidian Git, the index and the secret scan never see node_modules.
# Usage: build.sh. Exit: 0 built; 1 a step failed (named on stderr); 2 a bad console_build_dir.
set -uo pipefail  # no -e: each step's failure is named where it happens
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
cd "$VAULT_ROOT" || exit 1
# shellcheck source=../../../system/scripts/lib_config.sh
source system/scripts/lib_config.sh

(( $# == 0 )) || { echo "usage: build.sh" >&2; exit 2; }
dir="$(config_get console_build_dir "$HOME/.cache/foundry-console")"
[[ "$dir" == /* ]] || { echo "build.sh: console_build_dir must be an absolute path: $dir" >&2; exit 2; }
case "$dir/" in
  "$VAULT_ROOT"/*) echo "build.sh: console_build_dir must be outside the vault: $dir" >&2; exit 2 ;;
esac
if ! mkdir -p -- "$dir/src" 2>/dev/null || [[ ! -w "$dir/src" ]]; then
  echo "build.sh: console_build_dir is not writable: $dir" >&2
  exit 2
fi

step() {  # step <name> <command…>: run it in the source copy; a failure ends the build with its name
  local name="$1"
  shift
  if ! (cd "$dir/src" && "$@"); then
    echo "build.sh: $name failed" >&2
    exit 1
  fi
}
step copy rsync -a --delete --exclude node_modules --exclude .nuxt --exclude .output "$VAULT_ROOT/extensions/console/app/" "$dir/src/"
step "mise install" mise install
step "npm ci" mise exec -- npm ci
step "nuxi build" mise exec -- npx nuxi build
echo "built $dir/src/.output"
