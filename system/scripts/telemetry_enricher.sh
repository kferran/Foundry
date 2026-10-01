#!/bin/bash
# Context-Driven Telemetry Ingestion Engine for Ultron Production Errors
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ULTRON_REPO="${ULTRON_REPO:-$HOME/code/worktrees/main}"
RAW_DIR="$VAULT_ROOT/raw"
mkdir -p "$RAW_DIR"

# Simulation of incoming Kusto telemetry row data (swap for a real Kusto query later)
MOCK_EXCEPTION="System.NullReferenceException"
MOCK_MSG="Object reference not set to an instance of an object at Ultron.Core.Services.WithdrawalParsingService.MapDelta"
MOCK_OP_ID="ERR-$(date +%s)"
TARGET_FILE="$RAW_DIR/kusto_enriched_${MOCK_OP_ID}.md"

echo "🔍 Enriching incoming error telemetry string against code repository history..."

# Extract the class name from the stack frame footprint:
# "at Namespace.Class.Method" -> "Class" (second-to-last dotted segment)
FRAME=$(echo "$MOCK_MSG" | grep -oE 'at [A-Za-z0-9_.]+' | head -n 1 | cut -d' ' -f2)
TARGET_CLASS=$(echo "$FRAME" | awk -F. 'NF>=2 {print $(NF-1)}')

FILE_PATH="Unknown (class matching footprint not found in active workspace branches)"
LAST_COMMIT="N/A"
AUTHOR="Unknown"
COMMIT_DATE="N/A"
COMMIT_MSG="N/A"

if [ -n "$TARGET_CLASS" ] && git -C "$ULTRON_REPO" rev-parse --git-dir >/dev/null 2>&1; then
  # git ls-files is fast and skips node_modules/bin/obj automatically
  FOUND=$(git -C "$ULTRON_REPO" ls-files -- "*${TARGET_CLASS}.cs" | head -n 1)
  if [ -n "$FOUND" ]; then
    FILE_PATH="$FOUND"
    # Last commit that touched the whole file (a stronger signal than blaming lines 1-10)
    LAST_COMMIT=$(git -C "$ULTRON_REPO" log -1 --format="%h" -- "$FOUND")
    AUTHOR=$(git -C "$ULTRON_REPO" log -1 --format="%an" -- "$FOUND")
    COMMIT_DATE=$(git -C "$ULTRON_REPO" log -1 --format="%ad" --date=short -- "$FOUND")
    COMMIT_MSG=$(git -C "$ULTRON_REPO" log -1 --format="%s" -- "$FOUND")
  fi
else
  FILE_PATH="Repository path unreachable during background compilation pass"
fi

cat << TELEMETRY > "$TARGET_FILE"
---
type: production_error
service: UltronWebApi
exception: ${MOCK_EXCEPTION}
operation_id: ${MOCK_OP_ID}
detected_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
is_friction: true
assigned_agent: SystemMaintenance
---

# 🚨 Enriched Production Exception: ${MOCK_EXCEPTION}

## Telemetry Context
- Service Source: \`UltronWebApi\`
- Operation ID: \`${MOCK_OP_ID}\`

## 🧠 Codebase Attribution Layer
- Suspect Target File: \`${FILE_PATH}\`
- Last Commit Touching File: \`${LAST_COMMIT}\`
- Last Modifying Developer: \`${AUTHOR}\` (${COMMIT_DATE})
- Commit Message Footprint: "${COMMIT_MSG}"

## Exception Message
\`\`\`text
${MOCK_MSG}
\`\`\`
TELEMETRY

echo "✅ Telemetry context node synthesized at $TARGET_FILE"
