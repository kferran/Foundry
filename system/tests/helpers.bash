# Shared setup for shell suites. Usage: load helpers; make_vault
# An extension's suite loads this file from extensions/<name>/tests/ (extensions spec §3), so the repository root is
# found from this file's own folder, never from the test's.
FOUNDRY_TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# need_env <reason> <command…>: a test that needs what a container or a root runner lacks skips with
# "environment: <reason>" when the command fails; under the gate's --require-suites (FOUNDRY_REQUIRE_ENV=1, as
# CI and verify_on_host run it) it fails instead, so a missing environment never passes there (audit C16).
need_env() {
  "${@:2}" >/dev/null 2>&1 && return 0
  if [[ "${FOUNDRY_REQUIRE_ENV:-}" == 1 ]]; then echo "environment required: $1" >&2; return 1; fi
  skip "environment: $1"
}
user_systemd() {  # systemd-analyze can verify a user unit (needs a user systemd instance)
  local d
  d="$(mktemp -d)"
  printf '[Unit]\nDescription=probe\n[Service]\nType=oneshot\nExecStart=/bin/true\n' > "$d/foundry-probe.service"
  systemd-analyze --user verify "$d/foundry-probe.service"
  local rc=$?
  rm -rf "$d"
  return "$rc"
}
need_user_systemd() { need_env "no user systemd instance" user_systemd; }
need_non_root() { need_env "root ignores file modes" test "$(id -u)" -ne 0; }
make_vault() {
  REPO="$(cd "$FOUNDRY_TESTS_DIR/../.." && pwd)"
  V="$BATS_TEST_TMPDIR/vault"
  unset VAULT_ROOT
  cp -r "$REPO/system/tests/fixtures/vault" "$V"
  mkdir -p "$V/system" "$V/.claude"
  cp -r "$REPO/system/schemas" "$V/system/schemas"
  cp -r "$REPO/system/templates" "$V/system/templates"
  mkdir -p "$V/system/scripts"
  cp -r "$REPO/system/scripts/." "$V/system/scripts/"
  rm -rf "$V/system/scripts/__pycache__" "$V/system/scripts/vaultlib/__pycache__"
  cp "$REPO/CLAUDE.md" "$V/CLAUDE.md"
  cp -r "$REPO/.claude/commands" "$V/.claude/commands"
  [[ -f "$REPO/system/headless.settings.json" ]] && cp "$REPO/system/headless.settings.json" "$V/system/"
  [[ -f "$REPO/.claude/settings.json" ]] && cp "$REPO/.claude/settings.json" "$V/.claude/"
  cat > "$V/system/config.md" <<EOF
---
type: config
timezone: "America/Denver"
brief_time: "06:00"
debrief_time: "17:00"
remote_mode: "none"
default_partition: "personal"
order_workspace: "$BATS_TEST_TMPDIR/ws"
---
EOF
  git -C "$V" init -q
  git -C "$V" config user.email test@example.com
  git -C "$V" config user.name test
}

# use_extension <name…>: turn extensions on in the fixture vault ($V). A folder under the real extensions/ wins,
# else the loader's fixture extension of that name is copied in; then config.md lists exactly these names.
use_extension() {
  local n list=""
  mkdir -p "$V/extensions"
  for n in "$@"; do
    if [[ ! -d "$V/extensions/$n" ]]; then
      if [[ -d "$REPO/extensions/$n" ]]; then cp -r "$REPO/extensions/$n" "$V/extensions/$n"
      else cp -r "$REPO/system/tests/fixtures/extensions/$n" "$V/extensions/$n"; fi
    fi
    list+="${list:+, }\"$n\""
  done
  sed -i '/^extensions:/d' "$V/system/config.md"
  sed -i '$d' "$V/system/config.md"
  printf 'extensions: [%s]\n---\n' "$list" >> "$V/system/config.md"
}
