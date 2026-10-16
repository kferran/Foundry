---
name: dtcc
contract: 1
description: "DTCC Insurance & Retirement Services changes that touch a registered codebase"
requires: []
config_keys: {}
sources:
  - {name: dtcc, credential: "none (public pages)", renew: "check the map with /dtcc-watch check"}
smoke:
  - {source: dtcc, timeout: 60, connector: false, run: "scripts/dtcc_watch.py --check"}
brief: true
units: [{name: foundry-dtcc-watch, roles: [standalone, server]}]
alert_tags: [dtcc]
allow: ["Bash(extensions/dtcc/scripts/dtcc_watch.py --check)", "Bash(extensions/dtcc/scripts/dtcc_watch.py)", "Bash(extensions/dtcc/scripts/dtcc_watch.py --status)"]
deps: [pdftotext]
index_ignore: []
---
**DTCC change watcher.** Watches DTCC Insurance & Retirement Services (Learning Center documents, release dates, Important Notices, the API Marketplace) for changes that touch a registered codebase, and writes a `dtcc_change` note for each into `wiki/<partition>/changes/`. It runs from `system/dtcc/map.yaml`; start from `extensions/dtcc/map.example.yaml`. Run `extensions/dtcc/scripts/dtcc_watch.py --check` and report its lines; exit 2 means the map is invalid, and its lines say why.
