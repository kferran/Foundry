#!/usr/bin/env bats
# The console extension as core sees it (console C1 spec §5, plan Task 2): the manifest, its config keys, the
# always-on unit and the build script. Runs from a vault checkout: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

setup() {
  make_vault
  use_extension console
  cd "$V"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  for c in mise rsync; do
    printf '#!/bin/bash\nprintf "%%s %%s\\n" "%s" "$*" >> "%s/calls"\n' "$c" "$BATS_TEST_TMPDIR" > "$STUBS/$c"
    chmod +x "$STUBS/$c"
  done
}

@test "the manifest loads with one always-on unit, a smoke row and its scripts executable" {
  run system/scripts/extensions.py check
  [ "$status" -eq 0 ]
  run system/scripts/extensions.py units server
  [ "$output" = "$(printf 'console\tfoundry-console\tservice')" ]
  run system/scripts/extensions.py units client
  [ "$output" = "$(printf 'console\tfoundry-console\tservice')" ]
  run system/scripts/extensions.py smoke
  [ "$output" = "$(printf 'console\t30\t0\textensions/console/scripts/today.py --check')" ]
  for s in today.py build.sh serve.sh; do [ -x "extensions/console/scripts/$s" ]; done
}

@test "the config keys validate, and a bad auth or port is an error" {
  sed -i '$d' system/config.md
  printf '%s\n' 'console_port: "3110"' 'console_auth: "tailscale"' 'console_login: "owner@example.com"' '---' >> system/config.md
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -eq 0 ]
  sed -i 's/console_auth: "tailscale"/console_auth: "open"/' system/config.md
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -ne 0 ]
  sed -i 's/console_auth: "open"/console_auth: "none"/; s/console_port: "3110"/console_port: "80"/' system/config.md
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -ne 0 ]
}

@test "the unit renders on 127.0.0.1 with the vault and starts serve.sh" {
  t="$BATS_TEST_TMPDIR/unit"
  sed -e "s|{{VAULT_ROOT}}|$V|g" -e 's|{{TZ}}|UTC|' -e 's|{{UNIT_PATH}}|/usr/bin:/bin|' \
    extensions/console/units/foundry-console.service.in > "$t"
  grep -qx 'Type=simple' "$t"
  grep -qxF 'Environment="NITRO_HOST=127.0.0.1"' "$t"
  grep -qxF "ExecStart=\"$V/extensions/console/scripts/serve.sh\"" "$t"
  run grep -c '{{' "$t"
  [ "$output" = 0 ]
}

@test "build.sh refuses a build dir inside the vault or not absolute" {
  sed -i '$d' system/config.md
  printf 'console_build_dir: "%s/inside"\n---\n' "$V" >> system/config.md
  PATH="$STUBS:$PATH" run extensions/console/scripts/build.sh
  [ "$status" -eq 2 ]
  [[ "$output" == *"must be outside the vault"* ]]
  sed -i "s|console_build_dir: .*|console_build_dir: \"relative/dir\"|" system/config.md
  PATH="$STUBS:$PATH" run extensions/console/scripts/build.sh
  [ "$status" -eq 2 ]
  [[ "$output" == *"must be an absolute path"* ]]
}

@test "build.sh copies the app without node_modules and runs the steps in order" {
  sed -i '$d' system/config.md
  printf 'console_build_dir: "%s/build"\n---\n' "$BATS_TEST_TMPDIR" >> system/config.md
  PATH="$STUBS:$PATH" run extensions/console/scripts/build.sh
  [ "$status" -eq 0 ]
  mapfile -t calls < "$BATS_TEST_TMPDIR/calls"
  [[ "${calls[0]}" == "rsync -a --delete --exclude node_modules --exclude .nuxt --exclude .output $V/extensions/console/app/ $BATS_TEST_TMPDIR/build/src/" ]]
  [ "${calls[1]}" = "mise install" ]
  [ "${calls[2]}" = "mise exec -- npm ci" ]
  [ "${calls[3]}" = "mise exec -- npx nuxi build" ]
}

@test "build.sh names the step that failed" {
  sed -i '$d' system/config.md
  printf 'console_build_dir: "%s/build"\n---\n' "$BATS_TEST_TMPDIR" >> system/config.md
  printf '#!/bin/bash\n[[ "$1" == install ]] && exit 0\nexit 3\n' > "$STUBS/mise"
  PATH="$STUBS:$PATH" run extensions/console/scripts/build.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"npm ci failed"* ]]
}

@test "serve.sh without a build exits 1 and names build.sh" {
  sed -i '$d' system/config.md
  printf 'console_build_dir: "%s/none"\n---\n' "$BATS_TEST_TMPDIR" >> system/config.md
  run extensions/console/scripts/serve.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"run extensions/console/scripts/build.sh"* ]]
}
