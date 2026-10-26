#!/bin/bash
# Start the built console for foundry-console.service (console C1 spec §5): node on 127.0.0.1 at console_port,
# from <console_build_dir>/src/.output. The unit cannot read config keys, so this reads them.
# Usage: serve.sh. Exit: node's; 1 when nothing is built (run build.sh); 2 a bad setting.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=../../../system/scripts/lib_config.sh
source system/scripts/lib_config.sh

(( $# == 0 )) || { echo "usage: serve.sh" >&2; exit 2; }
dir="$(config_get console_build_dir "$HOME/.cache/foundry-console")"
port="$(config_get console_port 3110)"
[[ "$port" =~ ^[0-9]+$ ]] || { echo "serve.sh: console_port is not a number: $port" >&2; exit 2; }
server="$dir/src/.output/server/index.mjs"
[[ -f "$server" ]] || { echo "serve.sh: no build at $dir/src; run extensions/console/scripts/build.sh" >&2; exit 1; }
auth="$(config_get console_auth tailscale)"
login="$(config_get console_login "")"
export NITRO_HOST=127.0.0.1 NITRO_PORT="$port" FOUNDRY_VAULT="$VAULT_ROOT" CONSOLE_AUTH="$auth" CONSOLE_LOGIN="$login"
exec mise exec --cd "$dir/src" -- node "$server"
