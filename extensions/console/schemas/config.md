---
type: schema
schema_for: config
fields:
  console_port: {kind: int, min: "1024", max: "65535", default: "3110"}
  console_auth: {kind: enum, values: [tailscale, none], default: tailscale}
  console_login: {kind: string}
  console_foreman_url: {kind: string, default: "https://claude.ai/code"}
  console_build_dir: {kind: string, default: "~/.cache/foundry-console"}
---
The console extension's keys (console C1 spec §5). `console_port` is the port on `127.0.0.1` (3110). `console_auth` is `tailscale` (the default: only `console_login` gets an answer) or `none` (no check, for a client's local fallback). `console_login` is your Tailscale login; empty, with `console_auth: tailscale`, every request gets 403. `console_foreman_url` is where "Talk to the Foreman" goes (`https://claude.ai/code`, the session list). `console_build_dir` is where `build.sh` puts the source copy, `node_modules` and the build, outside the vault (`~/.cache/foundry-console`).
