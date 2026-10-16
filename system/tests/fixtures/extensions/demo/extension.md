---
name: demo
contract: 1
description: "A fixture extension for the loader tests"
requires: []
config_keys:
  demo_site: {kind: string, default: ""}
sources:
  - {name: demo, credential: "Demo connector", renew: "reconnect it at example.invalid"}
smoke:
  - {source: demo, timeout: 30, connector: false, run: "scripts/demo_check.sh"}
brief: true
units: [{name: foundry-demo, roles: [standalone, server]}]
alert_tags: [demo]
allow: ["Bash(extensions/demo/scripts/demo_check.sh)"]
deps: []
index_ignore: ["raw/demo"]
---
The text /setup shows when the owner turns demo on, and the questions it asks.
