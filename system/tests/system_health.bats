#!/usr/bin/env bats
# Live service and machine state (spec §12). Advisory: verify_setup.sh runs it only with --health and
# never gates on it, and /backup reports its failures as warnings. It reads this vault, not a fixture.

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd -P)"
  cd "$VAULT_ROOT"
}

field() { system/scripts/vault_index.py field system/config.md "$1"; }

# skip_unless_role <role…>: skip this check on a machine whose role is not listed.
skip_unless_role() {
  local role
  role="$(field machine_role 2>/dev/null || true)"
  role="${role:-standalone}"
  [[ " $* " == *" $role "* ]] || skip "not used on a $role machine"
}

@test "claude version is unchanged since the last health check (else re-run spike item 12)" {
  mkdir -p system/logs
  current="$(claude --version 2>/dev/null || echo unknown)"
  recorded="$(cat system/logs/claude_version 2>/dev/null || true)"
  printf '%s\n' "$current" > system/logs/claude_version
  if [[ -n "$recorded" && "$recorded" != "$current" ]]; then
    echo "claude changed from '$recorded' to '$current': re-run spike item 12 (session eligibility env vars)"
    false
  fi
}

@test "headless sandbox never auto-allows Bash" {
  [ "$(jq '.sandbox.autoAllowBashIfSandboxed' system/headless.settings.json)" = "false" ]
}

@test "system/config.md exists and validates" {
  [ -f system/config.md ]
  system/scripts/vault_index.py validate system/config.md
}

@test "the intake, brief and debrief timers are active" {
  skip_unless_role standalone server
  for t in jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer; do
    systemctl --user is-active --quiet "$t"
  done
}

@test "the sync timer is active" {
  skip_unless_role server
  systemctl --user is-active --quiet jarvis-sync.timer
}

@test "no sync conflict is blocking the runs" {
  skip_unless_role server
  if [[ -e system/logs/sync-blocked ]]; then
    cat system/logs/sync-blocked
    false
  fi
}

@test "the focus tracker is active" {
  skip_unless_role standalone
  systemctl --user is-active --quiet jarvis-focus.service
}

@test "lingering is enabled, so timers run while logged out" {
  skip_unless_role standalone server
  [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" = yes ]
}

@test "git hooks path is .githooks" {
  [ "$(git config --get core.hooksPath)" = .githooks ]
}

@test "remotes match remote_mode" {
  source system/scripts/lib_git.sh
  mode="$(field remote_mode)"
  template="$(head -n 1 system/template_source)"
  origin="$(git remote get-url origin 2>/dev/null || true)"
  case "$mode" in
    private)
      [ -n "$origin" ]
      run git_url_same "$origin" "$template"
      [ "$status" -ne 0 ]
      ;;
    none|keep) ;;
    *) echo "unknown remote_mode: $mode"; false ;;
  esac
}

@test "every required dependency is present" {
  system/scripts/check_deps.sh --strict
}

@test "the index builds with no errors" {
  system/scripts/lint_vault.sh
}
