#!/bin/bash
# Fixture check of one item: an item named in system/logs/items.bad fails with its reason there; any other is ok.
reason="$(awk -F'\t' -v i="$1" '$1 == i { print $2 }' system/logs/items.bad 2>/dev/null)"
if [[ -n "$reason" ]]; then
  echo "items_check: $1: $reason"
  exit 1
fi
echo "items_check: $1: ok"
