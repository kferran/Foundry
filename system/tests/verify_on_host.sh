#!/bin/bash
# Run the gate natively on another machine over ssh (two-machine spec §6). Copies HEAD, never the
# working tree, into a new directory under the host's /tmp; installs nothing there.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$REPO"

die() { echo "verify_on_host: $2" >&2; exit "$1"; }
(( $# == 1 )) || die 2 "usage: verify_on_host.sh <ssh-host>"
host="$1"
[[ "$host" =~ ^[A-Za-z0-9._@-]+$ && "$host" != -* ]] || die 2 "not a plain ssh host name: $host"

dir="${VERIFY_TMP:-/tmp}/foundry-verify-$(date +%Y%m%dT%H%M%S)-$$"
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=15)

git archive --format=tar HEAD \
  | ssh "${ssh_opts[@]}" "$host" "mkdir -- '$dir' && tar -x -C '$dir' && cd '$dir' && git init -q && git add -A && git -c user.name=verify -c user.email=verify@localhost commit -qm verify" \
  || die 1 "could not copy HEAD to $host:$dir"

set +e
ssh "${ssh_opts[@]}" "$host" "cd '$dir' && system/scripts/verify_setup.sh > '$dir.log' 2>&1; rc=\$?; sed -n '/===== summary/,\$p' '$dir.log'; if [ \$rc -eq 0 ]; then rm -rf -- '$dir' '$dir.log'; else echo 'kept: $host:$dir and $dir.log'; fi; exit \$rc"
rc=$?
set -e
exit "$rc"
