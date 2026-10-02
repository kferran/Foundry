#!/bin/bash
# Fetch and merge template updates; never auto-resolves (spec §6.12).
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

die() { echo "update_template: $2" >&2; exit "$1"; }
(( $# == 0 )) || die 2 "usage: update_template.sh"

git remote get-url template >/dev/null 2>&1 || die 1 "no template remote; run system/scripts/setup_remote.sh first"
[[ -z "$(git status --porcelain)" ]] || die 1 "working tree is not clean; commit or stash first"

git fetch --quiet template || die 1 "git fetch template failed"
# LC_ALL=C: "HEAD branch:" is translated in other locales.
branch="$(LC_ALL=C git remote show template 2>/dev/null | sed -n 's/^ *HEAD branch: //p')"
[[ -n "$branch" && "$branch" != "(unknown)" ]] || die 1 "cannot determine the template's default branch"
ref="template/$branch"
git merge-base HEAD "$ref" >/dev/null 2>&1 \
  || die 1 "$ref shares no history with this vault (created from a GitHub template?); merge it by hand: git merge --allow-unrelated-histories $ref"

if ! git merge --no-ff --no-edit "$ref"; then
  conflicted="$(git diff --name-only --diff-filter=U)"
  [[ -n "$conflicted" ]] || die 1 "git merge $ref failed"
  echo "update_template: merge stopped on conflicts in:" >&2
  sed 's/^/  /' <<< "$conflicted" >&2
  echo "Resolve each file, then 'git add' it and 'git commit'; or run 'git merge --abort' to undo." >&2
  exit 1
fi

system/scripts/vault_index.py rebuild

# Re-render units only where this vault already installed them: an update must never install or
# enable units the user skipped (spec gate: no unit runs before Plan 4 rewrites the commands).
unit_dir="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
owned=0
for f in "$unit_dir"/*.service "$unit_dir"/*.timer; do
  if [[ -f "$f" && "$(head -n 1 -- "$f")" == "# Managed by vault: $VAULT_ROOT" ]]; then owned=1; break; fi
done
if (( owned )); then
  system/scripts/install_units.sh
else
  echo "update_template: units not installed; skipped (install them with system/scripts/install_units.sh)"
fi
