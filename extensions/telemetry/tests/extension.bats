#!/usr/bin/env bats
# The telemetry extension as core sees it (extensions spec §3): the manifest, the per-source smoke and Sources rows,
# the brief section, the units, the skill link, the intake tick and the migration from the old switch.
# Runs from a vault checkout: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

setup() {
  make_vault
  use_extension handoffs telemetry
  cd "$V"
  mkdir -p system/telemetry system/codebases "$BATS_TEST_TMPDIR/bin"
  printf -- '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n' > system/codebases/shop.md
  printf -- '---\ntype: telemetry_source\nname: "prod-adx"\ncodebase: "shop"\nenvironment: "prod"\nkind: "adx"\nadx_cluster: "https://example.kusto.windows.net"\nadx_database: "prod"\nadx_signals: ["logs"]\n---\n' > system/telemetry/prod-adx.md
  printf '#!/bin/bash\necho tok\n' > "$BATS_TEST_TMPDIR/bin/az"
  chmod +x "$BATS_TEST_TMPDIR/bin/az"
  export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
  export FOUNDRY_TELEMETRY_STUB="$BATS_TEST_TMPDIR/stub"
  cp -r "$REPO/extensions/telemetry/tests/fixtures/telemetry" "$FOUNDRY_TELEMETRY_STUB"
  IN="$V/system/logs/inputs/2026-10-01"
}

# prep_telemetry: the brief section's prep.sh as brief_prep.sh sources it, in a subshell with the prep_* functions.
prep_telemetry() {
  (
    VAULT_ROOT="$V"
    source system/scripts/lib_config.sh
    source system/scripts/lib_prep.sh
    PREP_NAME=brief_prep PREP_DATE=2026-10-01 PREP_DIR="$IN"
    mkdir -p "$PREP_DIR/sections"
    prep_sources_init
    # shellcheck disable=SC1091
    source extensions/telemetry/brief/prep.sh
  )
}

@test "the manifest loads after handoffs, with one per-source smoke row, the hourly unit, a tick and its scripts executable" {
  run system/scripts/extensions.py list
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf 'handoffs\ntelemetry')" ]
  run system/scripts/extensions.py check
  [ "$status" -eq 0 ]
  run system/scripts/extensions.py smoke
  grep -qxF "$(printf 'telemetry\t120\t0\textensions/telemetry/scripts/telemetry_fetch.py --check {}\textensions/telemetry/scripts/telemetry_fetch.py --sources')" <<< "$output"
  run system/scripts/extensions.py units server
  [ "$output" = "$(printf 'telemetry\tfoundry-telemetry\ttimer')" ]
  for s in telemetry_fetch.py rca.py rca_file.sh; do
    [ -x "extensions/telemetry/scripts/$s" ]
  done
}

@test "telemetry without handoffs does not load: its RCA filer needs the handoffs site" {
  sed -i 's/^extensions:.*/extensions: ["telemetry"]/' system/config.md
  run system/scripts/extensions.py check
  [ "$status" -eq 1 ]
  [ "$output" = "telemetry: requires handoffs, which is missing or not loadable" ]
}

@test "--sources lists each enabled source with the login its kind needs; the Sources line and the smoke check read it" {
  printf -- '---\ntype: telemetry_source\nname: "off"\ncodebase: "shop"\nenvironment: "uat"\nkind: "adx"\nenabled: "false"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n' > system/telemetry/off.md
  run extensions/telemetry/scripts/telemetry_fetch.py --sources
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf 'prod-adx\tAzure CLI\taz login on the server')" ]
  run system/scripts/sources.py credential telemetry/prod-adx "auth: run az login"
  [ "$output" = "$(printf 'Azure CLI\taz login on the server')" ]
  run system/scripts/sources.py report 2026-10-01
  grep -qx -- '- telemetry/prod-adx: unknown (no smoke check reading today)' <<< "$output"
  rm system/telemetry/prod-adx.md
  run system/scripts/sources.py report 2026-10-01
  grep -qx -- '- telemetry: off' <<< "$output"
}

@test "brief section: fetch exit codes become Unavailable Sources lines; exit 0 adds none" {
  for code in 0 1 4; do
    printf '#!/bin/bash\nexit %s\n' "$code" > extensions/telemetry/scripts/telemetry_fetch.py
    run prep_telemetry
    [ "$status" -eq 0 ]
  done
  grep -qxF -- '- brief_prep: telemetry: a source failed (see system/logs/telemetry-2026-10.jsonl)' "$IN/unavailable.md"
  grep -qxF -- '- brief_prep: telemetry: a fetch was already running' "$IN/unavailable.md"
  [ "$(grep -c 'brief_prep: telemetry' "$IN/unavailable.md")" -eq 2 ]
}

