#!/bin/bash
# Focus log -> top notes and fragmentation windows (spec §6.6).
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_args.sh
source system/scripts/lib_args.sh

(( $# == 1 )) || { echo "usage: focus_stats.sh <YYYY-MM-DD>" >&2; exit 2; }
args_date "$1" || { echo "focus_stats: invalid date: $1" >&2; exit 2; }
date="$1"
log="system/logs/obsidian_focus_$date.log"

printf '# Focus: %s\n\n' "$date"
if [[ ! -s "$log" ]]; then
  echo "no focus data"
  exit 0
fi

export LC_ALL=C
# One valid sample per line: [HH:MM:SS] <note>. Anything else (a torn last line) is skipped.
samples="$(sed -nE 's/^\[([01][0-9]|2[0-3]):([0-5][0-9]):[0-5][0-9]\] (.+)$/\1 \2 \3/p' "$log")"
if [[ -z "$samples" ]]; then
  echo "no focus data"
  exit 0
fi

echo "## Top notes"
echo
echo "| Note | Samples | ≈ Minutes |"
echo "|---|---|---|"
cut -d' ' -f3- <<< "$samples" | sort | uniq -c | sed -E 's/^ *([0-9]+) /\1\t/' \
  | sort -t$'\t' -k1,1nr -k2,2 | head -n 10 \
  | awk -F'\t' '{ n = $2; gsub(/\|/, "\\|", n); printf "| %s | %d | %g |\n", n, $1, $1 / 2 }'
echo
echo "## Fragmentation"
echo
awk '
  { note = $0; sub(/^[^ ]+ [^ ]+ /, "", note)
    w = int(($1 * 60 + $2) / 15)
    if (NR > 1 && note != prev) sw[w]++
    prev = note }
  END {
    found = 0
    for (w = 0; w < 96; w++) if (sw[w] > 4) {
      s = w * 15; e = s + 15
      printf "- **Focus Fragmentation Warning** %02d:%02d–%02d:%02d: %d switches\n", int(s / 60), s % 60, int(e / 60) % 24, e % 60, sw[w]
      found = 1 }
    if (!found) print "No fragmentation windows." }' <<< "$samples"
