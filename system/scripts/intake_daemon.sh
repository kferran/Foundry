#!/bin/bash
VAULT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$VAULT_PATH" || exit 1

CURRENT_DAILY="briefings/$(date +%Y-%m-%d).md"

# Pull any #wiki-ingest-start ... #wiki-ingest-end block out of today's briefing into raw/
if [ -f "$CURRENT_DAILY" ]; then
  AWK_EXTRACT=$(awk '/#wiki-ingest-start/,/#wiki-ingest-end/ {if ($0 !~ /#wiki-ingest/) print}' "$CURRENT_DAILY")
  if [ -n "$AWK_EXTRACT" ]; then
    TMP_DROP="raw/daily_note_drop_$(date +%s).md"
    echo "$AWK_EXTRACT" > "$TMP_DROP"
    sed -i '/#wiki-ingest-start/,/#wiki-ingest-end/ d' "$CURRENT_DAILY"
  fi
fi

mkdir -p raw/archive system/quarantine system/logs

for file in raw/*; do
  [ -f "$file" ] || continue
  FILENAME=$(basename "$file")
  LOG_FILE="system/logs/intake_$(date +%Y-%m-%d).log"

  # -p = headless (print) mode; -c would try to resume an interactive session
  if claude -p "/ingest $file" >> "$LOG_FILE" 2>&1; then
    mv "$file" raw/archive/
  else
    mv "$file" "system/quarantine/$FILENAME"
    echo "- [ ] CRITICAL FAULT: Raw file \`$FILENAME\` failed compilation." >> "briefings/$(date +%Y-%m-%d).md" 2>/dev/null
  fi
done