@test "brief section: the active groups as one table and the source ranks; empty with no group" {
  run prep_telemetry
  [ "$status" -eq 0 ]
  grep -q '^## Error groups (cutoff ' "$IN/sections/telemetry.md"
  grep -q '^| path | environment | source | service | exception | count |' "$IN/sections/telemetry.md"
  grep -q '^| raw/telemetry/prod-adx-a-' "$IN/sections/telemetry.md"
  grep -qx '## Sources' "$IN/sections/telemetry.md"
  grep -qF '| prod-adx | prod | 50 |' "$IN/sections/telemetry.md"
  rm -rf raw/telemetry system/logs/telemetry_state.json system/telemetry/prod-adx.md
  run prep_telemetry
  [ "$status" -eq 0 ]
  [ -e "$IN/sections/telemetry.md" ]
  [ ! -s "$IN/sections/telemetry.md" ]
}

@test "the intake tick's command exits 0 and files nothing while rca_project is empty" {
  run extensions/telemetry/scripts/rca.py tick
  [ "$status" -eq 0 ]
  [ ! -e system/logs/rca ]
}

@test "the rca skill is linked while the extension is on and unlinked when it goes off" {
  git init -q .
  run system/scripts/extensions.py link
  [ "$status" -eq 0 ]
  grep -qx 'linked rca' <<< "$output"
  [ "$(readlink .claude/skills/rca)" = "../../extensions/telemetry/skills/rca" ]
  grep -q '^name: rca$' .claude/skills/rca/SKILL.md
  sed -i 's/^extensions:.*/extensions: ["handoffs"]/' system/config.md
  run system/scripts/extensions.py link
  grep -qx 'unlinked rca' <<< "$output"
  [ ! -e .claude/skills/rca ]
}

@test "the update turns telemetry on, with handoffs first, when the vault has a telemetry source; once" {
  sed -i '/^extensions:/d' system/config.md
  run system/scripts/extensions.py migrate
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf 'enabled handoffs\nenabled telemetry')" ]
  grep -qx 'extensions: \["handoffs", "telemetry"\]' system/config.md
  sed -i '/^extensions:/d' system/config.md
  run system/scripts/extensions.py migrate
  [ -z "$output" ]
}

@test "a vault with only the example source is not migrated" {
  sed -i '/^extensions:/d' system/config.md
  rm system/telemetry/prod-adx.md
  cp extensions/telemetry/templates/telemetry-source.example.md system/telemetry/example.md
  run system/scripts/extensions.py migrate
  [ -z "$output" ]
}

@test "the telemetry timer installs with the extension on a standalone machine or a server, with no sync drop-in" {
  need_user_systemd
  cp -r "$REPO/system/systemd" system/systemd
  mkdir -p "$BATS_TEST_TMPDIR/stubs"
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\n' > "$BATS_TEST_TMPDIR/stubs/systemctl"
  chmod +x "$BATS_TEST_TMPDIR/stubs/systemctl"
  ln -s "$REPO/system/tests/stub_claude" "$BATS_TEST_TMPDIR/stubs/claude"
  export PATH="$BATS_TEST_TMPDIR/stubs:$PATH" SYSTEMCTL="$BATS_TEST_TMPDIR/stubs/systemctl"
  export STUB_SYSTEMCTL_LOG="$BATS_TEST_TMPDIR/systemctl.log" SYSTEMD_USER_DIR="$BATS_TEST_TMPDIR/units" HOME="$BATS_TEST_TMPDIR/home"
  system/scripts/vault_index.py set system/config.md machine_role server > /dev/null
  run system/scripts/install_units.sh
  [ "$status" -eq 0 ]
  grep -q '^OnUnitActiveSec=1h$' "$SYSTEMD_USER_DIR/foundry-telemetry.timer"
  grep -qF 'extensions/telemetry/scripts/telemetry_fetch.py' "$SYSTEMD_USER_DIR/foundry-telemetry.service"
  grep -q 'enable --now .*foundry-telemetry.timer' "$STUB_SYSTEMCTL_LOG"
  [ ! -e "$SYSTEMD_USER_DIR/foundry-telemetry.service.d" ]
  sed -i 's/^extensions:.*/extensions: ["handoffs"]/' system/config.md
  run system/scripts/install_units.sh --update
  [ ! -e "$SYSTEMD_USER_DIR/foundry-telemetry.timer" ]
}
