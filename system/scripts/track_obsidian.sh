#!/bin/bash
LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../logs" && pwd)"
mkdir -p "$LOG_DIR"

while true; do
  CURRENT_DATE=$(date +%Y-%m-%d)
  TIMESTAMP=$(date +%H:%M:%S)
  WINDOW_TITLE=""

  if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    if command -v hyprctl &> /dev/null; then
      WINDOW_TITLE=$(hyprctl activewindow -j | jq -r '.title // empty')
    elif command -v swaymsg &> /dev/null; then
      WINDOW_TITLE=$(swaymsg -t get_tree | jq -r '.. | select(.focused? == true) | .name // empty')
    fi
  fi

  # Obsidian titles look like "Note Name - Vault Name - Obsidian v1.x.x"
  if [[ "$WINDOW_TITLE" == *"Obsidian"* ]]; then
    NOTE_NAME=$(echo "$WINDOW_TITLE" | awk -F ' - ' '{print $1}')
    echo "[$TIMESTAMP] $NOTE_NAME" >> "$LOG_DIR/obsidian_focus_$CURRENT_DATE.log"
  fi

  sleep 30
done
