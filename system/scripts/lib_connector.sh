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
  for t in "${CONNECTOR_OTHERS[@]}"; do others+=("${CONNECTOR_PREFIX}__$t"); done
  # The allow rules first: a refused rule stops before the up-to-30 s server listing.
  if ! confine_deny --strict "$CONNECTOR_PREFIX" "$CONNECTOR_TOOL" "${others[@]}"; then
    CONNECTOR_REASON="$CONFINE_ERROR"
    return 1
  fi
  [[ -n "${CONFINE_SETTINGS:-}" ]] || confine_settings "$CONNECTOR_SERVER" "$work"
  [[ -z "${CONNECTOR_SCHEMA:-}" ]] || schema=(--json-schema "$(cat "$CONNECTOR_SCHEMA")")
  # A fresh working directory per session, under the caller's work directory so its trap removes the directory of a
  # session a stopped unit leaves behind (#40). The prompt comes first: --allowedTools and --disallowedTools take
  # variable-length lists and stay last.
  if ! sdir="$(mktemp -d -p "$work" session.XXXXXX 2>/dev/null)"; then
    CONNECTOR_REASON="cannot create a session directory under $work (claude was not run)"
    return 1
  fi
  (cd "$sdir" &&FOUNDRY_HEADLESS=1 timeout -k 10 "$CONNECTOR_TIMEOUT" "$claude_bin" -p "$prompt" \
    --settings "$CONFINE_SETTINGS" --disable-slash-commands --no-session-persistence --permission-mode dontAsk \
    --output-format stream-json --verbose "${schema[@]}" --max-turns "$CONNECTOR_TURNS" --max-budget-usd 1 \
    --allowedTools "$CONNECTOR_TOOL" --disallowedTools "${CONFINE_DENY[@]}" \
    < /dev/null > "$work/out.jsonl" 2> "$work/claude.err") || CONNECTOR_RC=$?
  rm -rf -- "$sdir"
  return 0
}

# connector_outcome <checker exit> <work dir>: set CONNECTOR_EXIT and CONNECTOR_REASON from the checker's verdict and
# the session's exit. The checker's verdict wins: 0 is success whatever claude's exit (the checker saw the whole result,
# or the post or ticket it confirms exists), and 7 (an unexpected tool) stands. Another failure after a timed-out session
# is 4; after any other failed session it keeps the checker's code and names claude's exit and stderr, so a refused flag
# does not read as a missing connector. The checker's stderr is <work dir>/check.err, its first line prefixed "<name>: ".
connector_outcome() {
  local prc="$1" work="$2"
  # sed quits after the first line itself: a `| head -n 1` would take SIGPIPE on a long traceback and, under the
  # callers' pipefail, kill the script with no log line or alert.
  CONNECTOR_EXIT="$prc" CONNECTOR_REASON="$(sed -En '1{s/^[a-z_]+: //;p;q}' "$work/check.err" 2>/dev/null)"
  (( prc != 0 && prc != 7 )) || return 0
  if (( CONNECTOR_RC == 124 || CONNECTOR_RC == 137 )); then
    CONNECTOR_EXIT=4 CONNECTOR_REASON="timed out after ${CONNECTOR_TIMEOUT}s"
  elif (( CONNECTOR_RC != 0 )); then
    CONNECTOR_REASON="$CONNECTOR_REASON; claude exited $CONNECTOR_RC: $(head -c 200 "$work/claude.err" 2>/dev/null)"
  fi
}

# connector_classify <exit> <reason> [work dir]: set CONNECTOR_CLASS to the failure's class (connector health spec §2):
# auth (no connector reachable, or the connector refused the credential: renew it), timeout, claude (no claude, or it
# is logged out or out of credit), connector (the connector failed otherwise), other, or "" on success. Callers print
# "<name>: <class>: <reason>" so the smoke check and the brief can name the credential to renew.
connector_classify() {
  local rc="$1" reason="$2" work="${3:-}" err=""
  [[ -z "$work" ]] || err="$(head -c 2000 "$work/claude.err" 2>/dev/null || true)"
  shopt -s nocasematch
  case "$rc" in
    0|2) CONNECTOR_CLASS="" ;;   # 2 is a usage or settings error: the reason already says what to change
    3) CONNECTOR_CLASS=auth ;;
    4) if [[ "$reason" == *"timed out"* ]]; then CONNECTOR_CLASS=timeout; else CONNECTOR_CLASS=other; fi ;;   # 4 is also a busy lock
    6) if [[ "$reason" =~ (401|403|unauthori[sz]ed|forbidden|expired|reconnect|invalid_grant|token) ]]; then
         CONNECTOR_CLASS=auth
       else
         CONNECTOR_CLASS=connector
       fi ;;
    127) CONNECTOR_CLASS=claude ;;
    *) if [[ "$reason $err" =~ (/login|invalid\ api\ key|not\ logged\ in|credit\ balance) ]]; then
         CONNECTOR_CLASS=claude
       else
         CONNECTOR_CLASS=other
       fi ;;
  esac
  shopt -u nocasematch
}
