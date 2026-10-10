# Shared setup for shell suites. Usage: load helpers; make_vault
make_vault() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
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
  cat > "$V/system/config.md" <<'EOF'
---
type: config
timezone: "America/Denver"
brief_time: "06:00"
debrief_time: "17:00"
remote_mode: "none"
default_partition: "personal"
---
EOF
  git -C "$V" init -q
  git -C "$V" config user.email test@example.com
  git -C "$V" config user.name test
}
