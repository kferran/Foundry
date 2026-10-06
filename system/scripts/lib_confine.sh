# shellcheck shell=bash
# Confinement for a connector fetch session (calendar spec §4; meetings spec §2.1). Source from VAULT_ROOT.
# The session must load user settings (connectors need them), so it is confined by dontAsk with one allowed
# tool, a deny list built from every allow rule the user's settings hold, and hooks off; the caller then
# checks the session's tool use.

CONFINE_BUILTIN_DENY=(Bash PowerShell Monitor Read Write Edit NotebookEdit Glob Grep WebFetch WebSearch Skill Agent
  Task Workflow SendMessage SendUserFile PushNotification Artifact ArtifactData ArtifactComments CronCreate
  CronDelete RemoteTrigger EnterWorktree ExitWorktree ListMcpResourcesTool ReadMcpResourceTool)

# confine_deny [--strict] <server prefix> <allowed tool> <other tool on that server…>: set CONFINE_DENY to the
# built-in tools, the server's other tools and every tool an allow rule names, except rules that would match the
# allowed tool. Returns 1 with CONFINE_ERROR set when a settings file does not parse or a rule is too broad;
# with --strict, also when a rule allows the whole server (its other tools could not be kept out by the rule).
confine_deny() {
  local strict=0 prefix tool config_dir f rules rule name
  local -a files
  if [[ "${1:-}" == --strict ]]; then strict=1; shift; fi
  prefix="$1" tool="$2"
  shift 2
  CONFINE_DENY=("${CONFINE_BUILTIN_DENY[@]}" "$@") CONFINE_ERROR=""
  config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  files=("$config_dir/settings.json" "$config_dir/settings.local.json" "${FOUNDRY_MANAGED_SETTINGS:-/etc/claude-code/managed-settings.json}")
  for f in "${FOUNDRY_MANAGED_SETTINGS_DIR:-/etc/claude-code/managed-settings.d}"/*.json; do files+=("$f"); done
  for f in "${files[@]}"; do
    [[ -e "$f" ]] || continue
    if ! rules="$(jq -er 'if type == "object" then (.permissions.allow // [])[] | strings else error("not an object") end' "$f" 2>/dev/null)"; then
      if [[ "$(jq -r 'type' "$f" 2>/dev/null)" != object ]]; then
        CONFINE_ERROR="cannot parse $f; fix it first (claude was not run)"
        return 1
      fi
      rules=""
    fi
    while IFS= read -r rule; do
      [[ -n "$rule" ]] || continue
      name="${rule%%(*}"
      # shellcheck disable=SC2053  # the rule is a glob on purpose
      if [[ "$name" == "$prefix" || "$tool" == $name ]]; then
        # A glob that also reaches other servers can't be denied without denying the allowed tool: fail closed.
        if [[ "$name" != "$prefix" && "$name" != "${prefix}__"* ]]; then
          CONFINE_ERROR="allow rule '$rule' in $f also allows other servers' tools; narrow it (claude was not run)"
          return 1
        fi
        if (( strict )) && [[ "$name" != "$tool" ]]; then
          CONFINE_ERROR="allow rule '$rule' in $f allows every tool on $prefix; allow single tools instead (claude was not run)"
          return 1
        fi
        continue
      fi
      CONFINE_DENY+=("$name")
    done <<< "$rules"
  done
}

# confine_settings <server name to keep> <working directory>: set CONFINE_SETTINGS to hooks off and every other
# listed server denied by name. This only lowers cost; the deny list and the tool-use check are the boundary.
confine_settings() {
  local servers denied
  servers="$(cd "$2" && timeout -k 5 30 "${CLAUDE_BIN:-claude}" mcp list 2>/dev/null)" || servers=""
  denied="$(awk -v keep="$1" '/: / && / - / { n = index($0, ": "); name = substr($0, 1, n - 1); if (name != keep) print name }' <<< "$servers" \
    | jq -Rcs 'split("\n") | map(select(length > 0)) | map({serverName: .})')"
  CONFINE_SETTINGS="$(jq -cn --argjson d "$denied" '{disableAllHooks: true, deniedMcpServers: $d}')"
}
