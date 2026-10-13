# shellcheck shell=bash
# One confined connector session (connector runner spec §2). Source from VAULT_ROOT after lib_confine.sh.
# Every `claude` flag a connector session gets is in this file. Set before calling:
#   CONNECTOR_SERVER   the connector's name in `claude mcp list`; the other listed servers are denied by name
#   CONNECTOR_PREFIX   the server's tool prefix, e.g. mcp__claude_ai_Gmail
#   CONNECTOR_TOOL     the one allowed tool
#   CONNECTOR_OTHERS   the server's other tools, bare names (an array)
#   CONNECTOR_TIMEOUT  seconds for the session
#   CONNECTOR_TURNS    --max-turns
#   CONNECTOR_SCHEMA   optional: a file whose JSON schema the reply must match (--json-schema)

# connector_run <prompt> <work dir>: run one session in a fresh directory under <work dir>, leaving <work dir>/out.jsonl
# and <work dir>/claude.err. Returns 127 (no claude) or 1 (a refused allow rule) with CONNECTOR_REASON set and nothing
# run; otherwise returns 0 with CONNECTOR_RC the session's exit (124 or 137 after the timeout). The server list is
# read once per process: a caller running several sessions pays for `claude mcp list` once.
connector_run() {
  local prompt="$1" work="$2" claude_bin="${CLAUDE_BIN:-claude}" sdir t
  local -a others=() schema=()
  CONNECTOR_REASON="" CONNECTOR_RC=0
  if ! command -v "$claude_bin" > /dev/null 2>&1; then
    CONNECTOR_REASON="claude not found ($claude_bin)"
    return 127
  fi
  [[ -n "${CONFINE_SETTINGS:-}" ]] || confine_settings "$CONNECTOR_SERVER" "$work"
  for t in "${CONNECTOR_OTHERS[@]}"; do others+=("${CONNECTOR_PREFIX}__$t"); done
  if ! confine_deny --strict "$CONNECTOR_PREFIX" "$CONNECTOR_TOOL" "${others[@]}"; then
    CONNECTOR_REASON="$CONFINE_ERROR"
    return 1
  fi
  [[ -z "${CONNECTOR_SCHEMA:-}" ]] || schema=(--json-schema "$(cat "$CONNECTOR_SCHEMA")")
  # A fresh working directory per session, under the caller's work directory so its trap removes the directory of a
  # session a stopped unit leaves behind (#40). The prompt comes first: --allowedTools and --disallowedTools take
  # variable-length lists and stay last.
  sdir="$(mktemp -d -p "$work" session.XXXXXX)"
  (cd "$sdir" && FOUNDRY_HEADLESS=1 timeout -k 10 "$CONNECTOR_TIMEOUT" "$claude_bin" -p "$prompt" \
    --settings "$CONFINE_SETTINGS" --disable-slash-commands --no-session-persistence --permission-mode dontAsk \
    --output-format stream-json --verbose "${schema[@]}" --max-turns "$CONNECTOR_TURNS" --max-budget-usd 1 \
    --allowedTools "$CONNECTOR_TOOL" --disallowedTools "${CONFINE_DENY[@]}" \
    < /dev/null > "$work/out.jsonl" 2> "$work/claude.err") || CONNECTOR_RC=$?
  rm -rf -- "$sdir"
  return 0
}
