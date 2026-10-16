#!/bin/bash
# Fixture list: the lines of system/logs/items.list ("item<tab>credential<tab>renewal"), from the vault root; with
# system/logs/items.fail present it fails, as a list that cannot run.
if [[ -e system/logs/items.fail ]]; then
  echo "items_list: other: the list broke" >&2
  exit 1
fi
cat system/logs/items.list 2>/dev/null || true
