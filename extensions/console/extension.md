---
name: console
contract: 1
description: "A web app over the vault: the Today screen, read-only, on 127.0.0.1 behind tailscale serve"
requires: []
sources: []
smoke:
  - {source: console, timeout: 30, connector: false, run: "scripts/today.py --check"}
units:
  - {name: foundry-console, roles: [standalone, server, client], timer: false}
alert_tags: []
allow: []
deps: [mise, rsync, curl, tailscale]
index_ignore: []
budget:
  out: "foundry-console is always on and starts no session: it has no run to time"
---
**Console.** A Vue and Nuxt web app over the vault (console C1 spec, #377). It shows the Today screen: your focus projects, today's objectives, the Now lines with their overdue bands, the Work Orders, the morning's calendar and meeting actions, and the pipeline's state. It reads the vault only through `extensions/console/scripts/today.py --json`, which runs the core scripts' `--json` commands and reads the morning's prep. It never writes to the vault and never starts a connector session.

**Where it runs.** `foundry-console.service` is always on (`timer: false`) and listens on `127.0.0.1:<console_port>` only. On the server, `tailscale serve` puts it on your tailnet over HTTPS; on a client such as a laptop it is a local fallback that reads the last synced copy of the vault.

**Setup questions** (`/setup` phase 6e asks them when you turn the console on):
1. On the server: your Tailscale login, for `console_login` (such as `owner@example.com`). Leave `console_auth` at `tailscale`.
2. On a client: set `console_auth: "none"`; the page answers only on `127.0.0.1`.
3. `console_port` if 3110 is taken.

**Then run, in order:**
1. `extensions/console/scripts/build.sh`: copies `extensions/console/app/` to `console_build_dir` (default `~/.cache/foundry-console`), outside the vault, and installs and builds it there. Run it again after a template update that changes `app/` (its change file says so), then `systemctl --user restart foundry-console`.
2. `system/scripts/install_units.sh`: installs and starts `foundry-console.service`.
3. On the server only, once: `tailscale serve --bg --https=443 http://127.0.0.1:<console_port>`. Nothing runs this for you.

**Security.** The app binds `127.0.0.1` and refuses to start on any other host. With `console_auth: tailscale` it answers 403 unless the `Tailscale-User-Login` header that `tailscale serve` adds equals `console_login`, and an empty `console_login` refuses every request. Every route is a GET, none takes input that reaches a command or a path, and the app holds no token. A process on the server itself can send that header to `127.0.0.1`; local processes can already read the vault.
